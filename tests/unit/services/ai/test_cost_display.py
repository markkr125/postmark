"""Model cost display and LiteLLM pricing lookup."""

from __future__ import annotations

from services.ai.ai_config import AiModelEntry
from services.ai.ops.model_metadata import litellm_cost_per_token
from services.ai.provider_catalog import (
    ModelSpec,
    cost_display_for_entry,
    cost_display_for_spec,
    format_model_cost_display,
)


def test_format_model_cost_display_per_million() -> None:
    """Costs show USD per 1M tokens for input and output."""
    inp = 2.5e-06
    out = 1e-05
    text = format_model_cost_display(inp, out, model="openai/gpt-4o")
    assert "$2.5 in" in text
    assert "$10 out" in text


def test_ollama_leaves_cost_empty_when_no_pricing() -> None:
    """Local models without pricing leave the cost column blank."""
    assert format_model_cost_display(0.0, 0.0, model="ollama/llama3") == ""


def test_cost_display_for_entry_uses_persisted_values() -> None:
    """Saved per-token costs format without calling LiteLLM."""
    entry: AiModelEntry = {
        "id": "1",
        "provider": "openai",
        "label": "G",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "input_cost_per_token": 2.5e-06,
        "output_cost_per_token": 1e-05,
    }
    assert "$2.5 in" in cost_display_for_entry(entry)


def test_cost_display_for_entry_does_not_lookup_missing_costs() -> None:
    """Saved rows without persisted pricing stay blank instead of blocking on metadata lookup."""
    entry: AiModelEntry = {
        "id": "2",
        "provider": "ollama",
        "label": "Local",
        "model": "ollama/qwen2.5-coder:7b",
        "base_url": "http://127.0.0.1:11434",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
    }
    assert cost_display_for_entry(entry) == ""


def test_litellm_cost_for_gpt4o() -> None:
    """LiteLLM registry includes OpenAI GPT-4o pricing."""
    inp, out = litellm_cost_per_token("openai/gpt-4o")
    assert inp > 0
    assert out > 0
    assert "$" in cost_display_for_spec(
        ModelSpec(
            "openai/gpt-4o",
            "GPT-4o",
            128000,
            True,
            True,
            True,
            False,
            inp,
            out,
        )
    )
