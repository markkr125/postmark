"""Tests for AiChatSessionService."""

from __future__ import annotations

import sys
import types
import uuid
from typing import Any

import pytest

from database.data_paths import session_disk_dir
from database.models.ai_chat.ai_chat_repository import create_session, delete_session

from services.ai.ai_config import AiConfig, AiModelEntry
from services.ai.chat.agent_registry import DEFAULT_AGENT_ID
from services.ai.chat.compaction import (
    CHAT_CONDENSER_MAX_EVENTS,
    CHAT_CONDENSER_MINIMUM_PROGRESS,
    condenser_max_tokens,
)
from services.ai.chat.session_service import (
    AiChatSessionService,
    UserMessageSendSnapshot,
    _TITLE_PREVIEW_LEN,
)


def _entry(**kw: object) -> AiModelEntry:
    base: AiModelEntry = {
        "id": "id1",
        "provider": "openai",
        "label": "L",
        "model": "openai/gpt-4o",
        "base_url": "https://x",
        "api_version": "v1",
        "auth_kind": "none",
        "auth_ref": "",
        "context": 128_000,
    }
    base.update(kw)  # type: ignore[typeddict-item]
    return base


def _install_fake_sdk(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Install a minimal fake openhands.sdk for conversation building."""
    captured: dict[str, Any] = {}

    mod = types.ModuleType("openhands.sdk")

    class _TextContent:
        def __init__(self, text: str = "") -> None:
            self.text = text

    class _Message:
        def __init__(self, role: str = "assistant", content: object = None) -> None:
            self.role = role
            self.content = content or []

    class _MessageEvent:
        def __init__(self, source: str, text: str) -> None:
            self.source = source
            self.llm_message = _Message(content=[_TextContent(text)])

    class _State:
        def __init__(self, events: list[object]) -> None:
            self.events = events

    class _LLM:
        def __init__(self, **kw: object) -> None:
            self.kw = kw
            self.stream = kw.get("stream", False)
            self.model = kw.get("model", "")
            self.reasoning_effort = kw.get("reasoning_effort")
            self.litellm_extra_body = kw.get("litellm_extra_body", {})
            self.num_retries = kw.get("num_retries", 5)

        def model_copy(self, *, update: dict[str, object], deep: bool = False) -> _LLM:
            _ = deep
            merged = {**self.kw, **update}
            return _LLM(**merged)

        def reset_metrics(self) -> None:
            captured["llm_reset"] = True

    class _Agent:
        def __init__(self, **kw: object) -> None:
            captured["agent_kw"] = kw

    class _Conversation:
        def __init__(self, **kw: object) -> None:
            captured["conversation_kw"] = kw
            self.state = _State([])

    class _LocalWorkspace:
        def __init__(self, *, working_dir: str) -> None:
            captured["workspace_dir"] = working_dir

    class _Tool:
        def __init__(self, *, name: str, params: dict[str, object] | None = None) -> None:
            self.name = name
            self.params = params or {}

    mod.LLM = _LLM  # type: ignore[attr-defined]
    mod.Agent = _Agent  # type: ignore[attr-defined]
    mod.Conversation = _Conversation  # type: ignore[attr-defined]
    mod.TextContent = _TextContent  # type: ignore[attr-defined]
    mod.Tool = _Tool  # type: ignore[attr-defined]

    workspace_mod = types.ModuleType("openhands.sdk.workspace")
    workspace_mod.LocalWorkspace = _LocalWorkspace  # type: ignore[attr-defined]
    context_pkg = types.ModuleType("openhands.sdk.context")

    condenser_mod = types.ModuleType("openhands.sdk.context.condenser")

    class _LLMSummarizingCondenser:
        def __init__(self, **kw: object) -> None:
            self.llm = kw["llm"]
            self.max_size = kw["max_size"]
            self.max_tokens = kw["max_tokens"]
            self.minimum_progress = kw.get("minimum_progress", 0.1)

        def get_condensation_reasons(
            self, view: object, *, agent_llm: object | None = None
        ) -> set[str]:
            return set()

    condenser_mod.LLMSummarizingCondenser = _LLMSummarizingCondenser  # type: ignore[attr-defined]

    class _ActionEvent:
        """Stub action event for ``_fold_agent_event`` isinstance checks."""

        def __init__(self, source: str = "agent") -> None:
            self.source = source

    event_pkg = types.ModuleType("openhands.sdk.event")
    llm_conv_pkg = types.ModuleType("openhands.sdk.event.llm_convertible")
    message_mod = types.ModuleType("openhands.sdk.event.llm_convertible.message")
    message_mod.MessageEvent = _MessageEvent  # type: ignore[attr-defined]
    action_mod = types.ModuleType("openhands.sdk.event.llm_convertible.action")
    action_mod.ActionEvent = _ActionEvent  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "openhands", types.ModuleType("openhands"))
    monkeypatch.setitem(sys.modules, "openhands.sdk", mod)
    monkeypatch.setitem(sys.modules, "openhands.sdk.workspace", workspace_mod)
    monkeypatch.setitem(sys.modules, "openhands.sdk.context", context_pkg)
    monkeypatch.setitem(sys.modules, "openhands.sdk.context.condenser", condenser_mod)
    monkeypatch.setitem(sys.modules, "openhands.sdk.event", event_pkg)
    monkeypatch.setitem(sys.modules, "openhands.sdk.event.llm_convertible", llm_conv_pkg)
    monkeypatch.setitem(sys.modules, "openhands.sdk.event.llm_convertible.message", message_mod)
    monkeypatch.setitem(sys.modules, "openhands.sdk.event.llm_convertible.action", action_mod)
    return captured


class _FakeConversation:
    """Minimal conversation for extract_final_text."""

    def __init__(self, events: list[object]) -> None:
        self.state = types.SimpleNamespace(events=events)


def test_flyout_title_repairs_legacy_preview_and_returns_full_first_message() -> None:
    """Flyout header expands old 48-char preview titles from the first user message."""
    session_id = str(uuid.uuid4())
    long_message = (
        "how do i create scripts in this app? can you give an example for a pre request script?"
    )
    legacy_title = long_message[: _TITLE_PREVIEW_LEN - 1] + "…"
    create_session(session_id=session_id, title=legacy_title, model_id="m1", mode="agent")
    AiChatSessionService.record_user_message(session_id, long_message)

    display = AiChatSessionService.flyout_title_for_session(session_id)
    assert display == long_message
    row = AiChatSessionService.get_session(session_id)
    assert row is not None
    assert row["title"] == long_message


def test_flyout_title_respects_user_rename() -> None:
    """After manual rename, flyout shows the stored title instead of the first message."""
    session_id = str(uuid.uuid4())
    create_session(session_id=session_id, title="Custom", model_id="m1", mode="agent")
    AiChatSessionService.record_user_message(session_id, "A much longer first user message here")

    assert AiChatSessionService.flyout_title_for_session(session_id, user_renamed=True) == "Custom"


def test_new_session_title_stores_full_first_message() -> None:
    """Initial session title keeps the full first user message (not a 48-char preview)."""
    long_message = (
        "how do i create scripts in this app? can you give an example for a pre request script?"
    )
    session = AiChatSessionService.new_session(_entry(), "agent", first_message=long_message)
    assert session["title"] == long_message


def test_new_session_and_messages() -> None:
    """Session CRUD and message recording round-trip."""
    session = AiChatSessionService.new_session(_entry(), "agent", first_message="Hello world")
    sid = session["id"]
    assert session["model_id"] == "id1"
    assert session["agent_id"] == DEFAULT_AGENT_ID

    user = AiChatSessionService.record_user_message(sid, "Hello")
    assert user["role"] == "user"
    assistant = AiChatSessionService.record_assistant_message(
        sid,
        "Hi there",
        thinking="trace",
        thinking_duration_seconds=4,
    )
    assert assistant["role"] == "assistant"
    assert assistant["thinking_duration_seconds"] == 4

    messages = AiChatSessionService.get_messages(sid)
    assert len(messages) == 2
    listed = AiChatSessionService.list_sessions()
    assert any(s["id"] == sid for s in listed)


def test_extract_final_text_returns_latest_agent_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``extract_final_text`` scans events for the latest agent message."""
    _install_fake_sdk(monkeypatch)
    from openhands.sdk.event.llm_convertible.message import MessageEvent

    conv = _FakeConversation(
        [
            MessageEvent(source="user", text="ignored"),  # type: ignore[call-arg]
            MessageEvent(source="agent", text="first"),  # type: ignore[call-arg]
            MessageEvent(source="agent", text="final answer"),  # type: ignore[call-arg]
        ]
    )
    assert AiChatSessionService.extract_final_text(conv) == "final answer"  # type: ignore[arg-type]


def test_build_conversation_passes_composer_to_llm(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """``build_conversation`` forwards composer context settings to ``build_llm``."""
    captured = _install_fake_sdk(monkeypatch)
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )

    import services.ai.llm_service as llm_svc

    class _Store:
        backend_id = "noop"

        def put(self, r: str, s: str) -> None: ...

        def get(self, r: str) -> str | None:
            return None

        def delete(self, r: str) -> None: ...

    monkeypatch.setattr(llm_svc, "get_default_store", lambda: _Store())

    session_id = str(uuid.uuid4())
    conv = AiChatSessionService.build_conversation(
        session_id,
        _entry(
            provider="ollama",
            model="ollama/qwen3:8b",
            base_url="",
            auth_kind="none",
            auth_ref="",
            thinking=True,
        ),
        DEFAULT_AGENT_ID,
        composer={
            "run_context_tokens": 8192,
            "thinking_enabled": "off",
            "reasoning_effort": "medium",
        },
    )
    llm = captured["agent_kw"]["llm"]
    assert llm.litellm_extra_body == {"num_ctx": 8192, "think": False}
    assert llm.num_retries == 0
    assert conv is not None


def test_build_conversation_passes_sdk_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """``build_conversation`` uses BASE persistence_dir, UUID id, stream=True."""
    captured = _install_fake_sdk(monkeypatch)
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )

    import services.ai.llm_service as llm_svc

    class _Store:
        backend_id = "noop"

        def put(self, r: str, s: str) -> None: ...

        def get(self, r: str) -> str | None:
            return None

        def delete(self, r: str) -> None: ...

    monkeypatch.setattr(llm_svc, "get_default_store", lambda: _Store())

    session_id = str(uuid.uuid4())
    token_calls: list[str] = []
    event_calls: list[str] = []

    def token_cb(_chunk: object) -> None:
        token_calls.append("t")

    def event_cb(_event: object) -> None:
        event_calls.append("e")

    conv = AiChatSessionService.build_conversation(
        session_id,
        _entry(),
        DEFAULT_AGENT_ID,
        callbacks=[event_cb],
        token_callbacks=[token_cb],
    )

    kw = captured["conversation_kw"]
    assert kw["delete_on_close"] is False
    assert kw["conversation_id"] == uuid.UUID(session_id)
    assert str(kw["persistence_dir"]).endswith("ai_conversations")
    assert kw["token_callbacks"] == [token_cb]
    assert kw["callbacks"] == [event_cb]

    agent_kw = captured["agent_kw"]
    assert len(agent_kw["tools"]) == 1
    assert agent_kw["tools"][0].name == "postmark_wiki_query"
    assert agent_kw["system_prompt"]
    assert "postmark_wiki_query" in agent_kw["system_prompt"]
    assert agent_kw["include_default_tools"] == []
    assert agent_kw["condenser"] is not None
    assert agent_kw["condenser"].max_size == CHAT_CONDENSER_MAX_EVENTS
    assert agent_kw["condenser"].max_tokens == condenser_max_tokens(128_000)
    assert agent_kw["condenser"].minimum_progress == CHAT_CONDENSER_MINIMUM_PROGRESS
    assert agent_kw["llm"].stream is True
    assert agent_kw["condenser"].llm.stream is False
    assert kw["max_iteration_per_run"] == 5
    assert conv is not None


