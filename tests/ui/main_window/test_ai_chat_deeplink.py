"""Tests for AI chat workspace deep-link navigation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from ui.main_window.ai_chat_controller import _AiChatControllerMixin
from ui.main_window.tab_controller import _TabControllerMixin


class _StubTabBar:
    """Minimal tab bar for focus-by-index tests."""

    def __init__(self, count: int) -> None:
        self._count = count
        self.current_index_calls: list[int] = []

    def count(self) -> int:
        return self._count

    def setCurrentIndex(self, index: int) -> None:
        self.current_index_calls.append(index)


class _TabFocusHost(_TabControllerMixin):
    """Minimal host exercising _focus_open_tab."""

    def __init__(self, tab_bar: _StubTabBar) -> None:
        self._tab_bar = tab_bar  # type: ignore[assignment]


class _DeepLinkHost(_AiChatControllerMixin):
    """Minimal host recording open/focus calls."""

    def __init__(self) -> None:
        self.open_request_calls: list[tuple[Any, ...]] = []
        self.open_folder_calls: list[tuple[Any, ...]] = []
        self.open_script_calls: list[int] = []
        self.focus_calls: list[str] = []
        self.focus_open_tab_calls: list[int] = []
        self.history_open_calls: list[tuple[int, bool]] = []
        self.env_open_calls: list[int | None] = []
        self.sidebar_refresh_calls: int = 0
        self.panel_open_calls: list[str] = []
        self.select_response_calls: list[int] = []
        self.status_messages: list[tuple[str, int]] = []
        self.open_request_succeeds = True
        self.open_script_succeeds = True
        self.focus_tab_succeeds = True
        self.env_open_succeeds = True
        self._tab_ctx = SimpleNamespace(
            editor=SimpleNamespace(focus_section=self._record_focus),
            request_id=12,
        )
        self._right_sidebar: Any = SimpleNamespace(
            open_panel=self._open_panel,
            saved_responses_panel=SimpleNamespace(select_response=self._select_response),
        )

    def _record_focus(self, section: str, *, scripts_kind: str | None = None) -> None:
        self.focus_calls.append(section)

    def _open_request(self, request_id: int, *, push_history: bool, is_preview: bool) -> bool:
        self.open_request_calls.append((request_id, push_history, is_preview))
        return self.open_request_succeeds

    def _open_folder(self, collection_id: int, *, focus_scripts_kind: str | None = None) -> None:
        self.open_folder_calls.append((collection_id, focus_scripts_kind))

    def _open_local_script(self, script_id: int) -> bool:
        self.open_script_calls.append(script_id)
        return self.open_script_succeeds

    def _focus_open_tab(self, index: int) -> bool:
        self.focus_open_tab_calls.append(index)
        return self.focus_tab_succeeds

    def _open_from_global_history(
        self,
        entry_id: int,
        *,
        load_centre_response: bool = False,
    ) -> None:
        self.history_open_calls.append((entry_id, load_centre_response))

    def _open_environments_tab(self, *, environment_id: int | None = None) -> bool:
        self.env_open_calls.append(environment_id)
        return self.env_open_succeeds

    def _refresh_sidebar(self, *, history_load_detail: bool = True) -> None:
        self.sidebar_refresh_calls += 1

    def _open_panel(self, panel: str) -> None:
        self.panel_open_calls.append(panel)

    def _select_response(self, response_id: int) -> None:
        self.select_response_calls.append(response_id)

    def _current_tab_context(self) -> SimpleNamespace:
        return self._tab_ctx

    def statusBar(self) -> SimpleNamespace:
        return SimpleNamespace(showMessage=self._show_status)

    def _show_status(self, message: str, timeout: int = 0) -> None:
        self.status_messages.append((message, timeout))


@pytest.fixture
def deeplink_host(qapp: QApplication) -> _DeepLinkHost:
    """Host wired for workspace target navigation tests."""
    host = _DeepLinkHost()
    return host


def test_on_workspace_target_requested(deeplink_host: _DeepLinkHost) -> None:
    """Deep links open tabs and apply focus per kind."""
    host = deeplink_host
    host._on_workspace_target_requested("request", 12, "test")
    assert host.open_request_calls == [(12, True, False)]
    assert host.focus_calls == ["test"]

    host.open_request_calls.clear()
    host.focus_calls.clear()
    host._on_workspace_target_requested("request", 12, "")
    assert host.open_request_calls == [(12, True, False)]
    assert host.focus_calls == []

    host._on_workspace_target_requested("collection", 5, "test")
    assert host.open_folder_calls[-1] == (5, "test")

    host._on_workspace_target_requested("collection", 5, "body")
    assert host.open_folder_calls[-1] == (5, None)

    host._on_workspace_target_requested("script", 9, "")
    assert 9 in host.open_script_calls

    before = len(host.open_request_calls)
    host._on_workspace_target_requested("request", 0, "")
    assert len(host.open_request_calls) == before
    assert host.status_messages
    assert "Invalid" in host.status_messages[-1][0]

    before_folder = len(host.open_folder_calls)
    host._on_workspace_target_requested("collection", -1, "")
    assert len(host.open_folder_calls) == before_folder


def test_on_workspace_target_skips_focus_when_tab_request_mismatch(
    deeplink_host: _DeepLinkHost,
) -> None:
    """Focus is applied only when the opened tab matches the deep-link entity id."""
    host = deeplink_host
    host._tab_ctx.request_id = 99
    host._on_workspace_target_requested("request", 12, "body")
    assert host.open_request_calls == [(12, True, False)]
    assert host.focus_calls == []
    assert any("could not focus" in msg.casefold() for msg, _ in host.status_messages)


def test_unknown_deeplink_kind_shows_status(deeplink_host: _DeepLinkHost) -> None:
    """Unsupported postmark:// kinds do not silently no-op — status tip is shown."""
    host = deeplink_host
    before_req = len(host.open_request_calls)
    host._on_workspace_target_requested("snippet", 42, "")
    assert len(host.open_request_calls) == before_req
    assert host.status_messages
    assert "snippet" in host.status_messages[-1][0]


