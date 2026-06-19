"""Tests for per-message usage helpers."""

from __future__ import annotations

from services.ai.ai_config import AiModelEntry
from services.ai.chat.context_usage import ContextUsageSdkMetrics
from services.ai.chat.message_usage import (
    SessionSpendBreakdown,
    assistant_turn_cost_for_message,
    effective_assistant_model_id,
    entry_for_model_id,
    format_assistant_footer_label,
    format_context_ring_tooltip,
    format_spend_pill_label,
    format_spend_tab_label,
    message_turn_cost_usd,
    pricing_model_id_for_assistant_message,
    resolve_model_display_name,
    resolve_turn_model_id,
    session_spend_breakdown,
    spend_pill_visible,
    sum_assistant_turn_costs,
    turn_usage_delta,
)
from services.ai.chat.session_service import AiChatMessageDict


def _entry(**kw: object) -> AiModelEntry:
    base: AiModelEntry = {
        "id": "m1",
        "provider": "openai",
        "label": "GPT-4o",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "input_cost_per_token": 0.0000025,
        "output_cost_per_token": 0.00001,
    }
    base.update(kw)  # type: ignore[typeddict-item]
    return base


def test_format_assistant_footer_label_prefers_stored_cost_usd() -> None:
    """Persisted SDK turn cost wins over token-rate estimates."""
    text = format_assistant_footer_label(
        _entry(),
        "m1",
        prompt_tokens=1000,
        completion_tokens=200,
        reasoning_tokens=0,
        cost_usd=0.0097,
    )
    assert text == "GPT-4o · $0.0097"


def test_assistant_turn_cost_for_message_uses_stored_cost_usd() -> None:
    """Spend rollups prefer SDK-persisted per-turn USD."""
    messages: list[AiChatMessageDict] = [
        _msg(id=1, role="user", send_model_id="m1"),
        _msg(
            id=2,
            role="assistant",
            prompt_tokens=1000,
            completion_tokens=200,
            cost_usd=0.0097,
        ),
    ]
    _model_id, cost = assistant_turn_cost_for_message(
        messages[1],
        messages=messages,
        msg_index=1,
    )
    assert cost == 0.0097


def test_turn_usage_delta_subtracts_previous_cumulative() -> None:
    """Turn delta is SDK cumulative minus prior assistant totals."""
    sdk = ContextUsageSdkMetrics(
        prompt_tokens=1200,
        completion_tokens=300,
        reasoning_tokens=50,
    )
    previous = {"prompt_tokens": 1000, "completion_tokens": 200, "reasoning_tokens": 0}
    delta = turn_usage_delta(sdk, previous)
    assert delta["prompt_tokens"] == 200
    assert delta["completion_tokens"] == 100
    assert delta["reasoning_tokens"] == 50


def test_message_turn_cost_usd_uses_input_and_output_rates() -> None:
    """Cost combines prompt input tokens and completion/reasoning output tokens."""
    cost = message_turn_cost_usd(
        _entry(),
        prompt_tokens=1000,
        completion_tokens=200,
        reasoning_tokens=0,
    )
    assert cost is not None
    assert abs(cost - (1000 * 0.0000025 + 200 * 0.00001)) < 1e-9


def test_format_assistant_footer_label_includes_cost_when_priced() -> None:
    """Footer label shows model name and USD cost when pricing exists."""
    text = format_assistant_footer_label(
        _entry(),
        "m1",
        prompt_tokens=1000,
        completion_tokens=200,
        reasoning_tokens=0,
    )
    assert text.startswith("GPT-4o · $")


def test_resolve_model_display_name_prefers_message_model_id(monkeypatch) -> None:
    """Footer labels follow the persisted message model, not a stale entry."""
    oss = _entry(id="oss", label="gpt-oss")
    mini = _entry(id="mini", label="gpt-5.4-mini")

    monkeypatch.setattr(
        "services.ai.chat.message_usage.AiConfig.get_models",
        lambda: [oss, mini],
    )

    assert resolve_model_display_name("mini", oss) == "gpt-5.4-mini"
    assert entry_for_model_id("mini") == mini


def test_effective_assistant_model_id_falls_back_to_session() -> None:
    """Rows without per-message model ids use the session default."""
    assert effective_assistant_model_id(None, "sess-model") == "sess-model"
    assert effective_assistant_model_id("msg-model", "sess-model") == "msg-model"


def test_resolve_model_display_name_uses_raw_id_when_entry_missing() -> None:
    """Orphan model ids still show a label instead of Unknown model."""
    assert resolve_model_display_name("deleted-model-id", None) == "deleted-model-id"


def test_format_assistant_footer_label_uses_persisted_model_label() -> None:
    """Persisted model labels win over stale entry lookups."""
    text = format_assistant_footer_label(
        _entry(id="wrong", label="wrong"),
        "m1",
        model_label="gpt-oss",
        prompt_tokens=0,
        completion_tokens=0,
        reasoning_tokens=0,
    )
    assert text == "gpt-oss"


