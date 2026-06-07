"""Unit tests for thought expand/collapse row height updates."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

from ui.sidebar.ai.message_bubble import ChatMessageBubble


def _thought_toggle(bubble: ChatMessageBubble) -> QPushButton:
    """Return the thought section toggle button on *bubble*."""
    assert bubble._thought_section is not None
    toggle = bubble._thought_section.findChild(QPushButton, "aiChatThoughtToggle")
    assert toggle is not None
    return toggle


def test_thought_collapse_shrinks_row_immediately(qapp: QApplication, qtbot) -> None:
    """Collapsing thought text shrinks the assistant row without a delayed relayout."""
    host = QWidget()
    layout = QVBoxLayout(host)
    thinking = "internal reasoning line\n" * 8
    bubble = ChatMessageBubble(
        "assistant",
        "Answer body",
        thinking=thinking,
        thinking_duration_seconds=4,
    )
    layout.addWidget(bubble)
    qtbot.addWidget(host)
    host.resize(360, 480)
    host.show()
    qtbot.waitExposed(host)

    toggle = _thought_toggle(bubble)
    toggle.click()
    qapp.processEvents()
    expanded_h = bubble.sizeHint().height()
    assert bubble.is_thinking_expanded()

    toggle.click()
    qapp.processEvents()
    collapsed_h = bubble.sizeHint().height()
    assert not bubble.is_thinking_expanded()
    assert collapsed_h < expanded_h


def test_thought_collapse_emits_layout_height_changed(qapp: QApplication, qtbot) -> None:
    """Thought collapse notifies the transcript via one layout-height signal."""
    host = QWidget()
    layout = QVBoxLayout(host)
    bubble = ChatMessageBubble(
        "assistant",
        "Answer body",
        thinking="trace\n" * 6,
        thinking_duration_seconds=3,
    )
    layout.addWidget(bubble)
    qtbot.addWidget(host)
    host.resize(360, 480)
    host.show()
    qtbot.waitExposed(host)

    signals: list[object] = []
    bubble.layout_height_changed.connect(lambda: signals.append(object()))

    toggle = _thought_toggle(bubble)
    toggle.click()
    qapp.processEvents()
    toggle.click()
    qapp.processEvents()

    assert len(signals) == 2
