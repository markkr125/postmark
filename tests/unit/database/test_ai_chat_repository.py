"""Tests for AI chat session/message repository."""

from __future__ import annotations

import uuid

import pytest

from database.data_paths import session_disk_dir
from database.models.ai_chat.ai_chat_query_repository import (
    get_session_by_id,
    get_session_with_messages,
    list_sessions,
    search_messages,
)
from database.models.ai_chat.ai_chat_repository import (
    append_message,
    archive_session,
    create_session,
    delete_session,
    list_messages,
    rename_session,
    touch_session,
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
