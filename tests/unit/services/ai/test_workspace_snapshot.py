"""Tests for session-keyed workspace snapshot registry."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from services.ai.chat.workspace_snapshot import (
    clear_last_search_hits,
    clear_workspace_snapshot,
    get_last_search_hits,
    get_workspace_snapshot,
    set_last_search_hits,
    set_workspace_snapshot,
)
from ui.main_window.ai_chat_runs import _AiChatRunsMixin


@pytest.fixture(autouse=True)
def _clear_snapshots() -> None:
    clear_workspace_snapshot()


def test_set_get_and_clear_one_session() -> None:
    """Snapshots round-trip for a single session id."""
    session_id = str(uuid.uuid4())
    snap: dict[str, object] = {
        "active_tab_index": 0,
        "active_collection_id": 4,
        "current_env_id": None,
        "active_response": None,
        "tabs": [],
    }
    set_workspace_snapshot(session_id, snap)
    loaded = get_workspace_snapshot(session_id)
    assert loaded is not None
    assert loaded["active_collection_id"] == 4
    assert loaded["tabs"] == []

    clear_workspace_snapshot(session_id)
    assert get_workspace_snapshot(session_id) is None


def test_sessions_are_isolated() -> None:
    """Each session id keeps its own snapshot."""
    a = str(uuid.uuid4())
    b = str(uuid.uuid4())
    set_workspace_snapshot(a, {"active_tab_index": 1, "tabs": []})
    set_workspace_snapshot(
        b,
        {
            "active_tab_index": 2,
            "active_collection_id": 99,
            "current_env_id": None,
            "active_response": None,
            "tabs": [],
        },
    )
    loaded_a = get_workspace_snapshot(a)
    loaded_b = get_workspace_snapshot(b)
    assert loaded_a is not None
    assert loaded_b is not None
    assert loaded_a["active_tab_index"] == 1
    assert loaded_b["active_collection_id"] == 99


def test_clear_all_sessions() -> None:
    """clear_workspace_snapshot(None) drops every entry."""
    set_workspace_snapshot("s1", {"active_tab_index": 0, "tabs": []})
    set_workspace_snapshot("s2", {"active_tab_index": 1, "tabs": []})
    clear_workspace_snapshot()
    assert get_workspace_snapshot("s1") is None
    assert get_workspace_snapshot("s2") is None


def test_empty_session_id_is_ignored() -> None:
    """Blank session ids are no-ops."""
    set_workspace_snapshot("", {"active_tab_index": 0, "tabs": []})
    assert get_workspace_snapshot("") is None


def test_snapshot_cleared_on_run_finish() -> None:
    """Snapshot is cleared when the last run for a session finishes."""
    session_id = str(uuid.uuid4())
    set_workspace_snapshot(session_id, {"active_tab_index": 0, "tabs": []})

    class _Runs(_AiChatRunsMixin):
        def _update_active_session_busy_state(self) -> None:
            return None

    mixin = _Runs()
    mixin._host = staticmethod(  # type: ignore[assignment, method-assign, misc]
        lambda _obj: SimpleNamespace(_maybe_generate_session_title=lambda _sid: None)
    )
    mixin._active_run_context = None
    mixin._active_ai_session_id = session_id
    mixin._pending_title_session_id = None
    mixin._chat_run_registry = MagicMock(is_running=MagicMock(return_value=False))
    mixin._on_registry_run_finished(session_id, 1)
    assert get_workspace_snapshot(session_id) is None


def test_snapshot_builder_shapes() -> None:
    """Snapshot builder captures request vs folder tab shapes correctly."""
    request_editor = MagicMock()
    request_editor.get_request_data.return_value = {"method": "GET", "url": "http://x"}
    folder_editor = MagicMock()
    folder_editor.get_collection_data.return_value = {"name": "Folder A"}

    request_ctx = SimpleNamespace(
        tab_type="request",
        editor=request_editor,
        folder_editor=None,
        local_script_editor=None,
        response_viewer=SimpleNamespace(
            has_live_response=lambda: True,
            get_save_response_data=lambda: {
                "code": 200,
                "status": "OK",
                "headers": [],
                "body": "{}",
                "preview_language": "json",
            },
            _last_live_response={
                "elapsed_ms": 50,
                "size_bytes": 100,
                "test_results": [{"passed": True}],
            },
            _test_results=[{"passed": True}],
        ),
        request_id=10,
        collection_id=3,
        local_script_id=None,
        is_dirty=True,
        draft_name=None,
        variable_collection_id=None,
    )
    folder_ctx = SimpleNamespace(
        tab_type="folder",
        editor=folder_editor,
        folder_editor=folder_editor,
        local_script_editor=None,
        request_id=None,
        collection_id=4,
        local_script_id=None,
        is_dirty=False,
        draft_name=None,
        variable_collection_id=None,
    )

    host = SimpleNamespace(
        _tab_bar=SimpleNamespace(
            currentIndex=lambda: 0,
            tab_request_info=lambda i: ("GET", "Tab Name" if i == 0 else ""),
        ),
        _tabs={0: request_ctx, 1: folder_ctx},
        _deferred_tabs={},
        _env_selector=SimpleNamespace(current_environment_id=lambda: 7),
        response_viewer=SimpleNamespace(has_live_response=lambda: True),
    )

    class _Runs(_AiChatRunsMixin):
        pass

    mixin = _Runs()
    host_any = cast(Any, mixin)
    host_any._tab_bar = host._tab_bar
    host_any._tabs = host._tabs
    host_any._deferred_tabs = host._deferred_tabs
    host_any._env_selector = host._env_selector
    snap = mixin._build_ai_workspace_snapshot()

    req_tab = snap["tabs"][0]
    assert req_tab["request_data"] == {"method": "GET", "url": "http://x"}
    folder_tab = snap["tabs"][1]
    assert "request_data" not in folder_tab
    assert snap["current_env_id"] == 7

    active_resp = mixin._snapshot_active_response(request_ctx)
    assert active_resp is not None
    assert active_resp.get("elapsed_ms") == 50
    assert active_resp.get("test_summary") == {"passed": 1, "failed": 0}

    no_resp = mixin._snapshot_active_response(
        SimpleNamespace(response_viewer=SimpleNamespace(has_live_response=lambda: False))
    )
    assert no_resp is None

    name = mixin._snapshot_tab_name(host, 0, request_ctx)
    assert name == "Tab Name"
    folder_name = mixin._snapshot_tab_name(host, 1, folder_ctx)
    assert folder_name == "Folder A"

    expected_keys = {
        "index",
        "tab_type",
        "name",
        "request_id",
        "collection_id",
        "local_script_id",
        "is_dirty",
        "is_active",
    }
    for tab in snap["tabs"]:
        assert expected_keys.issubset(tab.keys())


def test_last_search_hits_round_trip_and_clear_with_snapshot() -> None:
    """Last search hits store per session and clear with the workspace snapshot."""
    session_id = str(uuid.uuid4())
    set_last_search_hits(session_id, [3, 1, 2, 0, -1])
    assert get_last_search_hits(session_id) == [3, 1, 2]
    clear_last_search_hits(session_id)
    assert get_last_search_hits(session_id) is None

    set_last_search_hits(session_id, [9, 8])
    set_workspace_snapshot(session_id, {"tabs": []})
    clear_workspace_snapshot(session_id)
    assert get_last_search_hits(session_id) is None
    assert get_workspace_snapshot(session_id) is None
