"""Tests for user message actions popup."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPushButton

from ui.sidebar.ai.message_bubble.user_message.actions_popup import AiUserMessageActionsPopup


def test_actions_popup_fork_callback_runs(qapp: QApplication) -> None:
    """Fork row invokes the callback supplied when the popup opens."""
    popup = AiUserMessageActionsPopup.instance()
    anchor = QPushButton()
    anchor.show()
    fired: list[str] = []
    popup.show_for(anchor, on_fork=lambda: fired.append("fork"))
    popup._on_fork()
    popup.hide_popup()
    assert fired == ["fork"]


def test_actions_popup_edit_callback_runs(qapp: QApplication) -> None:
    """Edit row invokes the callback supplied when the popup opens."""
    popup = AiUserMessageActionsPopup.instance()
    anchor = QPushButton()
    anchor.show()
    fired: list[str] = []
    popup.show_for(anchor, on_edit=lambda: fired.append("edit"))
    popup._on_edit()
    popup.hide_popup()
    assert fired == ["edit"]


def test_actions_popup_follows_transcript_scroll(qapp: QApplication, qtbot) -> None:
    """The flyout repositions when the transcript scrolls instead of staying fixed."""
    from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

    scroll = QScrollArea()
    scroll.setObjectName("aiChatScroll")
    scroll.setWidgetResizable(True)
    host = QWidget()
    host.setMinimumHeight(1200)
    layout = QVBoxLayout(host)
    layout.addStretch(1)
    anchor = QPushButton("anchor")
    layout.addWidget(anchor)
    layout.addStretch(1)
    scroll.setWidget(host)
    qtbot.addWidget(scroll)
    scroll.resize(320, 180)
    scroll.show()
    qtbot.waitExposed(scroll)

    popup = AiUserMessageActionsPopup.instance()
    popup.show_for(anchor)
    global_before = popup.frameGeometry().topLeft()

    bar = scroll.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum() // 2)
    assert popup.isVisible()
    qtbot.waitUntil(
        lambda: popup.frameGeometry().topLeft() != global_before,
        timeout=2000,
    )


def test_actions_popup_coalesces_scroll_reposition(qapp: QApplication, qtbot) -> None:
    """Burst scrollbar signals schedule at most one reposition per event-loop tick."""
    anchor = QPushButton("anchor")
    anchor.show()
    popup = AiUserMessageActionsPopup.instance()
    moves: list[object] = []
    popup.move = lambda *args, **kwargs: moves.append(args)  # type: ignore[method-assign, assignment]
    popup.show_for(anchor)
    qtbot.wait(50)
    moves.clear()
    for _ in range(8):
        popup._sync_popup_position_to_anchor()
    qtbot.wait(50)
    assert len(moves) == 1
    popup.hide_popup()
