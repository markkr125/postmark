"""AI page model-list helpers (provider refresh ordering)."""

from __future__ import annotations

from services.ai.ai_config import AiModelEntry
from ui.dialogs.settings.ai_page import splice_provider_models


def _row(row_id: str, *, provider: str, model: str, auth_ref: str = "") -> AiModelEntry:
    return {
        "id": row_id,
        "provider": provider,
        "label": row_id,
        "model": model,
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": auth_ref,
    }


def test_splice_provider_models_keeps_position() -> None:
    """Refreshing a provider replaces its block without moving it to the end."""
    ollama = _row("o1", provider="ollama", model="ollama/llama3", auth_ref="ai:o")
    openai_a = _row("a1", provider="openai", model="openai/gpt-4o", auth_ref="ai:openai")
    openai_b = _row("a2", provider="openai", model="openai/gpt-4o-mini", auth_ref="ai:openai")
    models = [ollama, openai_a, openai_b]
    refreshed = [
        _row("n1", provider="openai", model="openai/gpt-4o", auth_ref="ai:openai"),
        _row("n2", provider="openai", model="openai/gpt-5", auth_ref="ai:openai"),
    ]
    out = splice_provider_models(
        models,
        group_key="ai:openai",
        auth_ref="ai:openai",
        new_rows=refreshed,
    )
    assert [e["id"] for e in out] == ["o1", "n1", "n2"]