def test_generate_session_title_uses_first_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Title generation reads the first user message; no tools, thinking off."""
    import services.ai.chat.session_service as svc_mod

    captured: dict[str, object] = {}

    def _fake_build_llm(*_args: object, **kwargs: object) -> object:
        captured["thinking_enabled"] = kwargs.get("thinking_enabled")
        captured["reasoning_effort"] = kwargs.get("reasoning_effort")
        captured["stream"] = kwargs.get("stream")
        captured["usage_id"] = kwargs.get("usage_id")
        return object()

    monkeypatch.setattr(svc_mod.AiLlmService, "build_llm", staticmethod(_fake_build_llm))

    import openhands.sdk.conversation.title_utils as title_utils

    def _fake_title(message: str, _llm: object, max_length: int = 50) -> str:
        _ = max_length
        return f"Title: {message[:12]}"

    monkeypatch.setattr(title_utils, "generate_title_from_message", _fake_title)

    session_id = str(uuid.uuid4())
    create_session(session_id=session_id, title="x", model_id="m1", mode="agent")
    AiChatSessionService.record_user_message(session_id, "How do I create a collection?")

    title = AiChatSessionService.generate_session_title(session_id, _entry())
    assert title == "Title: How do I cre"
    assert captured["thinking_enabled"] == "off"
    assert captured["reasoning_effort"] == "off"
    assert captured["stream"] is False
    # Chat usage prefix so Ollama tuning (num_retries=0, ollama_chat routing) applies.
    assert str(captured["usage_id"]).startswith("postmark-chat")


def test_generate_session_title_requires_user_message() -> None:
    """No user message raises a clear error before any SDK call."""
    session_id = str(uuid.uuid4())
    create_session(session_id=session_id, title="x", model_id="m1", mode="agent")
    with pytest.raises(ValueError, match="No user message"):
        AiChatSessionService.generate_session_title(session_id, _entry())


def test_build_conversation_uses_model_context_for_condenser(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Condenser max_tokens follows the effective run context window."""
    captured = _install_fake_sdk(monkeypatch)
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )

    import services.ai.llm_service as llm_svc

    class _Store:
        backend_id = "noop"

        def put(self, r: str, s: str) -> None: ...

        def get(self, r: str) -> str | None:
            return None

        def delete(self, r: str) -> None: ...

    monkeypatch.setattr(llm_svc, "get_default_store", lambda: _Store())

    session_id = str(uuid.uuid4())
    AiChatSessionService.build_conversation(
        session_id,
        _entry(context=32_000, context_limit=24_000),
        DEFAULT_AGENT_ID,
    )

    condenser = captured["agent_kw"]["condenser"]
    assert condenser.max_tokens == condenser_max_tokens(24_000)
    assert condenser.minimum_progress == CHAT_CONDENSER_MINIMUM_PROGRESS


