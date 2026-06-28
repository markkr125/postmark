"""Tests for subagent disk path registry and resolution."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

from database.data_paths import session_disk_dir
from services.ai.chat.subagent_disk_registry import (
    clear_subagent_disk_registry,
    lookup_subagent_disk_path,
    next_unassigned_subagent_disk_path,
    register_subagent_disk_path,
    resolve_subagent_disk_path,
    session_subagents_root,
)
from services.ai.chat.subagent_events import SubagentRunRecord
from tests.unit.services.ai.test_subagent_events import (
    ActionEvent,
    DelegateAction,
    DelegateObservation,
    ObservationEvent,
)


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    clear_subagent_disk_registry()


def test_session_subagents_root_uses_session_disk(tmp_path, monkeypatch) -> None:
    """Subagent folders live under the parent session disk directory."""
    monkeypatch.setattr(
        "database.data_paths.user_ai_conversations_root",
        lambda: tmp_path,
    )
    session_id = str(uuid.uuid4())
    assert session_subagents_root(session_id) == session_disk_dir(session_id) / "subagents"


def test_register_and_lookup_disk_path() -> None:
    """Spawn-time registration returns the exact folder path."""
    session_id = str(uuid.uuid4())
    register_subagent_disk_path(session_id, "ts", "/tmp/subagents/ts-run")
    assert lookup_subagent_disk_path(session_id, "ts") is None  # path missing on disk

    path = Path("/tmp/postmark-test-subagent-ts")
    path.mkdir(parents=True, exist_ok=True)
    try:
        register_subagent_disk_path(session_id, "ts", str(path))
        assert lookup_subagent_disk_path(session_id, "ts") == str(path)
    finally:
        path.rmdir()


def test_next_unassigned_uses_session_subagents_dir(tmp_path, monkeypatch) -> None:
    """Oldest folder under the session subagents dir wins."""
    monkeypatch.setattr(
        "database.data_paths.user_ai_conversations_root",
        lambda: tmp_path,
    )
    session_id = str(uuid.uuid4())
    root = session_subagents_root(session_id)
    root.mkdir(parents=True)
    first = root / "aaa"
    second = root / "bbb"
    first.mkdir()
    time.sleep(0.02)
    second.mkdir()
    turn_at = time.time()
    assigned: set[str] = set()
    assert next_unassigned_subagent_disk_path(
        session_id,
        turn_started_at=turn_at - 5.0,
        assigned=assigned,
    ) == str(first)
    assigned.add(str(first))
    assert next_unassigned_subagent_disk_path(
        session_id,
        turn_started_at=turn_at - 5.0,
        assigned=assigned,
    ) == str(second)


def test_resolve_prefers_registry(tmp_path, monkeypatch) -> None:
    """Registry lookup beats mtime heuristics."""
    monkeypatch.setattr(
        "database.data_paths.user_ai_conversations_root",
        lambda: tmp_path,
    )
    session_id = str(uuid.uuid4())
    root = session_subagents_root(session_id)
    root.mkdir(parents=True)
    older = root / "older"
    newer = root / "newer"
    older.mkdir()
    time.sleep(0.02)
    newer.mkdir()
    register_subagent_disk_path(session_id, "py", str(newer))

    record: SubagentRunRecord = {
        "id": "py",
        "kind": "delegate",
        "label": "py",
        "subagent_type": "wiki-researcher",
        "status": "running",
    }
    path = resolve_subagent_disk_path(
        session_id,
        record,
        turn_started_at=time.time() - 5.0,
        assigned=set(),
    )
    assert path == str(newer)


def test_tracker_assigns_registered_disk_path(tmp_path, monkeypatch) -> None:
    """Event tracker uses the spawn registry when session_id is set."""
    monkeypatch.setattr(
        "database.data_paths.user_ai_conversations_root",
        lambda: tmp_path,
    )
    from services.ai.chat.subagent_events import SubagentEventTracker

    session_id = str(uuid.uuid4())
    disk = session_subagents_root(session_id) / "child"
    disk.mkdir(parents=True)
    register_subagent_disk_path(session_id, "ts", str(disk))

    tracker = SubagentEventTracker(session_id=session_id)
    tracker.ingest(
        ActionEvent(
            "delegate",
            DelegateAction("spawn", ids=["ts"], agent_types=["wiki-researcher"]),
            tool_call_id="spawn1",
        )
    )
    running = tracker.ingest(
        ObservationEvent("delegate", DelegateObservation("spawn"), tool_call_id="spawn1")
    )
    assert running[0]["disk_path"] == str(disk)

    delegated = tracker.ingest(
        ActionEvent(
            "delegate",
            DelegateAction("delegate", tasks={"ts": "Find TypeScript docs"}),
            tool_call_id="delegate1",
        )
    )
    assert delegated[0]["disk_path"] == str(disk)
