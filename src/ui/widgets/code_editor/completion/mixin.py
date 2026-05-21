"""Completion mixin for the code editor.

Provides ``_CompletionMixin`` containing trigger, filter, accept, and
popup positioning logic.  Must be combined with ``QPlainTextEdit`` via
``CodeEditorWidget``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QKeyEvent, QMouseEvent, QTextCursor
from PySide6.QtWidgets import QApplication, QPlainTextEdit

_SYMBOL_HOVER_DELAY_MS = 400
_LSP_DEF_HOVER_DELAY_MS = 350

if TYPE_CHECKING:
    from ui.widgets.code_editor.completion.engine import CompletionEngine
    from ui.widgets.code_editor.completion.parameter_hint import ParameterHintPopup
    from ui.widgets.code_editor.completion.popup import CompletionPopup
    from ui.widgets.code_editor.completion.symbol_doc_popup import SymbolDocPopup
    from ui.widgets.code_editor.debug_hover_popup import DebugValuePopup

    _CompletionBase = QPlainTextEdit
else:
    _CompletionBase = object


class _CompletionMixin(_CompletionBase):
    """Mixin providing code completion trigger, filter, and accept logic."""

    # -- Shared popup accessors (app-wide singletons; see popup_registry) ---

    @property
    def _completion_popup(self) -> CompletionPopup:
        from ui.widgets.code_editor import popup_registry

        return popup_registry.completion_popup()

    @property
    def _parameter_hint_popup(self) -> ParameterHintPopup:
        from ui.widgets.code_editor import popup_registry

        return popup_registry.parameter_hint_popup()

    @property
    def _symbol_doc_popup(self) -> SymbolDocPopup:
        from ui.widgets.code_editor import popup_registry

        return popup_registry.symbol_doc_popup()

    @property
    def _debug_popup(self) -> DebugValuePopup:
        from ui.widgets.code_editor import popup_registry

        return popup_registry.debug_value_popup()

    # -- Attribute stubs (set by CodeEditorWidget.__init__) -------------
    _symbol_hover_path: str | None
    _symbol_hover_global_pos: QPoint
    _symbol_hover_timer: QTimer
    _lsp_def_hover_timer: QTimer
    _lsp_def_hover_pending: bool
    _completion_engine: CompletionEngine
    _completion_prefix: str

    if TYPE_CHECKING:

        def toggle_fold(self, line: int) -> None: ...

    _fold_badge_rects: dict[int, QRect]
    _var_hover_name: str | None
    _var_hover_global_pos: QPoint
    _var_hover_timer: QTimer

    # -- Completion methods ---------------------------------------------

    def _completion_text_before_cursor(self) -> str:
        """Document text before the cursor (for string-literal completion)."""
        return self._text_before_cursor_document()

    def _trigger_completion(self) -> None:
        """Compute and show completions at the current cursor position."""
        self._parameter_hint_popup.hide_hint()
        self._symbol_doc_popup.hide_popup()
        self._completion_engine.scan_assignments(self.toPlainText())
        text_before = self._completion_text_before_cursor()
        in_local = self._completion_engine.is_local_require_completion_context(text_before)

        items = self._completion_engine.complete(text_before)
        prefix = ""
        if not items and not in_local:
            prefix = self._completion_engine.identifier_prefix(text_before)
            items = self._completion_engine.top_level_filtered(prefix)
        if not items:
            self._completion_popup.dismiss()
            return

        self._completion_prefix = prefix
        self._completion_popup.set_target(
            self._accept_completion,
            self._on_completion_dismissed,
        )
        self._completion_popup.set_items(items)
        self._position_completion_popup()
        self._completion_popup.show()

    def _filter_completion(self) -> None:
        """Re-filter the completion list as the user types."""
        text_before = self._completion_text_before_cursor()
        in_local = self._completion_engine.is_local_require_completion_context(text_before)

        items = self._completion_engine.complete(text_before)
        if not items and not in_local:
            prefix = self._completion_engine.identifier_prefix(text_before)
            items = self._completion_engine.top_level_filtered(prefix)
        if not items:
            self._completion_popup.dismiss()
            return
        self._completion_popup.set_items(items)

    def _maybe_trigger_local_path_completion(self) -> None:
        """Open or refresh local-script path completion after the cursor moves."""
        text_before = self._completion_text_before_cursor()
        if not self._completion_engine.is_local_require_completion_context(text_before):
            return
        if self._completion_popup.is_active():
            self._filter_completion()
        else:
            self._trigger_completion()

    def _position_completion_popup(self) -> None:
        """Place the popup below the current cursor position."""
        cursor_rect = self.cursorRect()
        global_pos = self.mapToGlobal(cursor_rect.bottomLeft())
        self._completion_popup.move(global_pos)

    def _accept_completion(self, insert_text: str, kind: str) -> None:
        """Insert the accepted completion text at the cursor."""
        cursor = self.textCursor()

        if self._completion_engine.is_local_require_completion_context(
            self._completion_text_before_cursor()
        ):
            text_before = self._completion_text_before_cursor()
        else:
            block_text = cursor.block().text()
            col = cursor.positionInBlock()
            text_before = block_text[:col]

        # Find how many chars of the completion are already typed.
        prefix_len = 0
        scan_len = min(len(insert_text), len(text_before))
        for i in range(scan_len, 0, -1):
            candidate = text_before[-i:]
            if insert_text.lower().startswith(candidate.lower()):
                prefix_len = i
                break

        if prefix_len > 0:
            for _ in range(prefix_len):
                cursor.deletePreviousChar()

        cursor.insertText(insert_text)

        # Append () for methods and place cursor between them.
        if kind == "method":
            cursor.insertText("()")
            cursor.movePosition(
                QTextCursor.MoveOperation.Left,
                QTextCursor.MoveMode.MoveAnchor,
            )
            self.setTextCursor(cursor)

    def _on_completion_dismissed(self) -> None:
        """Clean up when the completion popup is dismissed."""
        self._completion_prefix = ""
        self._completion_popup.clear_target()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Expand a collapsed fold when its ``...`` badge is clicked."""
        # Ctrl+click — jump to definition or show the schema doc.
        if event.button() == Qt.MouseButton.LeftButton and (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            pos = event.position().toPoint()
            hit = self._ident_at_pos(pos)  # type: ignore[attr-defined]
            if hit is not None:
                path, _start, _end = hit
                if self._completion_engine.is_linkable_symbol(path, self.toPlainText()):
                    head = path.split(".", 1)[0]
                    target = self._completion_engine.find_definition_pos(head, self.toPlainText())
                    self.set_symbol_link_range(None, None)  # type: ignore[attr-defined]
                    if target is not None:
                        cur = self.textCursor()
                        cur.setPosition(target)
                        self.setTextCursor(cur)
                        self.centerCursor()
                        event.accept()
                        return
                    sym = self._completion_engine.resolve_symbol(path, self.toPlainText())
                    if sym is not None:
                        self._symbol_hover_global_pos = event.globalPosition().toPoint()
                        self._symbol_doc_popup.show_for(
                            self._symbol_hover_global_pos,
                            sym._replace(origin=f"{sym.origin} (no source location)"),
                        )
                        event.accept()
                        return
                if self._try_open_local_require_at_cursor():
                    event.accept()
                    return
                adapter = getattr(self, "_lsp_adapter", None)
                if adapter is not None:
                    cur = self.textCursor()
                    cur.setPosition(_start)
                    self.setTextCursor(cur)
                    future = adapter.request_definition()
                    if future is not None:
                        future.add_done_callback(self._on_lsp_definition_response)
                        event.accept()
                        return
        if self._debug_popup.isVisible() and hasattr(self, "_hide_debug_value_popup"):
            self._hide_debug_value_popup()  # type: ignore[attr-defined]
        if self._completion_popup.is_active():
            self._completion_popup.dismiss()
        self._parameter_hint_popup.hide_hint()
        self._symbol_doc_popup.hide_popup()
        if event.button() == Qt.MouseButton.LeftButton and self._fold_badge_rects:
            pos = event.position().toPoint()
            for start_line, rect in self._fold_badge_rects.items():
                if rect.contains(pos):  # type: ignore[arg-type]
                    self.toggle_fold(start_line)
                    return
        super().mousePressEvent(event)

    def _on_lsp_definition_response(self, future: object) -> None:
        """Jump to LSP definition in-buffer or open another host tab."""
        from pathlib import Path
        from urllib.parse import unquote, urlparse
        from urllib.request import url2pathname

        from services.lsp.qt_lsp_offsets import lsp_to_qpos
        from ui.widgets.code_editor.editor_widget import CodeEditorWidget

        adapter = getattr(self, "_lsp_adapter", None)
        if adapter is None:
            return
        try:
            locs = future.result(timeout_s=0.0)  # type: ignore[attr-defined]
        except Exception:
            locs = None
        if locs:
            loc = locs[0]
            uri = str(getattr(loc, "uri", ""))
            own_uri = str(getattr(adapter, "_uri", ""))
            if uri == own_uri:
                target = lsp_to_qpos(self.document(), int(loc.line), int(loc.column))
                cur = self.textCursor()
                cur.setPosition(target)
                self.setTextCursor(cur)
                self.centerCursor()
                return
            if uri.startswith("file:"):
                parsed = urlparse(uri)
                fs_path = Path(url2pathname(unquote(parsed.path)))
                parts = fs_path.parts
                if "local" in parts:
                    idx = parts.index("local")
                    if idx + 1 < len(parts):
                        stem = Path(parts[idx + 1]).stem
                        if stem.isdigit() and CodeEditorWidget._invoke_open_local_script(int(stem)):
                            return
        self._try_open_local_require_at_cursor()

    def _on_lsp_def_hover_timeout(self) -> None:
        """Debounced LSP definition probe for Ctrl+hover pointer cursor."""
        adapter = getattr(self, "_lsp_adapter", None)
        if adapter is None or self._lsp_def_hover_pending:
            return
        future = adapter.request_definition()
        if future is None:
            return
        self._lsp_def_hover_pending = True
        future.add_done_callback(self._on_lsp_def_hover_response)

    def _try_open_local_require_at_cursor(self) -> bool:
        """Open a local script tab when the cursor sits on ``pm.require('local:…')``."""
        from services.local_script_service import LocalScriptService
        from services.scripting.local_script_modules import local_require_path_at_offset
        from ui.widgets.code_editor.editor_widget import CodeEditorWidget

        hit = local_require_path_at_offset(self.toPlainText(), self.textCursor().position())
        if hit is None:
            return False
        rel, _, _ = hit
        script_id = LocalScriptService.resolve_script_id_by_virtual_path(rel)
        if script_id is None:
            return False
        return CodeEditorWidget._invoke_open_local_script(script_id)

    def _on_lsp_def_hover_response(self, future: object) -> None:
        """Apply pointing-hand cursor when LSP reports a definition at hover position."""
        self._lsp_def_hover_pending = False
        if not (QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier):  # type: ignore[name-defined]
            return
        try:
            locs = future.result(timeout_s=0.0)  # type: ignore[attr-defined]
        except Exception:
            locs = None
        if locs:
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        """Clear the Ctrl+hover underline as soon as Ctrl is released."""
        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Meta):
            if self._symbol_hover_path is not None:
                self._symbol_hover_path = None
                self._symbol_hover_timer.stop()  # type: ignore[union-attr]
            self._lsp_def_hover_timer.stop()  # type: ignore[union-attr]
            self._lsp_def_hover_pending = False
            self.set_symbol_link_range(None, None)  # type: ignore[attr-defined]
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        super().keyReleaseEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Track variable hover and fold-badge cursor changes."""
        pos = event.position().toPoint()

        # 1. Fold badge cursor.
        if self._fold_badge_rects:
            for rect in self._fold_badge_rects.values():
                if rect.contains(pos):  # type: ignore[arg-type]
                    self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
                    super().mouseMoveEvent(event)
                    return
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)

        # 1b. Ctrl+hover — quick doc popup for code identifiers.
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            hit = self._ident_at_pos(pos)  # type: ignore[attr-defined]
            if hit is not None:
                path, doc_start, doc_end = hit
                if self._completion_engine.is_linkable_symbol(path, self.toPlainText()):
                    self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
                    if path != self._symbol_hover_path:
                        self._symbol_hover_path = path
                        self._symbol_hover_global_pos = event.globalPosition().toPoint()
                        self.set_symbol_link_range(doc_start, doc_end)  # type: ignore[attr-defined]
                        self._symbol_hover_timer.stop()  # type: ignore[union-attr]
                        self._symbol_hover_timer.start(_SYMBOL_HOVER_DELAY_MS)  # type: ignore[union-attr]
                    super().mouseMoveEvent(event)
                    return
            adapter = getattr(self, "_lsp_adapter", None)
            if adapter is not None:
                self._lsp_def_hover_timer.stop()  # type: ignore[union-attr]
                self._lsp_def_hover_timer.start(_LSP_DEF_HOVER_DELAY_MS)  # type: ignore[union-attr]
                super().mouseMoveEvent(event)
                return
        if self._symbol_hover_path is not None:
            self._symbol_hover_path = None
            self._symbol_hover_timer.stop()  # type: ignore[union-attr]
            self._symbol_doc_popup.hide_popup()
            self.set_symbol_link_range(None, None)  # type: ignore[attr-defined]
        self._lsp_def_hover_timer.stop()  # type: ignore[union-attr]
        self._lsp_def_hover_pending = False

        # 2. Variable hover tracking.
        var_name = self._var_at_cursor(pos)  # type: ignore[attr-defined]
        if var_name:
            if var_name != self._var_hover_name:
                if self._debug_popup.isVisible():
                    self._hide_debug_value_popup()  # type: ignore[attr-defined]
                self._var_hover_name = var_name
                self._var_hover_global_pos = event.globalPosition().toPoint()
                from ui.widgets.variable_popup import VariablePopup

                self._var_hover_timer.start(VariablePopup.hover_delay_ms())  # type: ignore[union-attr]
        else:
            if self._debug_popup.isVisible():
                # Sticky debug hover: micro-moves can leave the token hit-test without
                # the pointer leaving the editor; keep the popup until click-away or Escape.
                super().mouseMoveEvent(event)
                return
            if self._var_hover_name is not None:
                self._var_hover_name = None
                self._var_hover_timer.stop()  # type: ignore[union-attr]
                if hasattr(self, "_hide_debug_value_popup"):
                    self._hide_debug_value_popup()  # type: ignore[attr-defined]

        super().mouseMoveEvent(event)

    def _text_before_cursor_document(self) -> str:
        """Return all document text strictly before the text cursor."""
        cur = self.textCursor()
        return self.toPlainText()[: cur.position()]

    def _try_show_parameter_hint(self) -> None:
        """Show parameter hint for the innermost call surrounding the cursor, if known."""
        self._completion_engine.scan_assignments(self.toPlainText())
        data = self._completion_engine.resolve_nearest_call_signature(
            self._text_before_cursor_document()
        )
        if not data:
            self._parameter_hint_popup.hide_hint()
            return
        sig, active = data
        from ui.widgets.code_editor.completion.parameter_hint import format_signature_rich

        html_sig = format_signature_rich(sig, active)
        cr = self.cursorRect()
        gp = self.mapToGlobal(cr.topLeft())
        self._parameter_hint_popup.show_hint(gp, html_sig, cr.height())

    def _refresh_parameter_hint_from_cursor(self) -> None:
        """Recompute the hint when the cursor moves while the hint is visible."""
        if self._parameter_hint_popup.isVisible():
            self._try_show_parameter_hint()

    def _dismiss_parameter_hint(self) -> None:
        """Hide the parameter hint popup."""
        self._parameter_hint_popup.hide_hint()

    def _on_cursor_moved_parameter_hint(self) -> None:
        """Cursor moved: refresh active parameter when the hint is open."""
        if self._parameter_hint_popup.isVisible():
            self._refresh_parameter_hint_from_cursor()