def test_resolve_restore_session_id_returns_none_when_unset() -> None:
    """An explicit **New chat** clear leaves the composer blank on restart."""
    AiConfig.set_chat_session_id("")
    assert AiConfig.is_chat_session_restore_cleared()
    assert AiChatSessionService.resolve_restore_session_id() is None


def test_resolve_restore_session_id_falls_back_when_never_persisted() -> None:
    """Legacy sessions with no stored id still reopen the latest chat."""
    session_id = str(uuid.uuid4())
    create_session(session_id=session_id, title="Latest", model_id="m1", mode="agent")
    assert AiConfig.get_chat_session_id() == ""
    assert not AiConfig.is_chat_session_restore_cleared()
    assert AiChatSessionService.resolve_restore_session_id() == session_id


def test_resolve_restore_session_id_returns_stored() -> None:
    """A valid stored id is restored on startup."""
    session_id = str(uuid.uuid4())
    create_session(session_id=session_id, title="Saved", model_id="m1", mode="agent")
    AiConfig.set_chat_session_id(session_id)
    assert AiChatSessionService.resolve_restore_session_id() == session_id


def test_resolve_restore_session_id_falls_back_when_deleted() -> None:
    """A deleted stored id falls back to the most recent remaining session."""
    kept_id = str(uuid.uuid4())
    deleted_id = str(uuid.uuid4())
    create_session(session_id=deleted_id, title="Gone", model_id=None, mode="agent")
    create_session(session_id=kept_id, title="Kept", model_id=None, mode="ask")
    delete_session(deleted_id)
    AiConfig.set_chat_session_id(deleted_id)
    assert AiChatSessionService.resolve_restore_session_id() == kept_id


