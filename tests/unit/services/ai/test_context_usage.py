"""Tests for AI chat context-usage accounting."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from database.models.ai_chat.ai_chat_repository import append_message, create_session
from services.ai.ai_config import AiModelEntry
from services.ai.chat.compaction import (
    CHAT_CONDENSER_MAX_EVENTS,
    CHAT_CONDENSER_MINIMUM_PROGRESS,
    condenser_max_tokens,
)
from services.ai.chat.context_usage import (
    ContextUsageService,
    SdkViewSnapshot,
    build_breakdown,
    build_breakdown_for_session,
    collect_compaction_diagnostics,
    count_summarized_events,
    estimate_text_tokens,
)
from services.ai.chat.session_service import AiChatMessageDict


def _entry(**overrides: object) -> AiModelEntry:
    entry: AiModelEntry = {
        "id": "m1",
        "provider": "openai",
        "label": "GPT-4o",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "context": 128_000,
    }
    entry.update(overrides)  # type: ignore[typeddict-item]
    return entry


def test_build_breakdown_keeps_cursor_eight_buckets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Breakdown always includes all Cursor buckets and sums their tokens."""
    monkeypatch.setattr(
        "services.ai.chat.context_usage.measure_sdk_view",
        lambda *_args, **_kw: None,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_system_and_tools",
        lambda _agent_id, _model, **_kw: (5, 3),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_transcript_messages",
        lambda _messages, _model, **_kw: 11,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_summarized_events",
        lambda _session_id, _model: (7, True),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.estimate_text_tokens",
        lambda text, _model, **_kw: 2 if text == "draft" else 4,
    )
    monkeypatch.setattr(
        "services.ai.chat.subagent_transcript.count_session_subagent_context_tokens",
        lambda *_args, **_kw: 0,
    )

    breakdown = build_breakdown(
        session_id="sess-1",
        messages=[],
        draft_text="draft",
        streaming_thinking="thinking",
        streaming_content="reply",
        entry=_entry(context=100),
        agent_id="postmark-assistant",
    )

    ids = [category["id"] for category in breakdown["categories"]]
    assert ids == [
        "system_prompt",
        "tools",
        "rules",
        "skills",
        "mcp",
        "subagents",
        "summarized_conversation",
        "conversation",
    ]
    token_by_id = {category["id"]: category["tokens"] for category in breakdown["categories"]}
    assert token_by_id["system_prompt"] == 5
    assert token_by_id["tools"] == 3
    assert token_by_id["summarized_conversation"] == 7
    assert token_by_id["conversation"] == 17
    assert breakdown["used_tokens"] == 32
    assert breakdown["draft_tokens"] == 2
    assert breakdown["has_summarized"] is True
    assert breakdown["is_estimated"] is True


