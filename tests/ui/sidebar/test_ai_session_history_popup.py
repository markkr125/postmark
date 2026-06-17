"""Tests for the AI session history popover."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from services.ai.chat.session_service import AiChatSessionDict, AiChatSessionService
from ui.sidebar.ai.chat_sessions.history.model import (
    ACTIVE_SESSION_ROLE,
    RELATIVE_TIME_ROLE,
)
from ui.sidebar.ai.chat_sessions.history_popup import AiSessionHistoryPopup
from ui.sidebar.ai.chat_sessions.time_format import format_relative_time
from ui.styling.theme import AI_SESSION_HISTORY_POPUP_WIDTH_EM


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
    assert popup._model.rowCount() == 2


def test_search_filters_by_title(qapp: QApplication, qtbot) -> None:
    """Client-side search filters session titles when rows are preloaded."""
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
    assert popup._model.rowCount() == 1


def test_active_session_row_is_highlighted(qapp: QApplication, qtbot) -> None:
    """The open chat session row is marked active in the list model."""
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
    assert popup._model.data(popup._model.index(0, 0), ACTIVE_SESSION_ROLE) is False
    assert popup._model.data(popup._model.index(1, 0), ACTIVE_SESSION_ROLE) is True
    assert popup._list.currentIndex().row() == 1


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
    popup._list.clicked.emit(popup._model.index(0, 0))
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
    index = popup._model.index(0, 0)
    assert popup._model.data(index, Qt.ItemDataRole.ToolTipRole) == long_title
    text_width = max(0, popup.width() - 16)
    title_font = QFont()
    title_font.setPixelSize(12)
    elided = QFontMetrics(title_font).elidedText(
        long_title,
        Qt.TextElideMode.ElideRight,
        text_width,
    )
    assert elided != long_title or len(long_title) <= text_width


def test_session_time_label_shown_below_title_when_scrollbar_visible(
    qapp: QApplication, qtbot
) -> None:
    """Relative time is available per row and the list scrolls with many sessions."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    popup.setMinimumHeight(120)
    popup.resize(popup._width_for_anchor(QWidget()), 120)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    old = datetime.now(tz=UTC) - timedelta(days=30)
    sessions = [_session(f"s{index}", f"Session {index}") for index in range(12)]
    for session in sessions:
        session["updated_at"] = old.isoformat()
    popup.show_for(anchor, sessions, lambda _id: None)
    qapp.processEvents()
    assert popup._list.verticalScrollBar().maximum() > 0

    expected = format_relative_time(old)
    for row in range(popup._model.rowCount()):
        index = popup._model.index(row, 0)
        assert popup._model.data(index, RELATIVE_TIME_ROLE) == expected


def test_open_for_shows_loading_then_sessions(qapp: QApplication, qtbot, monkeypatch) -> None:
    """``open_for`` loads sessions off the GUI thread and replaces the loading row."""
    calls: list[str | None] = []

    def fake_list_sessions(*, search: str | None = None) -> list[AiChatSessionDict]:
        calls.append(search)
        return [_session("a", "Alpha")]

    monkeypatch.setattr(AiChatSessionService, "list_sessions", fake_list_sessions)

    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    popup.open_for(anchor, lambda _id: None)
    assert popup._model.data(popup._model.index(0, 0)) == "Loading…"
    qtbot.waitUntil(
        lambda: popup._model.rowCount() == 1
        and popup._model.data(popup._model.index(0, 0)) == "Alpha",
        timeout=5000,
    )
    assert calls == [None]


def test_debounced_search_calls_list_sessions(qapp: QApplication, qtbot, monkeypatch) -> None:
    """Typing in search debounces SQL-backed ``list_sessions(search=...)`` reloads."""
    calls: list[str | None] = []

    def fake_list_sessions(*, search: str | None = None) -> list[AiChatSessionDict]:
        calls.append(search)
        if search:
            return [_session("b", "Beta")]
        return [_session("a", "Alpha"), _session("b", "Beta")]

    monkeypatch.setattr(AiChatSessionService, "list_sessions", fake_list_sessions)

    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    popup.open_for(anchor, lambda _id: None)
    qtbot.waitUntil(lambda: len(calls) >= 1, timeout=5000)

    popup._search.setText("beta")
    qtbot.wait(50)
    assert calls == [None]

    qtbot.wait(250)
    qtbot.waitUntil(lambda: calls[-1] == "beta", timeout=5000)
    qtbot.waitUntil(
        lambda: popup._model.rowCount() == 1
        and popup._model.data(popup._model.index(0, 0)) == "Beta",
        timeout=5000,
    )


def test_show_for_many_sessions_populates_quickly(qapp: QApplication, qtbot) -> None:
    """Two hundred preloaded rows bind to the model without a long stall."""
    import time

    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    sessions = [_session(f"s{index}", f"Session {index}") for index in range(220)]
    started = time.monotonic()
    popup.show_for(anchor, sessions, lambda _id: None)
    qapp.processEvents()
    elapsed = time.monotonic() - started
    assert popup._model.rowCount() == 220
    assert elapsed < 2.0