def test_record_assistant_message_persists_turn_usage_delta() -> None:
    """Assistant rows store per-turn token deltas derived from SDK cumulative usage."""
    session_id = str(uuid.uuid4())
    create_session(session_id=session_id, title="Usage", model_id="m1", mode="agent")
    AiChatSessionService.record_user_message(session_id, "Hi")
    first = AiChatSessionService.record_assistant_message(
        session_id,
        "Hello",
        model_id="m1",
        usage={"prompt_tokens": 100, "completion_tokens": 40, "reasoning_tokens": 0},
    )
    assert first["prompt_tokens"] == 100
    assert first["completion_tokens"] == 40
    second = AiChatSessionService.record_assistant_message(
        session_id,
        "Again",
        model_id="m1",
        usage={"prompt_tokens": 250, "completion_tokens": 90, "reasoning_tokens": 10},
    )
    assert second["prompt_tokens"] == 150
    assert second["completion_tokens"] == 50
    assert second["reasoning_tokens"] == 10


def test_record_assistant_message_persists_model_label() -> None:
    """Assistant rows store the human-readable model label at send time."""
    session_id = str(uuid.uuid4())
    create_session(session_id=session_id, title="Label", model_id="m1", mode="agent")
    row = AiChatSessionService.record_assistant_message(
        session_id,
        "Hi",
        model_id="m1",
        model_label="GPT-4o",
    )
    assert row["model_id"] == "m1"
    assert row["model_label"] == "GPT-4o"
    loaded = AiChatSessionService.get_messages(session_id)[0]
    assert loaded["model_label"] == "GPT-4o"


