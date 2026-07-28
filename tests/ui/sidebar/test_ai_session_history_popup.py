"""Tests for the AI session history popover."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox, QPushButton, QWidget

from services.ai.chat.session_service import AiChatSessionDict, AiChatSessionService
from ui.sidebar.ai.chat_sessions.history.actions_popup import SessionHistoryActionsPopup
from ui.sidebar.ai.chat_sessions.history.delegate import session_row_menu_rect
from ui.sidebar.ai.chat_sessions.history.model import (
    ACTIVE_SESSION_ROLE,
    RELATIVE_TIME_ROLE,
    RUNNING_ROLE,
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


def test_running_session_row_shows_running_indicator(qapp: QApplication, qtbot) -> None:
    """Rows for in-flight agent runs set RUNNING_ROLE and animate a spinner."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    running_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    popup.show_for(
        anchor,
        [_session(running_id, "Alpha"), _session("b", "Beta")],
        lambda _id: None,
    )
    popup.set_running_session_ids(frozenset({running_id}))
    index = popup._model.index(0, 0)
    assert popup._model.data(index, RUNNING_ROLE) is True
    assert "Running" not in str(popup._model.data(index, RELATIVE_TIME_ROLE))
    assert popup._model.data(popup._model.index(1, 0), RUNNING_ROLE) is False
    assert popup._running_spinner_timer.isActive()
    frame0 = popup._delegate.spin_frame()
    qtbot.wait(200)
    assert popup._delegate.spin_frame() != frame0
    popup.set_running_session_ids(frozenset())
    assert not popup._running_spinner_timer.isActive()


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
    """Clicking a row body invokes the select callback with the session id."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    selected: list[str] = []

    def on_select(session_id: str) -> None:
        selected.append(session_id)

    popup.show_for(anchor, [_session("sess-1", "One")], on_select)
    index = popup._model.index(0, 0)
    row_rect = popup._list.visualRect(index)
    body_pos = QPoint(row_rect.left() + 20, row_rect.center().y())
    qtbot.mouseClick(popup._list.viewport(), Qt.MouseButton.LeftButton, pos=body_pos)
    qtbot.wait(20)
    assert selected == ["sess-1"]
    assert not popup.isVisible()


def test_app_event_filter_ignores_non_qobject_watchers(qapp: QApplication, qtbot) -> None:
    """App-wide filter must not forward layout child events to QFrame.eventFilter."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    popup.show_for(anchor, [_session("sess-1", "One")], lambda _id: None)

    class _NotQObject:
        """Stand-in for QWidgetItem-style non-QObject event-filter watchers."""

    assert popup.eventFilter(_NotQObject(), QEvent(QEvent.Type.ChildAdded)) is False  # type: ignore[arg-type]


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


def test_long_title_menu_clickable_with_scrollbar(qapp: QApplication, qtbot) -> None:
    """Long titles with a vertical scrollbar keep the ⋯ control inside the viewport."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    popup.setMinimumHeight(120)
    popup.resize(popup._width_for_anchor(QWidget()), 120)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    long_title = (
        "can you find me collectiones named request? how many collections are called "
        "'DiagnosticCollection'?"
    )
    sessions = [
        _session(f"s{index}", long_title if index == 0 else f"Session {index}")
        for index in range(12)
    ]
    selected: list[str] = []
    popup.show_for(anchor, sessions, selected.append)
    qapp.processEvents()
    assert popup._list.verticalScrollBar().maximum() > 0

    index = popup._model.index(0, 0)
    row_rect = popup._list.visualRect(index)
    viewport_w = popup._list.viewport().width()
    from ui.sidebar.ai.chat_sessions.history.delegate import (
        session_row_menu_rect,
        session_row_viewport_rect,
    )

    content_rect = session_row_viewport_rect(row_rect, viewport_w)
    menu_rect = session_row_menu_rect(content_rect, viewport_width=0)
    assert menu_rect.right() <= viewport_w
    menu_center = menu_rect.center()
    qtbot.mouseMove(popup._list.viewport(), pos=menu_center)
    qtbot.wait(10)
    qtbot.mouseClick(popup._list.viewport(), Qt.MouseButton.LeftButton, pos=menu_center)
    qtbot.wait(10)
    assert SessionHistoryActionsPopup.instance().isVisible()
    assert selected == []
    assert popup.isVisible()


def test_menu_dots_click_opens_actions_not_session(qapp: QApplication, qtbot) -> None:
    """Clicking ⋯ opens the actions flyout without opening the session."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    selected: list[str] = []
    popup.show_for(anchor, [_session("sess-1", "One")], selected.append)
    index = popup._model.index(0, 0)
    row_rect = popup._list.visualRect(index)
    menu_center = session_row_menu_rect(row_rect).center()
    qtbot.mouseMove(popup._list.viewport(), pos=menu_center)
    qtbot.wait(10)
    qtbot.mouseClick(popup._list.viewport(), Qt.MouseButton.LeftButton, pos=menu_center)
    qtbot.wait(10)
    assert SessionHistoryActionsPopup.instance().isVisible()
    assert selected == []
    assert popup.isVisible()


