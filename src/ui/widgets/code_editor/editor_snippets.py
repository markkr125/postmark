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
    _snippet_collection_id: int | None
    _snippet_local_script_id: int | None

    def set_snippet_capture_context(
        self,
        *,
        script_type: str | None = None,
        collection_id: int | None = None,
        local_script_id: int | None = None,
    ) -> None:
        r"""Configure scope for the script editor "Save as snippet…" action."""
        self._snippet_script_type = script_type
        self._snippet_collection_id = collection_id
        self._snippet_local_script_id = local_script_id

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
            collection_id=self._snippet_collection_id,
            local_script_id=self._snippet_local_script_id,
            parent=self.window(),
        )
        from PySide6.QtWidgets import QDialog

        if dlg.exec() == int(QDialog.DialogCode.Accepted) and dlg.saved_snippet_id is not None:
            from ui.widgets.snippets.loader import invalidate_snippet_cache

            invalidate_snippet_cache()