def test_fork_session_at_message_copies_prefix() -> None:
    """Forking creates a new session with messages up to the fork point."""
    source_id = str(uuid.uuid4())
    create_session(session_id=source_id, title="Source", model_id="m1", mode="agent")
    AiChatSessionService.record_user_message(source_id, "One")
    assistant = AiChatSessionService.record_assistant_message(source_id, "A1", model_id="m1")
    AiChatSessionService.record_user_message(source_id, "Two")
    forked = AiChatSessionService.fork_session_at_message(source_id, assistant["id"])
    assert forked is not None
    assert forked["id"] != source_id
    assert forked["title"] == "Source (1)"
    messages = AiChatSessionService.get_messages(forked["id"])
    assert len(messages) == 2
    assert messages[-1]["content"] == "A1"


def test_fork_session_rewrites_sdk_conversation_id(tmp_path, monkeypatch) -> None:
    """Copied SDK disk state must use the fork session id when resumed."""
    import json

    from database import data_paths

    monkeypatch.setattr(data_paths, "user_ai_conversations_root", lambda: tmp_path)

    source_id = str(uuid.uuid4())
    create_session(session_id=source_id, title="Source", model_id="m1", mode="agent")
    AiChatSessionService.record_user_message(source_id, "One")
    assistant = AiChatSessionService.record_assistant_message(source_id, "A1", model_id="m1")

    source_disk = session_disk_dir(source_id)
    source_disk.mkdir(parents=True, exist_ok=True)
    (source_disk / "base_state.json").write_text(
        json.dumps({"id": source_id, "persistence_dir": str(source_disk)}),
        encoding="utf-8",
    )

    forked = AiChatSessionService.fork_session_at_message(source_id, assistant["id"])
    assert forked is not None

    fork_disk = session_disk_dir(forked["id"])
    data = json.loads((fork_disk / "base_state.json").read_text(encoding="utf-8"))
    assert data["id"] == forked["id"]
    assert data["persistence_dir"] == str(fork_disk)


