"""Read-only code snippet for the breakpoints dialog."""

from __future__ import annotations

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QVBoxLayout, QWidget

from ui.widgets.code_editor import CodeEditorWidget

_PREVIEW_CONTEXT_LINES = 8


class BreakpointCodePreview(QWidget):
    """Syntax-highlighted excerpt around the selected breakpoint line."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build a read-only editor showing a window of source lines."""
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._editor = CodeEditorWidget(read_only=True, parent=self)
        self._editor.setObjectName("breakpointsDialogPreview")
        self._editor.set_breakpoint_gutter_visible(True)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self._editor, 1)

        self._source_line: int | None = None

    def show_excerpt(
        self,
        *,
        full_text: str,
        language: str,
        source_line: int,
    ) -> None:
        """Display lines around *source_line* (0-based) from *full_text*."""
        self._source_line = source_line
        self._editor.set_language(language)

        lines = full_text.splitlines()
        if not lines:
            self._editor.setPlainText("")
            self._editor.setExtraSelections([])
            return

        start = max(0, source_line - _PREVIEW_CONTEXT_LINES)
        end = min(len(lines), source_line + _PREVIEW_CONTEXT_LINES + 1)
        excerpt_lines = lines[start:end]
        self._editor.setPlainText("\n".join(excerpt_lines))

        preview_line = source_line - start
        for ln in list(self._editor.breakpoints):
            self._editor.toggle_breakpoint(ln)
        if preview_line >= 0:
            self._editor.toggle_breakpoint(preview_line)

        p = self._editor._editor_palette()  # type: ignore[attr-defined]
        block = self._editor.document().findBlockByNumber(preview_line)
        if block.isValid():
            sel = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(p["editor_breakpoint_line"]))
            fmt.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
            cur = QTextCursor(block)
            cur.clearSelection()
            sel.cursor = cur
            sel.format = fmt
            self._editor.setExtraSelections([sel])

        cursor = self._editor.textCursor()
        cursor.setPosition(block.position())
        self._editor.setTextCursor(cursor)
        self._editor.centerCursor()