def test_build_breakdown_uses_sdk_metrics_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider metrics override the estimated conversation bucket after a run."""
    monkeypatch.setattr(
        "services.ai.chat.context_usage.measure_sdk_view",
        lambda *_args, **_kw: None,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_system_and_tools",
        lambda _agent_id, _model, **_kw: (5, 3),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_transcript_messages",
        lambda _messages, _model, **_kw: 99,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_summarized_events",
        lambda _session_id, _model: (7, True),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.estimate_text_tokens", lambda *_args, **_kw: 0
    )
    monkeypatch.setattr(
        "services.ai.chat.subagent_transcript.count_session_subagent_context_tokens",
        lambda *_args, **_kw: 0,
    )

    breakdown = build_breakdown(
        session_id="sess-1",
        messages=[],
        entry=_entry(context=100),
        agent_id="postmark-assistant",
        sdk_metrics={
            "prompt_tokens": 40,
            "completion_tokens": 10,
            "reasoning_tokens": 2,
        },
    )

    token_by_id = {category["id"]: category["tokens"] for category in breakdown["categories"]}
    assert token_by_id["conversation"] == 37
    assert breakdown["used_tokens"] == 52
    assert breakdown["is_estimated"] is False


def test_build_breakdown_prefers_sdk_view_when_events_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persisted OpenHands View tokens override a larger SQLite transcript estimate."""
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_system_and_tools",
        lambda _agent_id, _model, **_kw: (5, 0),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_transcript_messages",
        lambda _messages, _model, **_kw: 900,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.estimate_text_tokens",
        lambda *_args, **_kw: 0,
    )
    monkeypatch.setattr(
        "services.ai.chat.subagent_transcript.count_session_subagent_context_tokens",
        lambda *_args, **_kw: 0,
    )
    sdk_snapshot = SdkViewSnapshot(
        event_count=2,
        view_tokens=120,
        summarized_tokens=10,
        has_summarized=True,
        condenser_max_size=CHAT_CONDENSER_MAX_EVENTS,
        condenser_max_tokens=condenser_max_tokens(1000),
        condenser_minimum_progress=CHAT_CONDENSER_MINIMUM_PROGRESS,
        condensation_reasons=["tokens"],
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.measure_sdk_view",
        lambda _session_id, _entry: sdk_snapshot,
    )
    messages: list[AiChatMessageDict] = [
        {"id": idx, "session_id": "sess-1", "role": "user", "content": "x", "created_at": ""}
        for idx in range(6)
    ]

    breakdown = build_breakdown(
        session_id="sess-1",
        messages=messages,
        entry=_entry(context=1000),
        agent_id="postmark-assistant",
    )

    token_by_id = {category["id"]: category["tokens"] for category in breakdown["categories"]}
    assert token_by_id["summarized_conversation"] == 10
    assert token_by_id["conversation"] == 105
    assert token_by_id["subagents"] == 0
    assert breakdown["used_tokens"] == 120
    assert breakdown["is_estimated"] is False
    assert breakdown["used_sqlite_fallback"] is False
    assert breakdown["sdk_event_count"] == 2
    assert breakdown["sdk_view_tokens"] == 120
    assert breakdown["transcript_larger_than_sdk"] is True
    assert breakdown["condensation_reasons"] == ["tokens"]


def test_build_breakdown_attributes_subagent_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completed subagent disk answers fill the Subagents context bucket."""
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_system_and_tools",
        lambda _agent_id, _model, **_kw: (5, 3),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_transcript_messages",
        lambda _messages, _model, **_kw: 40,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_summarized_events",
        lambda _session_id, _model: (0, False),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.estimate_text_tokens",
        lambda *_args, **_kw: 0,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.measure_sdk_view",
        lambda *_args, **_kw: None,
    )
    monkeypatch.setattr(
        "services.ai.chat.subagent_transcript.count_session_subagent_context_tokens",
        lambda *_args, **_kw: 12,
    )

    breakdown = build_breakdown(
        session_id="sess-1",
        messages=[],
        entry=_entry(context=128_000),
        agent_id="postmark-assistant",
    )

    token_by_id = {category["id"]: category["tokens"] for category in breakdown["categories"]}
    assert token_by_id["subagents"] == 12
    # Conversation excludes the subagent slice to avoid double-counting.
    assert token_by_id["conversation"] == 28
    assert breakdown["used_tokens"] == 5 + 3 + 12 + 28


def test_collect_compaction_diagnostics_reports_sqlite_sdk_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Diagnostics expose SQLite-vs-SDK counts and condenser thresholds."""
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_system_and_tools",
        lambda _agent_id, _model, **_kw: (0, 0),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_transcript_messages",
        lambda _messages, _model, **_kw: 500,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.estimate_text_tokens",
        lambda *_args, **_kw: 0,
    )
    sdk_snapshot = SdkViewSnapshot(
        event_count=1,
        view_tokens=100,
        summarized_tokens=0,
        has_summarized=False,
        condenser_max_size=CHAT_CONDENSER_MAX_EVENTS,
        condenser_max_tokens=condenser_max_tokens(1000),
        condenser_minimum_progress=CHAT_CONDENSER_MINIMUM_PROGRESS,
        condensation_reasons=["events"],
    )

    def _mock_measure_sdk_view(_session_id: str, _entry: object, **_kw: object) -> SdkViewSnapshot:
        return sdk_snapshot

    monkeypatch.setattr(
        "services.ai.chat.context_usage.measure_sdk_view",
        _mock_measure_sdk_view,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage_sdk.measure_sdk_view",
        _mock_measure_sdk_view,
    )
    session_id = str(uuid.uuid4())
    messages: list[AiChatMessageDict] = [
        {
            "id": idx,
            "session_id": session_id,
            "role": "user",
            "content": "x",
            "created_at": "",
        }
        for idx in range(4)
    ]

    diagnostics = collect_compaction_diagnostics(
        session_id=session_id,
        messages=messages,
        entry=_entry(context=1000),
        agent_id="postmark-assistant",
        run_context_tokens=1000,
    )

    assert diagnostics["sqlite_message_count"] == 4
    assert diagnostics["sqlite_transcript_tokens"] == 500
    assert diagnostics["sdk_event_count"] == 1
    assert diagnostics["sdk_view_tokens"] == 100
    assert diagnostics["transcript_larger_than_sdk"] is True
    assert diagnostics["used_sqlite_fallback"] is False
    assert diagnostics["condenser_max_size"] == CHAT_CONDENSER_MAX_EVENTS
    assert diagnostics["condenser_max_tokens"] == condenser_max_tokens(1000)
    assert diagnostics["condenser_minimum_progress"] == CHAT_CONDENSER_MINIMUM_PROGRESS
    assert diagnostics["condensation_reasons"] == {"events"}