def test_fork_session_title_increments_for_same_family() -> None:
    """Each fork from the same title family gets the next ``(N)`` suffix."""
    source_id = str(uuid.uuid4())
    create_session(session_id=source_id, title="Planning", model_id="m1", mode="agent")
    AiChatSessionService.record_user_message(source_id, "One")
    assistant = AiChatSessionService.record_assistant_message(source_id, "A1", model_id="m1")

    first = AiChatSessionService.fork_session_at_message(source_id, assistant["id"])
    assert first is not None
    assert first["title"] == "Planning (1)"

    second = AiChatSessionService.fork_session_at_message(source_id, assistant["id"])
    assert second is not None
    assert second["title"] == "Planning (2)"

    first_messages = AiChatSessionService.get_messages(first["id"])
    third = AiChatSessionService.fork_session_at_message(
        first["id"],
        first_messages[-1]["id"],
    )
    assert third is not None
    assert third["title"] == "Planning (3)"


def test_fork_session_at_user_message_excludes_user_row() -> None:
    """User fork copies prefix before the user message and returns composer draft."""
    source_id = str(uuid.uuid4())
    create_session(session_id=source_id, title="Source", model_id="m1", mode="agent")
    AiChatSessionService.record_user_message(source_id, "One")
    AiChatSessionService.record_assistant_message(source_id, "A1", model_id="m1")
    user_two = AiChatSessionService.record_user_message(source_id, "Two")
    result = AiChatSessionService.fork_session_at_user_message(source_id, user_two["id"])
    assert result is not None
    forked = result["session"]
    assert result["composer_draft"] == "Two"
    assert forked["id"] != source_id
    messages = AiChatSessionService.get_messages(forked["id"])
    assert len(messages) == 2
    assert messages[-1]["content"] == "A1"


def test_fork_session_at_user_message_first_message_empty_transcript() -> None:
    """Forking from the first user message yields an empty transcript and draft text."""
    source_id = str(uuid.uuid4())
    create_session(session_id=source_id, title="Fresh", model_id="m1", mode="agent")
    user = AiChatSessionService.record_user_message(source_id, "Hello")
    result = AiChatSessionService.fork_session_at_user_message(source_id, user["id"])
    assert result is not None
    assert result["composer_draft"] == "Hello"
    messages = AiChatSessionService.get_messages(result["session"]["id"])
    assert messages == []


def test_edit_user_message_and_rewind_truncates_tail() -> None:
    """Editing a user message removes later rows and updates content in place."""
    source_id = str(uuid.uuid4())
    create_session(session_id=source_id, title="Source", model_id="m1", mode="agent")
    user_one = AiChatSessionService.record_user_message(source_id, "One")
    AiChatSessionService.record_assistant_message(source_id, "A1", model_id="m1")
    AiChatSessionService.record_user_message(source_id, "Two")
    snapshot: UserMessageSendSnapshot = {
        "send_model_id": "m1",
        "send_mode": "plan",
        "send_agent_id": "postmark-assistant",
        "send_reasoning_effort": None,
        "send_thinking_enabled": None,
        "send_run_context_tokens": None,
    }
    ok = AiChatSessionService.edit_user_message_and_rewind(
        source_id,
        user_one["id"],
        "One edited",
        snapshot,
    )
    assert ok is True
    messages = AiChatSessionService.get_messages(source_id)
    assert len(messages) == 1
    assert messages[0]["content"] == "One edited"
    assert messages[0]["send_mode"] == "plan"
    session = AiChatSessionService.get_session(source_id)
    assert session is not None
    assert session["mode"] == "plan"
