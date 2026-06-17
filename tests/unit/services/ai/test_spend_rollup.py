"""Tests for cross-session spend rollups."""

from __future__ import annotations

from services.ai.ai_config import AiModelEntry
from services.ai.chat.spend_rollup import global_spend_summary


def _entry(**kw: object) -> AiModelEntry:
    base: AiModelEntry = {
        "id": "m1",
        "provider": "openai",
        "label": "GPT-4o",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "token",
        "auth_ref": "ref-a",
        "input_cost_per_token": 0.0000025,
        "output_cost_per_token": 0.00001,
    }
    base.update(kw)  # type: ignore[typeddict-item]
    return base


def test_global_spend_summary_empty_when_no_messages(monkeypatch) -> None:
    """No assistant usage rows yields zeroed summaries."""
    monkeypatch.setattr(
        "services.ai.chat.spend_rollup.list_assistant_usage_messages",
        lambda **_kw: [],
    )
    monkeypatch.setattr(
        "services.ai.chat.spend_rollup._session_model_ids",
        lambda: {},
    )
    monkeypatch.setattr(
        "services.ai.chat.spend_rollup.AiConfig.get_models",
        lambda: [_entry()],
    )
    summary = global_spend_summary()
    assert summary["known_overall_usd"] == 0.0
    assert summary["overall_tokens"] == 0
    assert len(summary["connections"]) == 1
