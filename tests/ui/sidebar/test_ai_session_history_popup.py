"""Tests for the AI session history popover."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from services.ai.chat.session_service import AiChatSessionDict
from ui.sidebar.ai.chat_sessions.history_popup import AiSessionHistoryPopup
from ui.sidebar.ai.chat_sessions.time_format import format_relative_time


def _session(session_id: str, title: str) -> AiChatSessionDict:
    now = datetime.now(tz=UTC).isoformat()
    return AiChatSessionDict(
        id=session_id,
        title=title,
        model_id="m1",
        mode="agent",
        agent_id="postmark-assistant",
        created_at=now,
        updated_at=now,
        last_preview=None,
        archived=False,
    )


def test_format_relative_time_units() -> None:
    """Relative time helper formats common buckets."""
    now = datetime.now(tz=UTC)
    assert format_relative_time(now) == "now"
    assert format_relative_time(now - timedelta(minutes=5)) == "5m"
    assert format_relative_time(now - timedelta(hours=3)) == "3h"
    assert format_relative_time(now - timedelta(days=4)) == "4d"


def test_show_for_populates_rows(qapp: QApplication, qtbot) -> None:
    """``show_for`` fills the list with session rows."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    popup.show_for(anchor, [_session("a", "Alpha"), _session("b", "Beta")], lambda _id: None)
    assert popup._list.count() == 2


def test_search_filters_by_title(qapp: QApplication, qtbot) -> None:
    """Client-side search filters session titles."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    popup.show_for(
        anchor,
        [_session("a", "Python tips"), _session("b", "Other")],
        lambda _id: None,
    )
    popup._search.setText("python")
    qtbot.wait(50)
    assert popup._list.count() == 1


def test_active_session_row_is_highlighted(qapp: QApplication, qtbot) -> None:
    """The open chat session row is marked selected in the history list."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    popup.show_for(
        anchor,
        [_session("a", "Alpha"), _session("b", "Beta")],
        lambda _id: None,
        active_session_id="b",
    )
    active_row = popup._list.itemWidget(popup._list.item(1))
    inactive_row = popup._list.itemWidget(popup._list.item(0))
    assert active_row is not None
    assert inactive_row is not None
    assert active_row.property("activeSession") is True
    assert inactive_row.property("activeSession") is False
    assert popup._list.currentItem() is popup._list.item(1)


def test_row_click_calls_on_select(qapp: QApplication, qtbot) -> None:
    """Clicking a row invokes the select callback with the session id."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    selected: list[str] = []

    def on_select(session_id: str) -> None:
        selected.append(session_id)

    popup.show_for(anchor, [_session("sess-1", "One")], on_select)
    item = popup._list.item(0)
    assert item is not None
    popup._list.itemClicked.emit(item)
    assert selected == ["sess-1"]
    assert not popup.isVisible()


def test_escape_closes_popup(qapp: QApplication, qtbot) -> None:
    """Escape hides the popover."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    anchor.setCheckable(True)
    qtbot.addWidget(anchor)
    popup.show_for(anchor, [_session("a", "A")], lambda _id: None)
    assert anchor.isChecked()
    qtbot.keyClick(popup, Qt.Key.Key_Escape)
    assert not popup.isVisible()
    assert not anchor.isChecked()


def test_history_button_click_toggles_popup(qapp: QApplication, qtbot) -> None:
    """Clicking the anchor while open closes the popover instead of reopening it."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    anchor.setCheckable(True)
    qtbot.addWidget(anchor)

    def toggle_history() -> None:
        if popup.isVisible():
            popup.hide_popup()
        else:
            popup.show_for(anchor, [_session("a", "A")], lambda _id: None)

    anchor.clicked.connect(toggle_history)
    toggle_history()
    assert popup.isVisible()
    assert anchor.isChecked()
    qtbot.mouseClick(anchor, Qt.MouseButton.LeftButton)
    assert not popup.isVisible()
    assert not anchor.isChecked()


def test_outside_click_unchecks_anchor(qapp: QApplication, qtbot) -> None:
    """Dismissal via outside click clears the anchor selected state."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    anchor.setCheckable(True)
    qtbot.addWidget(anchor)
    popup.show_for(anchor, [_session("a", "A")], lambda _id: None)
    popup.hide_popup()
    assert not anchor.isChecked()


def test_long_session_title_is_elided(qapp: QApplication, qtbot) -> None:
    """Long titles ellipsize instead of forcing horizontal scroll."""
    from PySide6.QtWidgets import QLabel

    from ui.styling.theme import AI_SESSION_HISTORY_POPUP_WIDTH_EM

    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    flyout = QWidget()
    flyout.setObjectName("sidebarPanelArea")
    flyout.resize(420, 600)
    anchor = QPushButton("anchor", flyout)
    qtbot.addWidget(flyout)
    long_title = "tell me how to send an http request in classic asp with a very long title"
    popup.show_for(anchor, [_session("a", long_title)], lambda _id: None)
    assert popup.width() == round(AI_SESSION_HISTORY_POPUP_WIDTH_EM * popup.fontMetrics().height())
    assert popup._list.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    title = popup.findChild(QLabel, "aiSessionHistoryTitle")
    assert title is not None
    assert title.toolTip() == long_title
    assert title.text() != long_title
    assert title.text().endswith("…") or len(title.text()) < len(long_title)