def test_estimate_text_tokens_falls_back_to_character_heuristic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tokenizer failures fall back to the plan's simple char-based estimate."""
    import services.ai.chat.context_usage as mod

    def _boom(**_kwargs: object) -> int:
        raise RuntimeError("tokenizer unavailable")

    monkeypatch.setattr(mod, "_litellm_token_counter", _boom)
    assert estimate_text_tokens("abcdefgh", "openai/gpt-4o") == 2


def test_build_breakdown_for_session_counts_full_sqlite_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full session rows are counted, not just the visible transcript window."""
    session_id = str(uuid.uuid4())
    create_session(session_id=session_id, title="Long", model_id="m1", mode="agent")
    append_message(session_id=session_id, role="user", content="user 1")
    append_message(
        session_id=session_id,
        role="assistant",
        content="assistant 1",
        thinking="trace 1",
    )
    append_message(session_id=session_id, role="user", content="user 2")

    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_system_and_tools",
        lambda _agent_id, _model, **_kw: (0, 0),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_summarized_events",
        lambda _session_id, _model: (0, False),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.estimate_text_tokens",
        lambda text, _model, **_kw: 1 if text.strip() else 0,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.measure_sdk_view",
        lambda *_args, **_kw: None,
    )

    breakdown = build_breakdown_for_session(
        session_id,
        entry=_entry(context=20),
        agent_id="postmark-assistant",
    )

    token_by_id = {category["id"]: category["tokens"] for category in breakdown["categories"]}
    assert token_by_id["conversation"] == 4
    assert breakdown["used_tokens"] == 4


def test_count_summarized_events_reads_condensation_from_sdk_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Condensation summaries on disk populate the summarized bucket."""
    from openhands.sdk.event.condenser import Condensation

    session_id = str(uuid.uuid4())
    disk = tmp_path / "ai_conversations" / uuid.UUID(session_id).hex / "events"
    disk.mkdir(parents=True)
    event = Condensation(
        forgotten_event_ids={"a"},
        summary="older turns summary",
        summary_offset=1,
        llm_response_id="llm-1",
    )
    (disk / f"event-00000-{event.id}.json").write_text(
        event.model_dump_json(exclude_none=True),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.session_disk_dir",
        lambda _session_id: tmp_path / "ai_conversations" / uuid.UUID(session_id).hex,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.estimate_text_tokens",
        lambda text, _model, **_kw: 6 if "summary" in text else 0,
    )

    tokens, has_summarized = count_summarized_events(session_id, "openai/gpt-4o")
    assert tokens == 6
    assert has_summarized is True


