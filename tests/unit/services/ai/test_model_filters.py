"""Agent-capable model filtering."""

from __future__ import annotations

from services.ai.ops.model_filters import filter_agent_capable, filter_settings_models
from services.ai.ops.model_metadata import enrich_litellm_spec
from services.ai.provider_catalog import ModelSpec


def test_filter_settings_models_requires_tools() -> None:
    """Settings import drops models without tool calling."""
    models = (
        ModelSpec("ollama/gemma3:1b", "gemma3", 32768, False, False, True),
        ModelSpec("ollama/qwen2.5", "qwen", 32768, True, False, True),
    )
    kept = filter_settings_models(models)
    assert [m.model for m in kept] == ["ollama/qwen2.5"]


def test_filter_agent_capable_requires_text_and_tools() -> None:
    """Models must support text and tool calling."""
    models = (
        ModelSpec("a", "A", 0, True, False, True),
        ModelSpec("b", "B", 0, False, False, True),
        ModelSpec("c", "C", 0, True, False, False),
    )
    kept = filter_agent_capable(models)
    assert [m.model for m in kept] == ["a"]


def test_enrich_litellm_drops_embeddings(monkeypatch) -> None:
    """Embedding model ids are excluded."""
    base = ModelSpec("openai/text-embedding-3-small", "embed", 0, True, False, True)
    assert enrich_litellm_spec(base) is None