def test_history_environment_saved_response_deeplinks(deeplink_host: _DeepLinkHost) -> None:
    """History, environment, and saved_response kinds open via real handlers."""
    host = deeplink_host
    host._on_workspace_target_requested("history", 7, "")
    assert host.history_open_calls == [(7, False)]

    host._on_workspace_target_requested("history", 8, "response")
    assert host.history_open_calls[-1] == (8, True)

    host._on_workspace_target_requested("environment", 3, "")
    assert host.env_open_calls == [3]

    with patch(
        "services.collection_service.CollectionService.get_saved_response",
        return_value={"id": 9, "request_id": 12, "name": "OK"},
    ):
        host._on_workspace_target_requested("saved_response", 9, "")
    assert host.open_request_calls[-1] == (12, True, False)
    assert host.panel_open_calls == ["saved_responses"]
    assert host.select_response_calls == [9]


def test_stale_tab_and_missing_entity_status_tips(deeplink_host: _DeepLinkHost) -> None:
    """Stale tabs and missing request/script show status tips."""
    host = deeplink_host
    host.focus_tab_succeeds = False
    host._on_workspace_target_requested("tab", 99, "")
    assert "no longer open" in host.status_messages[-1][0].casefold()

    host.open_request_succeeds = False
    host._on_workspace_target_requested("request", 55, "")
    assert "request not found" in host.status_messages[-1][0].casefold()

    host.open_script_succeeds = False
    host._on_workspace_target_requested("script", 8, "")
    assert "script not found" in host.status_messages[-1][0].casefold()

    host.env_open_succeeds = False
    host._on_workspace_target_requested("environment", 2, "")
    assert "environment not found" in host.status_messages[-1][0].casefold()


def test_tab_deeplink_focuses_index(deeplink_host: _DeepLinkHost) -> None:
    """Tab deep links decode 1-based ids and focus the open-tab bar index."""
    host = deeplink_host
    host._on_workspace_target_requested("tab", 2, "")
    assert host.focus_open_tab_calls == [1]
    host._on_workspace_target_requested("tab", 1, "")
    assert host.focus_open_tab_calls == [1, 0]

    tab_bar = _StubTabBar(count=1)
    focus_host = _TabFocusHost(tab_bar)
    assert focus_host._focus_open_tab(5) is False
    assert tab_bar.current_index_calls == []
    assert focus_host._focus_open_tab(0) is True
    assert tab_bar.current_index_calls == [0]


def test_unsupported_focus_shows_status_tip(deeplink_host: _DeepLinkHost) -> None:
    """Unsupported ?focus= values tip after a successful open."""
    host = deeplink_host
    host._on_workspace_target_requested("collection", 5, "body")
    assert host.open_folder_calls[-1] == (5, None)
    assert any("focus=" in msg and "not supported" in msg for msg, _ in host.status_messages)

    host.status_messages.clear()
    host._on_workspace_target_requested("request", 12, "not_a_section")
    assert host.open_request_calls[-1] == (12, True, False)
    assert host.focus_calls == []
    assert any("not supported" in msg for msg, _ in host.status_messages)

    host.status_messages.clear()
    host._on_workspace_target_requested("script", 9, "body")
    assert 9 in host.open_script_calls
    assert any("not supported" in msg for msg, _ in host.status_messages)


def test_history_busy_shows_status_tip(qapp: QApplication) -> None:
    """A second history open while busy shows a wait tip instead of silent drop."""
    from ui.main_window.history_navigation.mixin import _HistoryNavigationMixin

    class _BusyHost(_HistoryNavigationMixin):
        def __init__(self) -> None:
            self._global_history_open_busy = True
            self.status_messages: list[tuple[str, int]] = []

        def statusBar(self) -> SimpleNamespace:
            return SimpleNamespace(showMessage=self._show)

        def _show(self, message: str, timeout: int = 0) -> None:
            self.status_messages.append((message, timeout))

    host = _BusyHost()
    host._open_from_global_history(42)
    assert host.status_messages
    assert "wait" in host.status_messages[-1][0].casefold()
    assert "history" in host.status_messages[-1][0].casefold()
