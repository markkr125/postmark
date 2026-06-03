"""Per-model context resolution from provider APIs and LiteLLM."""

from __future__ import annotations

import pytest

from services.ai.ops.model_metadata import (
    _ollama_agent_flags_from_show,
    litellm_context_tokens,
    ollama_context_from_show,
)
from services.ai.provider_catalog import ModelSpec


def test_litellm_context_openai() -> None:
    """LiteLLM maps OpenAI models to max_input_tokens."""
    ctx = litellm_context_tokens("openai/gpt-4o-mini")
    assert ctx >= 100_000


def test_ollama_context_from_show_model_info() -> None:
    """Ollama show responses expose context on model_info keys."""
    data = {
        "model_info": {
            "llama.context_length": 8192,
        },
        "capabilities": ["completion"],
    }
    assert ollama_context_from_show(data) == 8192


def test_ollama_vision_from_clip_family() -> None:
    """Multimodal Ollama models expose clip in families or a vision capability."""
    data = {
        "capabilities": ["completion", "tools"],
        "details": {"families": ["llama", "clip"]},
    }
    _text, _tools, vision, _insert = _ollama_agent_flags_from_show(data, raw_name="llama3.2:latest")
    assert vision is True


def test_ollama_vision_false_for_coder_model() -> None:
    """Text-only coders are not tagged as vision without clip/vision metadata."""
    data = {"capabilities": ["completion", "tools"]}
    _text, _tools, vision, _insert = _ollama_agent_flags_from_show(
        data, raw_name="qwen2.5-coder:latest"
    )
    assert vision is False


def test_ollama_insert_capability() -> None:
    """Ollama reports fill-in-middle as capability ``insert`` (shown as suggest in settings)."""
    data = {"capabilities": ["completion", "tools", "insert"]}
    _text, tools, _vision, insert = _ollama_agent_flags_from_show(
        data, raw_name="deepseek-coder-v2:latest"
    )
    assert tools is True
    assert insert is True


def test_enrich_ollama_spec_uses_default_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """When /api/show and LiteLLM lack context, apply the provider default."""
    from services.ai.ops import model_metadata as meta

    monkeypatch.setattr(
        meta,
        "_ollama_show_json",
        lambda *_a, **_kw: {"capabilities": ["completion", "tools"]},
    )
    monkeypatch.setattr(meta, "litellm_context_tokens", lambda _m: 0)
    monkeypatch.setattr(meta, "_resolve_spec_costs", lambda *_a, **_kw: (0.0, 0.0))

    out = meta.enrich_ollama_spec(
        ModelSpec("ollama/mystery", "mystery", 0, False, False, True),
        base_url="http://127.0.0.1:11434",
        api_key="",
        timeout=1.0,
        default_context=32_768,
    )
    assert out is not None
    assert out.context == 32_768


def test_enrich_ollama_spec_persists_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama enrich copies insert from /api/show into ModelSpec."""
    from services.ai.ops import model_metadata as meta

    monkeypatch.setattr(
        meta,
        "_ollama_show_json",
        lambda *_a, **_kw: {
            "capabilities": ["completion", "tools", "insert"],
            "model_info": {"llama.context_length": 32768},
        },
    )
    monkeypatch.setattr(meta, "_resolve_spec_costs", lambda *_a, **_kw: (0.0, 0.0))

    out = meta.enrich_ollama_spec(
        ModelSpec("ollama/qwen2.5-coder:14b", "qwen", 0, False, False, True),
        base_url="http://127.0.0.1:11434",
        api_key="",
        timeout=1.0,
    )
    assert out is not None
    assert out.insert is True


def test_enrich_openai_specs_sets_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI list ids are enriched with LiteLLM context (not a flat 128k default)."""
    from services.ai.ops import model_metadata as meta

    monkeypatch.setattr(meta, "litellm_context_tokens", lambda m: 200_000 if "gpt-4o" in m else 0)
    monkeypatch.setattr(
        meta,
        "_litellm_agent_caps",
        lambda _m: (True, True),
    )
    specs = (ModelSpec("openai/gpt-4o", "gpt-4o", 0, False, False, True),)
    out = meta.enrich_openai_specs(specs)
    assert len(out) == 1
    assert out[0].context == 200_000
