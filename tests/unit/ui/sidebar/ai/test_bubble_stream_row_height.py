"""Unit tests for assistant bubble row height during streaming."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ui.sidebar.ai.message_bubble import ChatMessageBubble


def test_bubble_row_height_monotonic_when_activity_hides(qapp: QApplication, qtbot) -> None:
    """Hiding the activity row does not shrink the streaming row floor."""
    host = QWidget()
    layout = QVBoxLayout(host)
    bubble = ChatMessageBubble("assistant", "")
    layout.addWidget(bubble)
    qtbot.addWidget(host)
    host.resize(320, 240)
    host.show()
    qtbot.waitExposed(host)

    bubble.begin_streaming()
    bubble.show_activity("Thinking…")
    qapp.processEvents()
    floor_with_activity = bubble.minimumHeight()

    bubble.hide_activity()
    bubble._commit_stream_row_layout()
    assert bubble.minimumHeight() >= floor_with_activity


def test_deferred_stream_flush_emits_one_layout_height_signal(qapp: QApplication, qtbot) -> None:
    """Batched stream layout emits one layout-height notification per flush."""
    host = QWidget()
    layout = QVBoxLayout(host)
    bubble = ChatMessageBubble("assistant", "")
    layout.addWidget(bubble)
    qtbot.addWidget(host)
    host.resize(320, 240)
    host.show()
    qtbot.waitExposed(host)

    signals: list[object] = []
    bubble.layout_height_changed.connect(lambda: signals.append(object()))

    bubble.begin_streaming()
    bubble.set_defer_layout_height_changed(True)
    if bubble._markdown_body is not None:
        bubble._markdown_body.set_defer_height_changed(True)
    bubble.append_content("line one\n", defer_geometry=True)
    bubble.append_content("line two\n", defer_geometry=True)
    bubble.set_defer_layout_height_changed(False)

    assert len(signals) == 1