def test_row_body_click_opens_session_not_menu(qapp: QApplication, qtbot) -> None:
    """Clicking the row body opens the session, not the actions flyout."""
    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    selected: list[str] = []
    popup.show_for(anchor, [_session("sess-1", "One")], selected.append)
    index = popup._model.index(0, 0)
    row_rect = popup._list.visualRect(index)
    body_pos = QPoint(row_rect.left() + 16, row_rect.center().y())
    qtbot.mouseClick(popup._list.viewport(), Qt.MouseButton.LeftButton, pos=body_pos)
    qtbot.wait(20)
    assert selected == ["sess-1"]
    assert not SessionHistoryActionsPopup.instance().isVisible()


def test_editor_event_menu_hit_returns_true(qapp: QApplication, qtbot) -> None:
    """``editorEvent`` on ⋯ returns True and emits ``menu_requested``."""
    from PySide6.QtCore import QEvent, QRect, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QStyleOptionViewItem

    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    delegate = popup._delegate
    popup._model.set_sessions([_session("a", "Alpha")], active_session_id=None)
    index = popup._model.index(0, 0)
    row_rect = QRect(0, 0, 300, 44)
    menu_center = session_row_menu_rect(row_rect).center()
    option = QStyleOptionViewItem()
    option.rect = row_rect
    emitted: list[int] = []
    delegate.menu_requested.connect(lambda idx: emitted.append(idx.row()))
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(menu_center),
        QPointF(menu_center),
        QPointF(menu_center),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    handled = delegate.editorEvent(event, popup._model, option, index)
    assert handled is True
    assert emitted == [0]


def test_rename_dialog_calls_service(qapp: QApplication, qtbot, monkeypatch) -> None:
    """Rename from the actions menu persists via ``rename_session``."""
    calls: list[tuple[str, str]] = []

    def fake_rename(session_id: str, title: str) -> AiChatSessionDict:
        calls.append((session_id, title))
        return _session(session_id, title)

    monkeypatch.setattr(AiChatSessionService, "rename_session", fake_rename)
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("Renamed", True),
    )

    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    popup.show_for(anchor, [_session("sess-1", "Old")], lambda _id: None)
    popup._rename_session("sess-1", "Old")
    assert calls == [("sess-1", "Renamed")]


def test_delete_confirmed_calls_service(qapp: QApplication, qtbot, monkeypatch) -> None:
    """Delete with confirmation calls ``delete_session``."""
    deleted: list[str] = []

    def fake_delete(session_id: str) -> bool:
        deleted.append(session_id)
        return True

    monkeypatch.setattr(AiChatSessionService, "delete_session", fake_delete)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    popup = AiSessionHistoryPopup()
    qtbot.addWidget(popup)
    anchor = QPushButton("anchor")
    qtbot.addWidget(anchor)
    popup.show_for(anchor, [_session("sess-1", "Gone")], lambda _id: None)
    popup._delete_session("sess-1", "Gone")
    assert deleted == ["sess-1"]