def test_format_assistant_footer_label_without_pricing_omits_cost() -> None:
    """Footer label falls back to model name when pricing is unknown."""
    entry = _entry()
    del entry["input_cost_per_token"]  # type: ignore[misc]
    del entry["output_cost_per_token"]  # type: ignore[misc]
    text = format_assistant_footer_label(
        entry,
        "m1",
        prompt_tokens=1000,
        completion_tokens=200,
        reasoning_tokens=0,
    )
    assert text == "GPT-4o"


def _msg(**kw: object) -> AiChatMessageDict:
    base: AiChatMessageDict = {
        "id": 1,
        "session_id": "sess",
        "role": "assistant",
        "content": "hi",
        "created_at": "2026-01-01T00:00:00Z",
    }
    base.update(kw)  # type: ignore[typeddict-item]
    return base


def test_session_spend_breakdown_groups_by_model(monkeypatch) -> None:
    """Assistant turns roll up per configured model."""
    openai_a = _entry(id="m1", provider="openai", auth_ref="a", label="GPT-4o")
    openai_b = _entry(id="m1b", provider="openai", auth_ref="a", label="GPT-4o mini")
    anthropic = _entry(
        id="m2",
        provider="anthropic",
        auth_ref="b",
        label="Claude",
        model="anthropic/claude-3",
    )
    monkeypatch.setattr(
        "services.ai.chat.message_usage.AiConfig.get_models",
        lambda: [openai_a, openai_b, anthropic],
    )
    messages: list[AiChatMessageDict] = [
        _msg(id=1, role="user", send_model_id="m1"),
        _msg(id=2, role="assistant", model_id="m1", prompt_tokens=1000, completion_tokens=100),
        _msg(id=3, role="user", send_model_id="m1b"),
        _msg(id=4, role="assistant", model_id="m1b", prompt_tokens=200, completion_tokens=20),
        _msg(id=5, role="user", send_model_id="m2"),
        _msg(id=6, role="assistant", model_id="m2", prompt_tokens=500, completion_tokens=50),
    ]
    summary = session_spend_breakdown(messages)
    assert summary["assistant_turns"] == 3
    assert summary["priced_turns"] == 3
    assert summary["partial"] is False
    assert summary["known_usd"] > 0
    assert len(summary["models"]) == 3
    labels = {row["model_label"] for row in summary["models"]}
    assert "GPT-4o" in labels
    assert "GPT-4o mini" in labels
    assert "Claude" in labels


def test_session_spend_breakdown_includes_ollama_tokens_without_cost(monkeypatch) -> None:
    """Unrated local models still appear with token totals."""
    ollama = _entry(
        id="ollama-llama",
        provider="ollama",
        auth_ref="local",
        label="llama3.2",
        model="ollama/llama3.2",
    )
    del ollama["input_cost_per_token"]  # type: ignore[misc]
    del ollama["output_cost_per_token"]  # type: ignore[misc]
    monkeypatch.setattr(
        "services.ai.chat.message_usage.AiConfig.get_models",
        lambda: [ollama],
    )
    messages: list[AiChatMessageDict] = [
        _msg(id=1, role="user", send_model_id="ollama-llama"),
        _msg(
            id=2,
            role="assistant",
            model_id="ollama-llama",
            model_label="llama3.2",
            prompt_tokens=12_000,
            completion_tokens=800,
        ),
    ]
    summary = session_spend_breakdown(messages)
    assert summary["assistant_turns"] == 1
    assert summary["priced_turns"] == 0
    assert summary["partial"] is False
    assert summary["known_usd"] == 0.0
    assert len(summary["models"]) == 1
    row = summary["models"][0]
    assert row["model_label"] == "llama3.2"
    assert "ollama" in row["provider_label"].lower()
    assert row["prompt_tokens"] == 12_000
    assert row["completion_tokens"] == 800
    assert row["cost_usd"] is None


def test_resolve_turn_model_id_falls_back_to_preceding_user_send_model() -> None:
    """Assistant rows without model_id use the preceding user send model."""
    messages: list[AiChatMessageDict] = [
        _msg(id=1, role="user", send_model_id="m1"),
        _msg(id=2, role="assistant", prompt_tokens=10, completion_tokens=5),
    ]
    model_id = resolve_turn_model_id(messages[1], messages=messages, msg_index=1)
    assert model_id == "m1"


def test_format_spend_pill_label_partial_suffix() -> None:
    """Partial pricing appends + to the pill label."""
    summary: SessionSpendBreakdown = {
        "total_usd": None,
        "known_usd": 0.04,
        "assistant_turns": 2,
        "priced_turns": 1,
        "partial": True,
        "models": [],
    }
    assert format_spend_pill_label(summary).endswith("+")


