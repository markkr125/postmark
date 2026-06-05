"""Tests for run-context presets and LiteLLM pricing tiers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.ai.ops.model_metadata import litellm_context_tier_thresholds
from services.ai.provider_catalog import (
    default_run_context_tokens,
    run_context_choices,
)


def test_litellm_context_tier_thresholds_parses_272k() -> None:
    """LiteLLM ``input_cost_per_token_above_*`` keys map to token counts."""
    row = {
        "input_cost_per_token": 5e-06,
        "input_cost_per_token_above_272k_tokens": 1e-05,
        "max_input_tokens": 1_050_000,
    }
    fake = MagicMock()
    fake.model_cost = {"openai/gpt-5.5": row}
    with patch.dict("sys.modules", {"litellm": fake}):
        tiers = litellm_context_tier_thresholds("openai/gpt-5.5")
    assert tiers == (272_000,)


def test_tiered_run_context_choices_only_breakpoints() -> None:
    """Cloud models with tiers offer standard cap vs max, not every step."""
    entry: dict[str, object] = {
        "provider": "openai",
        "context": 1_050_000,
        "context_tiers": [272_000],
    }
    choices = run_context_choices(entry)
    values = [v for _, v in choices]
    assert values == [272_000, 1_050_000]
    assert 32_768 not in values
    assert 131_072 not in values


def test_tiered_default_is_standard_cap() -> None:
    """Default run context uses the lowest pricing tier, not the model max."""
    entry: dict[str, object] = {
        "provider": "openai",
        "context": 1_050_000,
        "context_tiers": [272_000],
    }
    assert default_run_context_tokens(entry) == 272_000


def test_openai_without_tiers_has_no_context_choices() -> None:
    """Models without tier metadata do not expose context presets."""
    entry: dict[str, object] = {
        "provider": "openai",
        "context": 128_000,
    }
    assert run_context_choices(entry) == ()


def test_ollama_still_has_stepped_context_choices() -> None:
    """Ollama keeps the full stepped preset list."""
    entry: dict[str, object] = {
        "provider": "ollama",
        "context": 131_072,
        "default_context": 32_768,
    }
    choices = run_context_choices(entry)
    values = [v for _, v in choices]
    assert 32_768 in values
    assert 65_536 in values
    assert 131_072 in values
