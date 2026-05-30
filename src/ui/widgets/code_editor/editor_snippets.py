"""Snippet capture context menu helpers for :class:`~editor_widget.CodeEditorWidget`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMenu

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPlainTextEdit

    _SnippetBase = QPlainTextEdit
else:
    _SnippetBase = object


class _SnippetMixin(_SnippetBase):
    """Mixin providing Save as snippet… context-menu integration."""

    _snippet_script_type: str | None
    _read_only: bool

    if TYPE_CHECKING:

        @property
        def language(self) -> str: ...

    def set_snippet_capture_context(self, *, script_type: str | None = None) -> None:
        r"""Configure the script editor "Save as snippet…" action."""
        self._snippet_script_type = script_type

    def _add_snippet_menu_action(self, menu: QMenu) -> None:
        """Append Save as snippet… when selection and capture context allow it."""
        selected = self.textCursor().selectedText()
        if (
            self._snippet_script_type
            and selected.strip()
            and not self._read_only
            and not self.isReadOnly()
        ):
            save_act = menu.addAction("Save as snippet…")
            save_act.triggered.connect(self._save_selection_as_snippet)

    def _save_selection_as_snippet(self) -> None:
        """Open :class:`~ui.widgets.snippets.snippet_capture_dialog.SnippetCaptureDialog`."""
        from ui.widgets.snippets.snippet_capture_dialog import SnippetCaptureDialog

        cursor = self.textCursor()
        body = cursor.selectedText().replace("\u2029", "\n")
        if not body.strip():
            return
        dlg = SnippetCaptureDialog(
            body=body,
            language=self.language,
            script_type=self._snippet_script_type or "pre_request",
            parent=self.window(),
        )
        from PySide6.QtWidgets import QDialog

        if dlg.exec() == int(QDialog.DialogCode.Accepted):
            win = self.window()
            if hasattr(win, "refresh_snippets_sidebar"):
                win.refresh_snippets_sidebar()  # type: ignore[attr-defined]
