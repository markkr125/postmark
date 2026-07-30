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


def test_inline_edit_lifts_attachment_trailer_into_chips(qapp: QApplication, qtbot) -> None:
    """Edit must not dump the Attached files trailer into the compact text field.

    Regression: the full composed prompt (including long ``postmark://`` URI lines)
    was restored into the inline input, where it overlapped Agent / Cancel / Send
    and looked mangled. The body stays in the editor; attachments become chips.
    """
    from PySide6.QtWidgets import QPushButton

    prompt = (
        "Turn this pdf into a collection please\n\n"
        "Attached files:\n"
        "- Agoda Standard Pull Spec v1.34 (5) (1).pdf -> "
        "postmark://uploaded/Agoda_Standard_Pull_Spec_v1.34_5_1.md"
    )
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(420, 600)
    panel.show()
    panel.add_message("user", prompt, message_id=11)
    assert panel.begin_inline_edit(11) is True
    state = panel._inline_edit
    assert state is not None
    composer = state.composer

    assert composer.plain_text() == "Turn this pdf into a collection please"
    assert "postmark://" not in composer.input_widget().toPlainText()
    assert "Attached files:" not in composer.input_widget().toPlainText()

    chips = composer.findChildren(QPushButton, "aiChatAttachmentChip")
    assert len(chips) == 1
    assert chips[0].text().startswith("Agoda")
    assert "postmark://uploaded/Agoda_Standard_Pull_Spec_v1.34_5_1.md" in chips[0].toolTip()
    assert not composer._attachments_row.isHidden()

    fired: list[tuple[int, str]] = []
    panel.user_edit_submitted.connect(lambda mid, text: fired.append((mid, text)))
    panel._on_inline_edit_submit()
    assert len(fired) == 1
    assert fired[0][0] == 11
    assert "Turn this pdf into a collection please" in fired[0][1]
    assert "postmark://uploaded/Agoda_Standard_Pull_Spec_v1.34_5_1.md" in fired[0][1]
    panel.end_inline_edit(restore_bubble=True)


def test_inline_edit_grows_with_newlines_and_keeps_cancel_visible(
    qapp: QApplication, qtbot
) -> None:
    """Inline edit must expand the user row like the docked composer.

    Regression: the bubble stayed clamped to the read-only label height, so
    Shift+Enter lines were clipped inside the fixed frame and Cancel's bottom
    edge was cut off by ``aiChatMessageUser``.
    """
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QPushButton

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(420, 700)
    panel.show()
    qtbot.waitExposed(panel)
    prompt = (
        "Turn this pdf into a collection please\n\n"
        "Attached files:\n"
        "- Agoda Standard Pull Spec v1.34 (5) (1).pdf -> "
        "postmark://uploaded/Agoda_Standard_Pull_Spec_v1.34_5_1.md"
    )
    bubble = panel.add_message("user", prompt, message_id=21)
    qapp.processEvents()
    assert panel.begin_inline_edit(21) is True
    state = panel._inline_edit
    assert state is not None
    composer = state.composer
    cancel = composer.findChild(QPushButton, "aiChatEditCancel")
    assert cancel is not None and cancel.isVisible()

    def _cancel_fully_visible() -> bool:
        top_left = cancel.mapTo(bubble, QPoint(0, 0))
        bottom_right = cancel.mapTo(bubble, QPoint(cancel.width(), cancel.height()))
        cancel_rect = QRect(top_left, bottom_right)
        bubble_rect = QRect(0, 0, bubble.width(), bubble.height())
        return cancel_rect.intersected(bubble_rect) == cancel_rect

    qapp.processEvents()
    assert bubble._inline_composer is composer
    assert bubble.height() >= composer.sizeHint().height()
    assert _cancel_fully_visible()

    inp = composer.input_widget()
    initial_input_h = inp.height()
    initial_bubble_h = bubble.height()
    inp.setPlainText("\n".join(f"line {i}" for i in range(8)))
    qapp.processEvents()
    panel._on_inline_edit_composer_layout_changed()
    qapp.processEvents()

    assert inp.height() > initial_input_h
    assert bubble.height() > initial_bubble_h
    assert composer.height() >= inp.height()
    assert _cancel_fully_visible()
    panel.end_inline_edit(restore_bubble=True)
