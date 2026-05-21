"""Identifier and variable resolution mixin for :class:`CodeEditorWidget`."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint
from PySide6.QtGui import QTextCursor

from ui.widgets.code_editor.gutter import _VAR_RE

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPlainTextEdit

    _IdentBase = QPlainTextEdit
else:
    _IdentBase = object


class _IdentMixin(_IdentBase):
    """Resolve dot-path identifiers and ``{{var}}`` / debug names at a position."""

    _debug_locals: dict[str, Any]
    _debug_root_values: dict[str, Any]

    def _ident_at_pos(self, pos: QPoint) -> tuple[str, int, int] | None:
        """Return ``(dot_path, start_doc_pos, end_doc_pos)`` for an identifier.

        Resolves the JS/Python identifier under viewport position *pos*,
        walking left over ``.`` joins.  Returns ``None`` when the position is
        not on an identifier or is inside a string literal.
        """
        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        block_text = block.text()
        col = cursor.positionInBlock()
        if col > 0 and col >= len(block_text):
            col = len(block_text) - 1
        if col < 0 or col >= len(block_text):
            return None
        if not (block_text[col].isalnum() or block_text[col] in "_$."):
            return None
        # Walk right to end of identifier run.
        end = col
        while end < len(block_text) and (block_text[end].isalnum() or block_text[end] in "_$"):
            end += 1
        # Walk left over identifier + dot chains.
        start = col
        while start > 0 and (
            block_text[start - 1].isalnum()
            or block_text[start - 1] in "_$"
            or (
                block_text[start - 1] == "."
                and start - 2 >= 0
                and (block_text[start - 2].isalnum() or block_text[start - 2] in "_$")
            )
        ):
            start -= 1
        token = block_text[start:end]
        if not token or token[0].isdigit():
            return None
        # Reject when inside a string literal. Track template-literal
        # interpolation (`${ ... }`) so identifiers inside `${expr}` are
        # treated as code, not string content.
        prefix = block_text[:start]
        state = "code"  # code | sq | dq | tpl | tpl_expr
        expr_depth = 0
        i = 0
        while i < len(prefix):
            ch = prefix[i]
            if state in ("sq", "dq", "tpl") and ch == "\\":
                i += 2
                continue
            if state == "code":
                if ch == "'":
                    state = "sq"
                elif ch == '"':
                    state = "dq"
                elif ch == "`":
                    state = "tpl"
            elif state == "sq":
                if ch == "'":
                    state = "code"
            elif state == "dq":
                if ch == '"':
                    state = "code"
            elif state == "tpl":
                if ch == "`":
                    state = "code"
                elif ch == "$" and i + 1 < len(prefix) and prefix[i + 1] == "{":
                    state = "tpl_expr"
                    expr_depth = 1
                    i += 2
                    continue
            else:  # tpl_expr — JS code inside `${...}`
                if ch == "{":
                    expr_depth += 1
                elif ch == "}":
                    expr_depth -= 1
                    if expr_depth == 0:
                        state = "tpl"
                elif ch in ("'", '"'):
                    end_q = prefix.find(ch, i + 1)
                    if end_q == -1:
                        return None
                    i = end_q + 1
                    continue
            i += 1
        if state in ("sq", "dq", "tpl"):
            return None
        if not re.match(r"[A-Za-z_$][\w$.]*", token):
            return None
        # Segment range = only the identifier segment directly under the cursor,
        # so Ctrl+hover underlines just `set` in `pm.variables.set`.
        seg_start = col
        while seg_start > 0 and (
            block_text[seg_start - 1].isalnum() or block_text[seg_start - 1] in "_$"
        ):
            seg_start -= 1
        return token, block.position() + seg_start, block.position() + end

    def _ident_at_text_cursor(self) -> tuple[str, int, int] | None:
        """Same as :meth:`_ident_at_pos` but driven by the current text cursor."""
        return self._ident_at_pos(self.cursorRect().center())

    def _var_at_cursor(self, pos: QPoint) -> str | None:
        """Return ``{{name}}`` or a debug identifier at *pos*, or ``None``."""
        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        block_text = block.text()
        if "{{" in block_text:
            pos_in_block = cursor.positionInBlock()
            for match in _VAR_RE.finditer(block_text):
                if match.start() <= pos_in_block <= match.end():
                    return match.group(1)
        if self._debug_locals or self._debug_root_values:
            cur = self.cursorForPosition(pos)
            cur.select(QTextCursor.SelectionType.WordUnderCursor)
            word = cur.selectedText()
            if (
                word
                and re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", word)
                and (word in self._debug_locals or word in self._debug_root_values)
            ):
                return word
        return None
