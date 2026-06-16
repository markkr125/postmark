"""Tests for inline message edit on :class:`AiChatPanel`."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble


def test_begin_inline_edit_keeps_docked_composer_visible(qapp: QApplication, qtbot) -> None:
    """Inline edit swaps the user bubble for a composer but leaves the dock visible."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(400, 600)
    panel.show()
    bubble = panel.add_message("user", "edit me", message_id=42)
    assert panel.begin_inline_edit(42) is True
    assert panel._inline_edit is not None
    assert panel._docked_composer.isVisible()
    assert panel._docked_composer.isEnabled()
    assert bubble.user_message_text() == "edit me"
    panel.end_inline_edit(restore_bubble=True)
    assert panel._inline_edit is None


def test_inline_edit_submit_emits_signal(qapp: QApplication, qtbot) -> None:
    """Submitting the inline composer emits ``user_edit_submitted``."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(400, 600)
    panel.show()
    panel.add_message("user", "old text", message_id=7)
    fired: list[tuple[int, str]] = []
    panel.user_edit_submitted.connect(lambda mid, text: fired.append((mid, text)))
    assert panel.begin_inline_edit(7) is True
    state = panel._inline_edit
    assert state is not None
    state.composer.restore_text("new text")
    panel._on_inline_edit_submit()
    assert fired == [(7, "new text")]
    panel.end_inline_edit(restore_bubble=True)


def test_truncate_transcript_after_removes_later_bubbles(qapp: QApplication, qtbot) -> None:
    """``truncate_transcript_after`` removes bubbles with higher message ids."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(400, 800)
    panel.show()
    panel.add_message("user", "one", message_id=1)
    panel.add_message("assistant", "a1", message_id=2)
    panel.add_message("user", "two", message_id=3)
    panel.add_message("assistant", "a2", message_id=4)
    panel.truncate_transcript_after(1)
    bubbles = panel.findChildren(ChatMessageBubble)
    ids = sorted(b.message_id for b in bubbles if b.message_id is not None)
    assert ids == [1]


def test_begin_inline_edit_scrolls_user_row_to_top(qapp: QApplication, qtbot) -> None:
    """Edit scrolls the target user bubble to the top after layout settles."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(400, 280)
    panel.show()
    qtbot.waitExposed(panel)
    panel.add_message("user", "first", message_id=1)
    panel.add_message("assistant", "reply\n" * 40, message_id=2)
    panel.add_message("user", "edit target", message_id=3)
    panel.add_message("assistant", "tail\n" * 40, message_id=4)
    panel._scroll_to_bottom(force=True)
    qtbot.wait(50)
    target = panel._bubble_by_message_id[3]
    assert panel.begin_inline_edit(3) is True
    qtbot.wait(50)
    bar = panel._scroll.verticalScrollBar()
    from PySide6.QtCore import QPoint

    anchor = target.user_message_host() or target
    y = anchor.mapTo(panel._messages, QPoint(0, 0)).y()
    expected = max(0, y - 8)
    assert abs(bar.value() - expected) <= 12
    panel.end_inline_edit(restore_bubble=True)

