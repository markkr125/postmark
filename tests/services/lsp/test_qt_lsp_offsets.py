"""Tests for UTF-16 position mapping used by LSP."""

from __future__ import annotations

from PySide6.QtGui import QTextDocument

from services.lsp.qt_lsp_offsets import lsp_to_qpos, qpos_to_lsp, utf16_len


def test_utf16_len_ascii_and_supplementary() -> None:
    """BMP vs supplementary-plane code points count UTF-16 code units."""
    assert utf16_len("abc") == 3
    assert utf16_len("\U0001f600") == 2


def test_qpos_to_lsp_round_trip_ascii() -> None:
    """ASCII lines round-trip through qpos ↔ lsp."""
    doc = QTextDocument("hello\nworld")
    for pos in (0, 3, 5, 6, 10):
        line, col = qpos_to_lsp(doc, pos)
        assert lsp_to_qpos(doc, line, col) == pos


def test_qpos_to_lsp_supplementary_plane() -> None:
    """A surrogate pair occupies two UTF-16 columns for LSP."""
    s = "a\U0001f600b"
    doc = QTextDocument(s)
    # Position after emoji (3 QString chars: a, emoji, b)
    pos_after_emoji = 2
    line, col = qpos_to_lsp(doc, pos_after_emoji)
    assert line == 0
    assert col == 3  # 'a' (1) + emoji (2 UTF-16 units)
    assert lsp_to_qpos(doc, line, col) == pos_after_emoji