def test_context_usage_service_exposes_build_breakdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """The service facade delegates to the module-level breakdown builder."""
    monkeypatch.setattr(
        "services.ai.chat.context_usage.build_breakdown",
        lambda **kwargs: {
            "used_tokens": 1,
            "total_tokens": 2,
            "categories": [],
            "has_summarized": False,
            "is_estimated": True,
            **kwargs,
        },
    )

    breakdown = ContextUsageService.build_breakdown(
        session_id=None,
        messages=[],
        entry=_entry(context=2),
        agent_id="postmark-assistant",
    )
    assert breakdown["used_tokens"] == 1


def test_build_breakdown_prefers_sdk_view_over_sqlite_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK View token counts become authoritative when an event log exists."""
    from services.ai.chat.context_usage_sdk import SdkViewSnapshot

    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_system_and_tools",
        lambda _agent_id, _model, **_kw: (5, 3),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_transcript_messages",
        lambda _messages, _model, **_kw: 200,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.measure_sdk_view",
        lambda *_args, **_kw: SdkViewSnapshot(
            event_count=12,
            view_tokens=80,
            summarized_tokens=7,
            has_summarized=True,
            condenser_max_size=45,
            condenser_max_tokens=72,
            condenser_minimum_progress=0.05,
            condensation_reasons=["max_tokens"],
        ),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.estimate_text_tokens", lambda *_args, **_kw: 0
    )

    breakdown = build_breakdown(
        session_id="sess-sdk",
        messages=[
            {"id": 1, "session_id": "sess-sdk", "role": "user", "content": "x", "created_at": ""}
        ],
        entry=_entry(context=100),
        agent_id="postmark-assistant",
    )

    token_by_id = {category["id"]: category["tokens"] for category in breakdown["categories"]}
    assert token_by_id["conversation"] == 65
    assert breakdown["used_tokens"] == 80
    assert breakdown["is_estimated"] is False
    assert breakdown["used_sqlite_fallback"] is False
    assert breakdown["sdk_view_tokens"] == 80


def test_build_breakdown_flags_transcript_larger_than_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Diagnostics mark SQLite-heavy sessions when SDK events lag behind."""
    from services.ai.chat.context_usage_sdk import SdkViewSnapshot

    messages: list[AiChatMessageDict] = [
        {
            "id": index,
            "session_id": "sess",
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"message {index}",
            "created_at": "",
        }
        for index in range(8)
    ]
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_system_and_tools",
        lambda *_args, **_kw: (0, 0),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_transcript_messages",
        lambda _messages, _model, **_kw: 500,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.measure_sdk_view",
        lambda *_args, **_kw: SdkViewSnapshot(
            event_count=2,
            view_tokens=40,
            summarized_tokens=0,
            has_summarized=False,
            condenser_max_size=45,
            condenser_max_tokens=72,
            condenser_minimum_progress=0.05,
            condensation_reasons=[],
        ),
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.estimate_text_tokens", lambda *_args, **_kw: 0
    )

    breakdown = build_breakdown(
        session_id="sess",
        messages=messages,
        entry=_entry(context=100),
        agent_id="postmark-assistant",
    )

    assert breakdown["transcript_larger_than_sdk"] is True
    assert breakdown["sqlite_message_count"] == 8
    assert breakdown["sdk_event_count"] == 2


def test_metrics_from_conversation_returns_turn_cost_delta() -> None:
    """Per-turn USD is the SDK accumulated-cost delta since run start."""
    from types import SimpleNamespace

    from services.ai.chat.context_usage import metrics_from_conversation

    usage = SimpleNamespace(
        prompt_tokens=3900,
        completion_tokens=2280,
        reasoning_tokens=432,
        per_turn_token=6180,
    )
    metrics = SimpleNamespace(accumulated_token_usage=usage, accumulated_cost=0.0097)
    stats = SimpleNamespace(
        get_metrics_for_usage=lambda _usage_id: metrics,
    )
    conv = SimpleNamespace(conversation_stats=stats)
    result = metrics_from_conversation(
        conv,
        "sess-1",
        baseline_accumulated_cost=0.0073,
    )
    assert result is not None
    assert abs(float(result["turn_cost_usd"]) - 0.0024) < 1e-12
    assert result["prompt_tokens"] == 3900
