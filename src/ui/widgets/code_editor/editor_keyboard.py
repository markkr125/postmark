"""Keyboard handling mixin for :class:`CodeEditorWidget`."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFocusEvent, QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication

from ui.widgets.code_editor.gutter import _AUTO_CLOSE_PAIRS, _CLOSE_TO_OPEN

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPlainTextEdit

    from ui.widgets.code_editor.completion.engine import CompletionEngine
    from ui.widgets.code_editor.completion.parameter_hint import ParameterHintPopup
    from ui.widgets.code_editor.completion.popup import CompletionPopup
    from ui.widgets.code_editor.completion.symbol_doc_popup import SymbolDocPopup
    from ui.widgets.code_editor.debug_hover_popup import DebugValuePopup

    _KeyboardBase = QPlainTextEdit
else:
    _KeyboardBase = object


def _is_quick_doc_shortcut(event: QKeyEvent) -> bool:
    """Return True for Ctrl+Q (do not bind macOS Cmd+Q — that is OS quit)."""
    if event.key() != Qt.Key.Key_Q:
        return False
    chord = (
        Qt.KeyboardModifier.ShiftModifier
        | Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.MetaModifier
    )
    masked = event.modifiers() & chord
    return masked == Qt.KeyboardModifier.ControlModifier


def _is_parameter_hint_shortcut(event: QKeyEvent) -> bool:
    """Return True for Ctrl+P (Cmd+P on macOS), ignoring benign modifier bits.

    ``QKeyEvent.modifiers()`` may include ``GroupSwitchModifier`` or
    ``KeypadModifier`` alongside ``ControlModifier``; equality against
    ``ControlModifier`` alone then fails and the shortcut is never handled.
    """
    if event.key() != Qt.Key.Key_P:
        return False
    m = event.modifiers()
    if m & Qt.KeyboardModifier.AltModifier:
        return False
    chord = (
        Qt.KeyboardModifier.ShiftModifier
        | Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.MetaModifier
    )
    masked = m & chord
    if sys.platform == "darwin" and masked == Qt.KeyboardModifier.MetaModifier:
        return True
    return masked == Qt.KeyboardModifier.ControlModifier


class _KeyboardMixin(_KeyboardBase):
    """Tab/comment/bracket keys, auto-close pairs, and focus-out popup dismissal."""

    _language: str
    _read_only: bool
    _detected_indent: int
    _completion_engine: CompletionEngine

    if TYPE_CHECKING:

        @property
        def _completion_popup(self) -> CompletionPopup: ...
        @property
        def _parameter_hint_popup(self) -> ParameterHintPopup: ...
        @property
        def _symbol_doc_popup(self) -> SymbolDocPopup: ...
        @property
        def _debug_popup(self) -> DebugValuePopup: ...
        def _dismiss_parameter_hint(self) -> None: ...
        def _dismiss_symbol_doc(self) -> None: ...
        def _hide_debug_value_popup(self) -> None: ...
        def trigger_parameter_hint(self) -> None: ...
        def _trigger_completion(self) -> None: ...
        def _try_show_parameter_hint(self) -> None: ...
        def _maybe_trigger_local_path_completion(self) -> None: ...
        def _refresh_parameter_hint_from_cursor(self) -> None: ...
        def _text_before_cursor_document(self) -> str: ...
        def _completion_text_before_cursor(self) -> str: ...
        def _in_path_string_context(self, text_before: str) -> bool: ...
        def _filter_completion(self) -> None: ...
        def _activate_quick_doc(self) -> Any: ...

    @staticmethod
    def _indent_selection(cursor: QTextCursor, indent_width: int) -> None:
        """Prepend *indent_width* spaces to every line touched by *cursor*."""
        indent = " " * indent_width
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        cursor.beginEditBlock()

        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        first_block = cursor.blockNumber()

        cursor.setPosition(end, QTextCursor.MoveMode.MoveAnchor)
        if cursor.positionInBlock() == 0 and cursor.blockNumber() > first_block:
            cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
        last_block = cursor.blockNumber()

        blk = cursor.document().findBlockByNumber(first_block)
        while blk.isValid() and blk.blockNumber() <= last_block:
            cursor.setPosition(blk.position())
            cursor.insertText(indent)
            blk = blk.next()

        cursor.endEditBlock()

        new_start = cursor.document().findBlockByNumber(first_block).position()
        end_block = cursor.document().findBlockByNumber(last_block)
        new_end = end_block.position() + len(end_block.text())
        cursor.setPosition(new_start)
        cursor.setPosition(new_end, QTextCursor.MoveMode.KeepAnchor)

    @staticmethod
    def _outdent_selection(cursor: QTextCursor, indent_width: int) -> None:
        """Remove up to *indent_width* leading spaces from every selected line."""
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        cursor.beginEditBlock()

        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        first_block = cursor.blockNumber()

        cursor.setPosition(end, QTextCursor.MoveMode.MoveAnchor)
        if cursor.positionInBlock() == 0 and cursor.blockNumber() > first_block:
            cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
        last_block = cursor.blockNumber()

        blk = cursor.document().findBlockByNumber(first_block)
        while blk.isValid() and blk.blockNumber() <= last_block:
            txt = blk.text()
            leading = len(txt) - len(txt.lstrip(" "))
            remove = min(indent_width, leading)
            if remove > 0:
                cursor.setPosition(blk.position())
                for _ in range(remove):
                    cursor.deleteChar()
            blk = blk.next()

        cursor.endEditBlock()

        new_start = cursor.document().findBlockByNumber(first_block).position()
        end_block = cursor.document().findBlockByNumber(last_block)
        new_end = end_block.position() + len(end_block.text())
        cursor.setPosition(new_start)
        cursor.setPosition(new_end, QTextCursor.MoveMode.KeepAnchor)

    def _line_comment_token(self) -> str:
        """Return the line-comment marker for the current language."""
        lang = self._language
        if lang in ("python",):
            return "#"
        return "//"

    def _toggle_line_comment(self) -> None:
        """Toggle line-comment marker on the selected lines (or current line).

        Comments out every selected line if any line is uncommented;
        otherwise removes the marker from each. Indent of the marker
        matches the smallest leading-whitespace of the affected lines.
        """
        token = self._line_comment_token()
        prefix = token + " "
        cursor = self.textCursor()
        doc = self.document()

        if cursor.hasSelection():
            start = min(cursor.selectionStart(), cursor.selectionEnd())
            end = max(cursor.selectionStart(), cursor.selectionEnd())
        else:
            start = cursor.position()
            end = cursor.position()

        first_block = doc.findBlock(start).blockNumber()
        last_block_blk = doc.findBlock(end)
        # If selection ends right at start of a block, exclude that block.
        if (
            cursor.hasSelection()
            and last_block_blk.position() == end
            and last_block_blk.blockNumber() > first_block
        ):
            last_block = last_block_blk.blockNumber() - 1
        else:
            last_block = last_block_blk.blockNumber()

        # Pass 1: decide add vs remove. Add if any non-blank line lacks the marker.
        any_uncommented = False
        min_indent = None
        for bn in range(first_block, last_block + 1):
            blk = doc.findBlockByNumber(bn)
            text = blk.text()
            stripped = text.lstrip()
            if not stripped:
                continue
            indent = len(text) - len(stripped)
            min_indent = indent if min_indent is None else min(min_indent, indent)
            if not stripped.startswith(token):
                any_uncommented = True
        if min_indent is None:
            min_indent = 0

        cursor.beginEditBlock()
        for bn in range(first_block, last_block + 1):
            blk = doc.findBlockByNumber(bn)
            text = blk.text()
            stripped = text.lstrip()
            if not stripped:
                continue
            block_pos = blk.position()
            indent = len(text) - len(stripped)
            if any_uncommented:
                # Insert marker at the shared indent column.
                col = min(min_indent, indent)
                ins_cursor = QTextCursor(doc)
                ins_cursor.setPosition(block_pos + col)
                ins_cursor.insertText(prefix)
            else:
                # Remove marker (and one optional trailing space) from this line.
                idx = text.find(token)
                if idx == -1:
                    continue
                rm_len = len(token)
                if text[idx + rm_len : idx + rm_len + 1] == " ":
                    rm_len += 1
                rm_cursor = QTextCursor(doc)
                rm_cursor.setPosition(block_pos + idx)
                rm_cursor.setPosition(block_pos + idx + rm_len, QTextCursor.MoveMode.KeepAnchor)
                rm_cursor.removeSelectedText()
        cursor.endEditBlock()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle Tab-to-spaces, auto-closing brackets, and completions."""
        if event.key() == Qt.Key.Key_Escape:
            if self._completion_popup.is_active():
                self._completion_popup.dismiss()
                event.accept()
                return
            if self._parameter_hint_popup.isVisible():
                self._dismiss_parameter_hint()
                event.accept()
                return
            if self._symbol_doc_popup.isVisible():
                self._dismiss_symbol_doc()
                event.accept()
                return
            if self._debug_popup.isVisible():
                self._hide_debug_value_popup()
                event.accept()
                return

        # Ctrl+P / Cmd+P — parameter info (before read-only branch so hints work everywhere)
        if _is_parameter_hint_shortcut(event):
            self.trigger_parameter_hint()
            event.accept()
            return

        # Ctrl+Q — quick doc (layout-independent binding lives on QShortcut too).
        if _is_quick_doc_shortcut(event):
            activate = getattr(self, "_activate_quick_doc", None)
            if callable(activate):
                activate()
            event.accept()
            return

        if self._read_only:
            super().keyPressEvent(event)
            return

        # Ctrl+/ — line comment is handled by QShortcut (layout-independent).

        # Shift+Enter / Shift+Return — insert a normal newline (paragraph break).
        # Qt's default would insert U+2028 line-separator instead, which round-trips
        # poorly through save/load and some highlighters.
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() == Qt.KeyboardModifier.ShiftModifier
            and not self._completion_popup.is_active()
        ):
            self.textCursor().insertText("\n")
            return

        # -- Completion popup navigation (when active) --
        if self._completion_popup.is_active():
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                self._completion_popup.accept_current()
                return
            if key == Qt.Key.Key_Down:
                self._completion_popup.select_next()
                return
            if key == Qt.Key.Key_Up:
                self._completion_popup.select_previous()
                return

        # Ctrl+Space — manual completion trigger
        if (
            event.key() == Qt.Key.Key_Space
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self._trigger_completion()
            return

        iw = self._detected_indent

        # Tab — block indent or insert spaces
        if event.key() == Qt.Key.Key_Tab and not event.modifiers():
            cursor = self.textCursor()
            if cursor.hasSelection():
                self._indent_selection(cursor, iw)
            else:
                cursor.insertText(" " * iw)
            return

        # Shift+Tab — block outdent
        if event.key() == Qt.Key.Key_Backtab:
            cursor = self.textCursor()
            if cursor.hasSelection():
                self._outdent_selection(cursor, iw)
            else:
                block_text = cursor.block().text()
                leading = len(block_text) - len(block_text.lstrip(" "))
                remove = min(iw, leading)
                if remove > 0:
                    cursor.movePosition(
                        QTextCursor.MoveOperation.StartOfBlock,
                        QTextCursor.MoveMode.MoveAnchor,
                    )
                    for _ in range(remove):
                        cursor.deleteChar()
                    self.setTextCursor(cursor)
            return

        text = event.text()
        cursor = self.textCursor()

        # Auto-close pairs
        if text in _AUTO_CLOSE_PAIRS:
            closing = _AUTO_CLOSE_PAIRS[text]

            block_text = cursor.block().text()
            pos_in_block = cursor.positionInBlock()
            if text == closing and pos_in_block < len(block_text):
                next_char = block_text[pos_in_block]
                if next_char == closing:
                    cursor.movePosition(
                        QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor
                    )
                    self.setTextCursor(cursor)
                    return

            if cursor.hasSelection():
                selected = cursor.selectedText()
                cursor.insertText(text + selected + closing)
            else:
                cursor.insertText(text + closing)
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor)
                self.setTextCursor(cursor)
                if text == "(":
                    self._try_show_parameter_hint()
                self._maybe_trigger_local_path_completion()
            return

        # Skip over closing bracket
        if text in _CLOSE_TO_OPEN or text in (")", "]", "}"):
            block_text = cursor.block().text()
            pos_in_block = cursor.positionInBlock()
            if pos_in_block < len(block_text) and block_text[pos_in_block] == text:
                cursor.movePosition(
                    QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor
                )
                self.setTextCursor(cursor)
                return

        super().keyPressEvent(event)

        # -- Post-insert completion triggers --
        if text == "," and self._parameter_hint_popup.isVisible():
            self._refresh_parameter_hint_from_cursor()
        elif text == ")":
            if (
                self._completion_engine.resolve_call_signature(self._text_before_cursor_document())
                is None
            ):
                self._dismiss_parameter_hint()
            else:
                self._refresh_parameter_hint_from_cursor()
        if text and text.isprintable():
            self._maybe_trigger_local_path_completion()
        if text == "." and not self._in_path_string_context(self._completion_text_before_cursor()):
            self._trigger_completion()
        elif text == "{":
            block_text = self.textCursor().block().text()
            col = self.textCursor().positionInBlock()
            if col >= 2 and block_text[col - 2 : col] == "{{":
                self._trigger_completion()
        elif self._completion_popup.is_active():
            self._filter_completion()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        """Hide the parameter hint only when focus genuinely leaves our window.

        Showing a ``Qt.Tool`` popup briefly shifts the active window on Linux,
        which would otherwise dismiss the hint immediately.
        """
        reason = event.reason()
        new_active = QApplication.activeWindow()
        same_window = new_active is not None and (
            new_active is self.window()
            or new_active is self._parameter_hint_popup
            or new_active is self._symbol_doc_popup
        )
        transient = reason in (
            Qt.FocusReason.PopupFocusReason,
            Qt.FocusReason.ActiveWindowFocusReason,
        )
        if not (same_window or transient):
            self._dismiss_parameter_hint()
            self._dismiss_symbol_doc()
        super().focusOutEvent(event)