def test_format_spend_tab_label_prefixes_spend() -> None:
    """Spend flyout tab shows Spend prefix before USD amount."""
    summary: SessionSpendBreakdown = {
        "total_usd": 0.042,
        "known_usd": 0.042,
        "assistant_turns": 1,
        "priced_turns": 1,
        "partial": False,
        "models": [],
    }
    assert format_spend_tab_label(summary) == "Spend $0.042"
    summary["partial"] = True
    assert format_spend_tab_label(summary) == "Spend $0.042+"
    summary["known_usd"] = 0.0
    summary["total_usd"] = None
    assert format_spend_tab_label(summary) == "Spend"


def test_format_context_ring_tooltip_appends_session_spend() -> None:
    """Ring tooltip includes session spend when priced."""
    summary: SessionSpendBreakdown = {
        "total_usd": 0.042,
        "known_usd": 0.042,
        "assistant_turns": 1,
        "priced_turns": 1,
        "partial": False,
        "models": [],
    }
    text = format_context_ring_tooltip(18_700, 128_000, summary)
    assert "Context:" in text
    assert "Session ~" in text


def test_spend_pill_visible_when_partial_or_known() -> None:
    """Spend pill shows for known or partial pricing."""
    assert spend_pill_visible(
        {
            "total_usd": None,
            "known_usd": 0.01,
            "assistant_turns": 1,
            "priced_turns": 1,
            "partial": False,
            "models": [],
        }
    )
    assert spend_pill_visible(
        {
            "total_usd": None,
            "known_usd": 0.01,
            "assistant_turns": 2,
            "priced_turns": 1,
            "partial": True,
            "models": [],
        }
    )
    assert not spend_pill_visible(
        {
            "total_usd": None,
            "known_usd": 0.0,
            "assistant_turns": 0,
            "priced_turns": 0,
            "partial": False,
            "models": [],
        }
    )


def test_sum_assistant_turn_costs_matches_session_known_usd(monkeypatch) -> None:
    """Footer-priced turns sum to the Spend flyout known_usd total."""
    mini = _entry(
        id="mini",
        label="gpt-5.4-mini",
        input_cost_per_token=0.00000015,
        output_cost_per_token=0.0000006,
    )
    monkeypatch.setattr(
        "services.ai.chat.message_usage.AiConfig.get_models",
        lambda: [mini],
    )
    messages: list[AiChatMessageDict] = [
        _msg(id=1, role="user", send_model_id="mini"),
        _msg(id=2, role="assistant", prompt_tokens=1200, completion_tokens=400),
        _msg(id=3, role="user", send_model_id="mini"),
        _msg(id=4, role="assistant", prompt_tokens=900, completion_tokens=350),
        _msg(id=5, role="user", send_model_id="mini"),
        _msg(id=6, role="assistant", prompt_tokens=600, completion_tokens=200),
        _msg(id=7, role="user", send_model_id="mini"),
        _msg(id=8, role="assistant", prompt_tokens=1100, completion_tokens=420),
    ]
    summary = session_spend_breakdown(messages, session_model_id="other-default")
    summed = sum_assistant_turn_costs(messages, session_model_id="other-default")
    assert summary["assistant_turns"] == 4
    assert abs(float(summary["known_usd"]) - summed) < 1e-12
    for model_row in summary["models"]:
        model_id = model_row["model_id"]
        row_sum = 0.0
        for index, msg in enumerate(messages):
            if msg.get("role") != "assistant":
                continue
            priced_model_id, cost = assistant_turn_cost_for_message(
                msg,
                messages=messages,
                msg_index=index,
                session_model_id="other-default",
            )
            if priced_model_id == model_id and cost is not None:
                row_sum += cost
        if model_row.get("cost_usd") is not None:
            assert abs(float(model_row["cost_usd"] or 0.0) - row_sum) < 1e-12


def test_pricing_model_id_prefers_preceding_user_send_model(monkeypatch) -> None:
    """Spend attribution uses the user send model, not the session default."""
    mini = _entry(id="mini", label="gpt-5.4-mini")
    oss = _entry(id="oss", label="gpt-oss")
    monkeypatch.setattr(
        "services.ai.chat.message_usage.AiConfig.get_models",
        lambda: [mini, oss],
    )
    messages: list[AiChatMessageDict] = [
        _msg(id=1, role="user", send_model_id="mini"),
        _msg(id=2, role="assistant", prompt_tokens=1000, completion_tokens=200),
    ]
    model_id = pricing_model_id_for_assistant_message(
        messages[1],
        messages=messages,
        msg_index=1,
        session_model_id="oss",
    )
    assert model_id == "mini"
    footer = format_assistant_footer_label(
        mini,
        None,
        prompt_tokens=1000,
        completion_tokens=200,
        reasoning_tokens=0,
        message=messages[1],
        messages=messages,
        msg_index=1,
        session_model_id="oss",
    )
    summary = session_spend_breakdown(messages, session_model_id="oss")
    assert footer.startswith("gpt-5.4-mini · $")
    assert summary["known_usd"] == sum_assistant_turn_costs(messages, session_model_id="oss")
