"""LSP and idle auto-format helpers for :class:`~editor_widget.CodeEditorWidget`."""

from __future__ import annotations

import json
import subprocess
import tempfile
import xml.dom.minidom
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import QMenu

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPlainTextEdit

    _FormattingBase = QPlainTextEdit
else:
    _FormattingBase = object

# Ctrl+Shift chords match other editor shortcuts (Ctrl+Q, Ctrl+P, Ctrl+/).
_FORMAT_DOCUMENT_KEYSEQ = QKeySequence("Ctrl+Shift+F")
_FORMAT_SELECTION_KEYSEQ = QKeySequence("Ctrl+Shift+S")


def _format_snippet_with_deno(source: str, extension: str) -> str | None:
    """Run ``deno fmt`` on a temp file; return formatted text or ``None``."""
    from services.scripting.deno_manager import DenoManager

    deno = DenoManager.managed_deno_path()
    if deno is None or not source.strip():
        return None
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=extension,
            delete=False,
            encoding="utf-8",
        ) as fh:
            fh.write(source)
            if not source.endswith("\n"):
                fh.write("\n")
            path = Path(fh.name)
        proc = subprocess.run(
            [str(deno), "fmt", str(path)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode != 0:
            return None
        out = path.read_text(encoding="utf-8")
        return out.rstrip("\n") if not source.endswith("\n") else out
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def _apply_lsp_text_edits(editor: Any, edits: list[dict[str, Any]]) -> bool:
    """Apply LSP ``TextEdit`` items to *editor*'s document (reverse document order)."""
    from services.lsp.qt_lsp_offsets import lsp_to_qpos

    doc = editor.document()
    parsed: list[tuple[int, int, str]] = []
    for edit in edits:
        rng = edit.get("range") or {}
        start = rng.get("start") or {}
        end = rng.get("end") or {}
        s = lsp_to_qpos(
            doc,
            int(start.get("line", 0)),
            int(start.get("character", 0)),
        )
        e = lsp_to_qpos(
            doc,
            int(end.get("line", 0)),
            int(end.get("character", 0)),
        )
        parsed.append((s, e, str(edit.get("newText", ""))))
    if not parsed:
        return False
    parsed.sort(key=lambda item: item[0], reverse=True)
    cur = QTextCursor(doc)
    cur.beginEditBlock()
    for start, end, new_text in parsed:
        cur.setPosition(start)
        cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cur.insertText(new_text)
    cur.endEditBlock()
    return True


def _menu_cut_action(menu: QMenu) -> QAction | None:
    """Return the standard Cut action, if present."""
    for act in menu.actions():
        if act.isSeparator():
            continue
        if "Ctrl+X" in act.text():
            return act
    return None


class _FormattingMixin(_FormattingBase):
    """Mixin providing prettify and format-on-idle behaviour."""

    _format_in_progress: bool
    _skip_format_on_idle: bool
    _format_on_idle_timer: Any
    _format_saved_selection: tuple[int, int]

    def _install_format_shortcuts(self) -> None:
        """Register Ctrl+Shift+F (document) and Ctrl+Shift+S (selection) format shortcuts."""
        if self._read_only or self.isReadOnly():
            return
        ctx = Qt.ShortcutContext.WidgetShortcut
        doc_sc = QShortcut(_FORMAT_DOCUMENT_KEYSEQ, self)
        doc_sc.setContext(ctx)
        doc_sc.activated.connect(self.format_document)
        sel_sc = QShortcut(_FORMAT_SELECTION_KEYSEQ, self)
        sel_sc.setContext(ctx)
        sel_sc.activated.connect(self._activate_format_selection_shortcut)

    def _activate_format_selection_shortcut(self) -> None:
        """Format selection shortcut — no-op without an active selection."""
        if not self.textCursor().hasSelection():
            return
        self.format_selection()

    def format_document(self) -> bool:
        """Format the entire buffer (context menu / legacy ``prettify`` alias)."""
        return self.prettify()

    def format_selection(self) -> bool:
        """Format the current selection (LSP range, ``deno fmt``, or JSON/XML/HTML)."""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return False
        selected = cursor.selectedText().replace("\u2029", "\n")
        if not selected.strip():
            return False

        self._format_saved_selection = (cursor.selectionStart(), cursor.selectionEnd())

        adapter = getattr(self, "_lsp_adapter", None)
        if (
            adapter is not None
            and bool(getattr(adapter, "is_ready", False))
            and self._language in ("javascript", "typescript")
        ):
            future = adapter.request_format_range()
            if future is not None:
                self._format_in_progress = True
                future.add_done_callback(self._on_lsp_format_selection_response)
                return False

        return self._apply_format_selection_text(selected, cursor)

    def _format_text_snippet(self, text: str) -> str | None:
        """Return formatted *text* for the current language, or ``None``."""
        if self._language == "python":
            from services.scripting.python_format import format_python_source

            return format_python_source(text)
        if self._language in ("javascript", "typescript"):
            ext = ".ts" if self._language == "typescript" else ".js"
            return _format_snippet_with_deno(text, ext)
        if self._language == "json":
            try:
                parsed = json.loads(text)
                return json.dumps(parsed, indent=4, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                return None
        if self._language in ("xml", "html"):
            try:
                dom = xml.dom.minidom.parseString(text)
                return dom.toprettyxml(indent="    ")
            except Exception:
                return None
        return None

    def _apply_format_selection_text(self, selected: str, cursor: QTextCursor) -> bool:
        """Replace *selected* with a formatted equivalent when possible."""
        replacement = self._format_text_snippet(selected)
        if replacement is None or replacement == selected:
            return False
        cursor.insertText(replacement)
        return True

    def _restore_format_selection(self, cursor: QTextCursor) -> None:
        """Re-select the range saved when format selection started."""
        start, end = getattr(self, "_format_saved_selection", (0, 0))
        if end > start:
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

    def _add_format_menu_actions(self, menu: QMenu) -> None:
        """Insert Format Document / Selection after Undo & Redo, then a separator above Cut."""
        if self._read_only or self.isReadOnly():
            return
        cut = _menu_cut_action(menu)
        if cut is None:
            if self.textCursor().hasSelection():
                sel_act = QAction("Format Selection", self)
                sel_act.setShortcut(_FORMAT_SELECTION_KEYSEQ)
                sel_act.triggered.connect(self.format_selection)
                menu.addAction(sel_act)
            doc_act = QAction("Format Document", self)
            doc_act.setShortcut(_FORMAT_DOCUMENT_KEYSEQ)
            doc_act.triggered.connect(self.format_document)
            menu.addAction(doc_act)
            return
        if self.textCursor().hasSelection():
            sel_act = QAction("Format Selection", self)
            sel_act.setShortcut(_FORMAT_SELECTION_KEYSEQ)
            sel_act.triggered.connect(self.format_selection)
            menu.insertAction(cut, sel_act)
        doc_act = QAction("Format Document", self)
        doc_act.setShortcut(_FORMAT_DOCUMENT_KEYSEQ)
        doc_act.triggered.connect(self.format_document)
        menu.insertAction(cut, doc_act)
        menu.insertSeparator(cut)

    def _apply_python_document_format(self) -> bool:
        """Replace the buffer with Ruff-formatted Python (jedi LSP has no formatter)."""
        from services.scripting.python_format import format_python_source

        text = self.toPlainText()
        formatted = format_python_source(text)
        if formatted is None or formatted == text:
            return False
        cursor_pos = self.textCursor().position()
        self._skip_format_on_idle = True
        try:
            self.setPlainText(formatted)
        finally:
            self._skip_format_on_idle = False
        cur = self.textCursor()
        cur.setPosition(min(cursor_pos, len(formatted)))
        self.setTextCursor(cur)
        return True

    def prettify(self) -> bool:
        """Auto-format the current content. Return True if formatting changed synchronously."""
        text = self.toPlainText()
        if not text.strip():
            return False

        if self._language == "python":
            return self._apply_python_document_format()

        adapter = getattr(self, "_lsp_adapter", None)
        if adapter is not None and self._language in ("javascript", "typescript"):
            future = adapter.request_format()
            if future is not None:
                self._format_in_progress = True
                future.add_done_callback(self._on_lsp_format_response)
                return False

        if self._language == "json":
            try:
                parsed = json.loads(text)
                pretty = json.dumps(parsed, indent=4, ensure_ascii=False)
                if pretty != text:
                    self.setPlainText(pretty)
                    return True
            except (json.JSONDecodeError, TypeError):
                pass
        elif self._language in ("xml", "html"):
            try:
                dom = xml.dom.minidom.parseString(text)
                pretty = dom.toprettyxml(indent="    ")
                if pretty != text:
                    self.setPlainText(pretty)
                    return True
            except Exception:
                pass
        return False

    def _on_lsp_format_selection_response(self, future: Any) -> None:
        """Apply range-format LSP edits, or fall back to ``deno fmt`` / snippet format."""
        try:
            raw = future.result(timeout_s=0.0)
        except Exception:
            raw = None
        finally:
            self._format_in_progress = False
        if isinstance(raw, list) and raw and _apply_lsp_text_edits(self, raw):
            return
        cursor = self.textCursor()
        if not cursor.hasSelection():
            self._restore_format_selection(cursor)
        selected = cursor.selectedText().replace("\u2029", "\n")
        if selected.strip():
            self._apply_format_selection_text(selected, cursor)

    def _on_lsp_format_response(self, future: Any) -> None:
        """Apply full-document format edits from the LSP."""
        try:
            raw = future.result(timeout_s=0.0)
        except Exception:
            raw = None
        finally:
            self._format_in_progress = False
        if raw is None:
            return
        if isinstance(raw, list) and _apply_lsp_text_edits(self, raw):
            return
        if self._language == "python":
            self._apply_python_document_format()
            return
        if not isinstance(raw, list) or not raw:
            return
        new_text = str(raw[0].get("newText", ""))
        if not new_text or new_text == self.toPlainText():
            return
        cursor_pos = self.textCursor().position()
        self._skip_format_on_idle = True
        try:
            self.setPlainText(new_text)
        finally:
            self._skip_format_on_idle = False
        cur = self.textCursor()
        cur.setPosition(min(cursor_pos, len(new_text)))
        self.setTextCursor(cur)

    def _schedule_format_on_idle(self) -> None:
        """Restart the debounced format-on-save timer after user edits."""
        if self._skip_format_on_idle or self._read_only or self.isReadOnly():
            return
        self._format_on_idle_timer.start()

    def _on_format_on_idle_timeout(self) -> None:
        """Run LSP prettify when format-on-save is enabled and idle."""
        from services.scripting.runtime_settings import RuntimeSettings

        if self._format_in_progress or self._skip_format_on_idle:
            return
        if not RuntimeSettings.format_on_save():
            return
        self.format_document()
