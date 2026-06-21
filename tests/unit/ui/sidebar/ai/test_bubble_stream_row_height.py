"""Unit tests for assistant bubble row height during streaming."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ui.sidebar.ai.message_bubble import ChatMessageBubble


def test_thought_collapse_does_not_pin_row_minimum_height(qapp: QApplication, qtbot) -> None:
    """Collapsing thought at answer start does not pin a monotonic row minimum."""
    host = QWidget()
    layout = QVBoxLayout(host)
    bubble = ChatMessageBubble("assistant", "")
    layout.addWidget(bubble)
    qtbot.addWidget(host)
    host.resize(320, 240)
    host.show()
    qtbot.waitExposed(host)

    bubble.begin_streaming()
    bubble.append_thinking("thinking line\n" * 8)
    qapp.processEvents()
    bubble.append_content("answer line\n")
    qapp.processEvents()
    assert bubble.minimumHeight() == 0


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
