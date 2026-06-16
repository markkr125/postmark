"""Tests for AI chat session/message repository."""

from __future__ import annotations

import uuid

import pytest

from database.data_paths import session_disk_dir
from database.models.ai_chat.ai_chat_query_repository import (
    get_session_by_id,
    get_session_with_messages,
    list_messages_after,
    list_messages_before,
    list_messages_tail,
    list_sessions,
    search_messages,
)
from database.models.ai_chat.ai_chat_repository import (
    append_message,
    archive_session,
    count_messages_after,
    create_session,
    delete_message,
    delete_messages_after,
    delete_session,
    list_messages,
    rename_session,
    touch_session,
    update_user_message,
)


@pytest.fixture
def session_id() -> str:
    """Return a fresh session UUID string."""
    return str(uuid.uuid4())


def test_create_and_get_session(session_id: str) -> None:
    """Create a session and fetch it by id."""
    created = create_session(
        session_id=session_id,
        title="Hello",
        model_id="openai/gpt-4",
        mode="agent",
    )
    assert created["id"] == session_id
    assert created["title"] == "Hello"
    assert created["agent_id"] == "postmark-assistant"

    fetched = get_session_by_id(session_id)
    assert fetched is not None
    assert fetched["title"] == "Hello"


def test_get_session_with_messages(session_id: str) -> None:
    """Session metadata and messages load in one query."""
    create_session(
        session_id=session_id,
        title="Combo",
        model_id="openai/gpt-4",
        mode="agent",
    )
    append_message(session_id=session_id, role="user", content="one")
    append_message(session_id=session_id, role="assistant", content="two")
    session, messages = get_session_with_messages(session_id)
    assert session is not None
    assert session["title"] == "Combo"
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_append_message_and_list(session_id: str) -> None:
    """Messages append and list in order."""
    create_session(
        session_id=session_id,
        title="Chat",
        model_id=None,
        mode="ask",
    )
    append_message(session_id=session_id, role="user", content="Hi")
    append_message(
        session_id=session_id,
        role="assistant",
        content="Hello",
        thinking="trace",
        thinking_duration_seconds=3,
    )

    messages = list_messages(session_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["content"] == "Hello"
    assert messages[1]["thinking"] == "trace"
    assert messages[1]["thinking_duration_seconds"] == 3


def test_delete_message_removes_row(session_id: str) -> None:
    """delete_message removes one row and returns its session id."""
    create_session(
        session_id=session_id,
        title="Chat",
        model_id=None,
        mode="ask",
    )
    row = append_message(session_id=session_id, role="user", content="Hi")
    assert delete_message(row["id"]) == session_id
    assert list_messages(session_id) == []


def test_touch_session_updates_preview(session_id: str) -> None:
    """``touch_session`` updates preview and bumps updated_at."""
    create_session(session_id=session_id, title="T", model_id=None, mode="agent")
    before = get_session_by_id(session_id)
    assert before is not None
    touched = touch_session(session_id, last_preview="preview text")
    assert touched is not None
    assert touched["last_preview"] == "preview text"
    assert touched["updated_at"] >= before["updated_at"]


def test_rename_session(session_id: str) -> None:
    """Rename updates the title."""
    create_session(session_id=session_id, title="Old", model_id=None, mode="agent")
    updated = rename_session(session_id, "New title")
    assert updated is not None
    assert updated["title"] == "New title"


def test_archive_session_filters_list(session_id: str) -> None:
    """Archived sessions are hidden unless requested."""
    create_session(session_id=session_id, title="Archived", model_id=None, mode="agent")
    archive_session(session_id)
    assert not list_sessions()
    assert list_sessions(include_archived=True)


def test_search_messages_by_title_and_content(session_id: str) -> None:
    """Search finds sessions by title or message content."""
    other_id = str(uuid.uuid4())
    create_session(session_id=session_id, title="Python tips", model_id=None, mode="agent")
    create_session(session_id=other_id, title="Other", model_id=None, mode="agent")
    append_message(session_id=other_id, role="user", content="javascript async")

    by_title = search_messages("Python")
    assert any(s["id"] == session_id for s in by_title)

    by_content = search_messages("javascript")
    assert any(s["id"] == other_id for s in by_content)


def test_delete_session_removes_rows_and_disk(
    session_id: str,
    monkeypatch,
    tmp_path,
) -> None:
    """Delete removes SQLite rows and the SDK disk directory."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    create_session(session_id=session_id, title="Del", model_id=None, mode="agent")
    append_message(session_id=session_id, role="user", content="bye")
    disk = session_disk_dir(session_id)
    disk.mkdir(parents=True)
    (disk / "base_state.json").write_text("{}", encoding="utf-8")

    assert delete_session(session_id)
    assert get_session_by_id(session_id) is None
    assert list_messages(session_id) == []
    assert not disk.exists()


def _seed_turns(session_id: str, turns: int) -> list[dict]:
    """Append *turns* user/assistant pairs and return message dicts."""
    rows: list[dict] = []
    for index in range(turns):
        rows.append(append_message(session_id=session_id, role="user", content=f"u{index}"))
        rows.append(append_message(session_id=session_id, role="assistant", content=f"a{index}"))
    return rows


def test_list_messages_tail_and_before(session_id: str) -> None:
    """Tail and before pagination return ordered slices with has_older probes."""
    create_session(session_id=session_id, title="Page", model_id=None, mode="agent")
    all_rows = _seed_turns(session_id, 5)
    tail, has_older = list_messages_tail(session_id, limit=4)
    assert has_older
    assert len(tail) == 4
    assert tail[-1]["id"] == all_rows[-1]["id"]
    older, has_more = list_messages_before(session_id, before_id=tail[0]["id"], limit=4)
    assert older
    assert older[-1]["id"] < tail[0]["id"]
    assert has_more or older[0]["id"] == all_rows[0]["id"]


def test_list_messages_after(session_id: str) -> None:
    """After pagination returns rows newer than a cursor id."""
    create_session(session_id=session_id, title="After", model_id=None, mode="agent")
    all_rows = _seed_turns(session_id, 4)
    middle_id = all_rows[3]["id"]
    newer, has_newer = list_messages_after(session_id, after_id=middle_id, limit=4)
    assert newer
    assert newer[0]["id"] > middle_id
    assert newer[-1]["id"] == all_rows[-1]["id"]
    assert not has_newer


def test_list_messages_tail_exact_length(session_id: str) -> None:
    """Tail has_older is false when the session fits in one page."""
    create_session(session_id=session_id, title="Exact", model_id=None, mode="agent")
    _seed_turns(session_id, 2)
    tail, has_older = list_messages_tail(session_id, limit=4)
    assert len(tail) == 4
    assert not has_older


def test_append_message_persists_usage_columns(session_id: str) -> None:
    """Assistant usage metadata round-trips through append_message."""
    create_session(session_id=session_id, title="Usage", model_id="m1", mode="agent")
    row = append_message(
        session_id=session_id,
        role="assistant",
        content="Hi",
        model_id="m1",
        prompt_tokens=100,
        completion_tokens=20,
        reasoning_tokens=5,
    )
    assert row["model_id"] == "m1"
    assert row["prompt_tokens"] == 100
    assert row["completion_tokens"] == 20
    assert row["reasoning_tokens"] == 5
    loaded = list_messages(session_id)
    assert loaded[-1]["prompt_tokens"] == 100


def test_count_and_delete_messages_after(session_id: str) -> None:
    """``count_messages_after`` and ``delete_messages_after`` truncate the tail."""
    create_session(session_id=session_id, title="T", model_id=None, mode="agent")
    u1 = append_message(session_id=session_id, role="user", content="One")
    a1 = append_message(session_id=session_id, role="assistant", content="A1")
    u2 = append_message(session_id=session_id, role="user", content="Two")
    a2 = append_message(session_id=session_id, role="assistant", content="A2")
    assert count_messages_after(session_id, u1["id"]) == 3
    deleted = delete_messages_after(session_id, u1["id"])
    assert deleted == [a1["id"], u2["id"], a2["id"]]
    remaining = list_messages(session_id)
    assert len(remaining) == 1
    assert remaining[0]["content"] == "One"


def test_update_user_message_persists_send_snapshot(session_id: str) -> None:
    """``update_user_message`` updates content and per-send fields."""
    create_session(session_id=session_id, title="T", model_id=None, mode="agent")
    row = append_message(session_id=session_id, role="user", content="Hi")
    updated = update_user_message(
        row["id"],
        content="Edited",
        send_model_id="m1",
        send_mode="plan",
        send_agent_id="postmark-assistant",
        send_reasoning_effort="medium",
        send_thinking_enabled="1",
        send_run_context_tokens=128_000,
    )
    assert updated is not None
    assert updated["content"] == "Edited"
    assert updated["send_model_id"] == "m1"
    assert updated["send_mode"] == "plan"
