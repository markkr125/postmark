"""Tests for per-message usage helpers."""

from __future__ import annotations

from services.ai.ai_config import AiModelEntry
from services.ai.chat.context_usage import ContextUsageSdkMetrics
from services.ai.chat.message_usage import (
    effective_assistant_model_id,
    entry_for_model_id,
    format_assistant_footer_label,
    message_turn_cost_usd,
    resolve_model_display_name,
    turn_usage_delta,
)


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
