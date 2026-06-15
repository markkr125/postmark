"""Tests for per-message usage helpers."""

from __future__ import annotations

from services.ai.ai_config import AiModelEntry
from services.ai.chat.context_usage import ContextUsageSdkMetrics
from services.ai.chat.message_usage import (
    format_assistant_footer_label,
    message_turn_cost_usd,
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
