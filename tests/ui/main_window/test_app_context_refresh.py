"""Tests for live app-context snapshot refresh."""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtCore import QObject

from ui.main_window.app_context_refresh import _AppContextRefreshMixin


class _RefreshHost(QObject, _AppContextRefreshMixin):
    """Minimal host exercising the refresh mixin."""

    def __init__(self) -> None:
        """Set up registry and session state."""
        super().__init__()
        self._active_ai_session_id: str | None = None
        self._chat_run_registry = MagicMock()
        self._app_context_refresh_timer = None
        self.writes: list[tuple[str, str]] = []
        self.collection_widget = MagicMock()
        self.local_scripts_widget = MagicMock()

    def write_app_context_snapshot(self, session_id: str, send_mode: str) -> None:
        """Record snapshot writes."""
        self.writes.append((session_id, send_mode))


def test_debounced_refresh_writes_once(qapp, qtbot) -> None:
    """Two rapid schedules coalesce into one snapshot write."""
    host = _RefreshHost()
    host._active_ai_session_id = "sess-1"
    registry = MagicMock()
    registry.is_running.return_value = True
    handle = MagicMock()
    handle.send_mode = "agent"
    registry.run_for.return_value = handle
    host._chat_run_registry = registry

    host._init_app_context_refresh()
    host.schedule_app_context_refresh()
    host.schedule_app_context_refresh()

    qtbot.wait(300)
    assert len(host.writes) == 1
    assert host.writes[0] == ("sess-1", "agent")


def test_refresh_skips_when_session_not_running(qapp) -> None:
    """No write when the active session has no in-flight worker."""
    host = _RefreshHost()
    host._active_ai_session_id = "sess-1"
    registry = MagicMock()
    registry.is_running.return_value = False
    host._chat_run_registry = registry

    host.refresh_active_session_snapshot()
    assert host.writes == []


def test_flush_refresh_writes_immediately(qapp) -> None:
    """Flush bypasses the debounce timer."""
    host = _RefreshHost()
    host._active_ai_session_id = "sess-1"
    registry = MagicMock()
    registry.is_running.return_value = True
    handle = MagicMock()
    handle.send_mode = "plan"
    registry.run_for.return_value = handle
    host._chat_run_registry = registry

    host._init_app_context_refresh()
    host.schedule_app_context_refresh()
    host.flush_app_context_refresh()

    assert host.writes == [("sess-1", "plan")]
