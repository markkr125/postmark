"""Map between QTextDocument UTF-16 offsets and LSP line/character."""

from __future__ import annotations

from PySide6.QtGui import QTextDocument


def utf16_len(s: str) -> int:
    """Return UTF-16 code-unit length of *s* (PySide6 document positions)."""
    n = 0
    for ch in s:
        code = ord(ch)
        n += 2 if code > 0xFFFF else 1
    return n


def qpos_to_lsp(document: QTextDocument, position: int) -> tuple[int, int]:
    """Map a QTextDocument character offset to ``(line, column_utf16)``."""
    if position < 0:
        position = 0
    max_pos = document.characterCount()
    if position > max_pos:
        position = max_pos
    block = document.findBlock(position)
    if not block.isValid():
        return (0, 0)
    line = block.blockNumber()
    col_pos = position - block.position()
    prefix = block.text()[:col_pos]
    col_utf16 = utf16_len(prefix)
    return (line, col_utf16)


def lsp_to_qpos(document: QTextDocument, line: int, column_utf16: int) -> int:
    """Inverse of :func:`qpos_to_lsp`."""
    block = document.findBlockByNumber(line)
    if not block.isValid():
        return max(0, document.characterCount() - 1)
    text = block.text()
    acc = 0
    col_chars = 0
    for ch in text:
        u16 = 2 if ord(ch) > 0xFFFF else 1
        if acc + u16 > column_utf16:
            break
        acc += u16
        col_chars += 1
    return block.position() + col_chars
