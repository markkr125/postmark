"""Completion mixin for the code editor.

Provides ``_CompletionMixin`` containing trigger, filter, accept, and
popup positioning logic.  Must be combined with ``QPlainTextEdit`` via
``CodeEditorWidget``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QMouseEvent, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

if TYPE_CHECKING:
    from ui.widgets.code_editor.completion.engine import CompletionEngine
    from ui.widgets.code_editor.completion.popup import CompletionPopup

    _CompletionBase = QPlainTextEdit
else:
    _CompletionBase = object


class _CompletionMixin(_CompletionBase):
    """Mixin providing code completion trigger, filter, and accept logic."""

    # -- Attribute stubs (set by CodeEditorWidget.__init__) -------------
    _completion_popup: CompletionPopup
    _completion_engine: CompletionEngine
    _completion_prefix: str

    if TYPE_CHECKING:

        def toggle_fold(self, line: int) -> None: ...

    _fold_badge_rects: dict[int, QRect]
    _var_hover_name: str | None
    _var_hover_global_pos: QPoint
    _var_hover_timer: QTimer

    # -- Completion methods ---------------------------------------------

    def _trigger_completion(self) -> None:
        """Compute and show completions at the current cursor position."""
        self._completion_engine.scan_assignments(self.toPlainText())
        cursor = self.textCursor()
        block_text = cursor.block().text()
        col = cursor.positionInBlock()
        text_before = block_text[:col]

        items = self._completion_engine.complete(text_before)
        if not items:
            items = self._completion_engine.top_level_completions()
        if not items:
            self._completion_popup.dismiss()
            return

        self._completion_prefix = ""
        self._completion_popup.set_items(items)
        self._position_completion_popup()
        self._completion_popup.show()

    def _filter_completion(self) -> None:
        """Re-filter the completion list as the user types."""
        cursor = self.textCursor()
        block_text = cursor.block().text()
        col = cursor.positionInBlock()
        text_before = block_text[:col]

        items = self._completion_engine.complete(text_before)
        if not items:
            self._completion_popup.dismiss()
            return
        self._completion_popup.set_items(items)

    def _position_completion_popup(self) -> None:
        """Place the popup below the current cursor position."""
        cursor_rect = self.cursorRect()
        global_pos = self.mapToGlobal(cursor_rect.bottomLeft())
        self._completion_popup.move(global_pos)

    def _accept_completion(self, insert_text: str, kind: str) -> None:
        """Insert the accepted completion text at the cursor."""
        cursor = self.textCursor()

        block_text = cursor.block().text()
        col = cursor.positionInBlock()
        text_before = block_text[:col]

        # Find how many chars of the completion are already typed.
        prefix_len = 0
        for i in range(min(len(insert_text), col), 0, -1):
            candidate = text_before[col - i :]
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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Expand a collapsed fold when its ``...`` badge is clicked."""
        if self._completion_popup.is_active():
            self._completion_popup.dismiss()
        if event.button() == Qt.MouseButton.LeftButton and self._fold_badge_rects:
            pos = event.position().toPoint()
            for start_line, rect in self._fold_badge_rects.items():
                if rect.contains(pos):  # type: ignore[arg-type]
                    self.toggle_fold(start_line)
                    return
        super().mousePressEvent(event)

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

        # 2. Variable hover tracking.
        var_name = self._var_at_cursor(pos)  # type: ignore[attr-defined]
        if var_name:
            if var_name != self._var_hover_name:
                self._var_hover_name = var_name
                self._var_hover_global_pos = event.globalPosition().toPoint()
                from ui.widgets.variable_popup import VariablePopup

                self._var_hover_timer.start(VariablePopup.hover_delay_ms())  # type: ignore[union-attr]
        else:
            if self._var_hover_name is not None:
                self._var_hover_name = None
                self._var_hover_timer.stop()  # type: ignore[union-attr]

        super().mouseMoveEvent(event)
