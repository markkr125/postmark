"""Settings tree context and capability display helpers."""

from __future__ import annotations

from services.ai.ai_config import AiModelEntry
from services.ai.provider_catalog import (
    capability_flags_for_entry,
    capability_tags_for_entry,
    context_display_for_entry,
    context_tokens_for_model,
    format_context_tokens,
)


def test_format_context_tokens() -> None:
    """Context sizes use compact k/M labels."""
    assert format_context_tokens(0) == "—"
    assert format_context_tokens(128000) == "128k"
    assert format_context_tokens(2000000) == "2M"


def test_context_from_catalog_when_not_persisted() -> None:
    """Known catalog models resolve context without LiteLLM."""
    assert context_tokens_for_model("openai/gpt-4o") == 128000
    assert context_display_for_entry({"model": "openai/gpt-4o"}) == "128k"


def test_capability_flags_tools_and_vision() -> None:
    """Capabilities column shows suggest, tools, and vision only."""
    entry: AiModelEntry = {
        "id": "1",
        "provider": "openai",
        "label": "G",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "context": 128000,
        "tools": True,
        "vision": True,
        "text": True,
    }
    assert context_display_for_entry(entry) == "128k"
    assert capability_flags_for_entry(entry) == "tools · vision"


def test_capability_flags_omit_unsupported() -> None:
    """Only enabled capabilities appear in the column."""
    entry: AiModelEntry = {
        "id": "2",
        "provider": "openai",
        "label": "T",
        "model": "openai/gpt-3.5-turbo",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "tools": True,
        "vision": False,
        "text": True,
    }
    assert capability_flags_for_entry(entry) == "tools"


def test_suggest_tag_from_ollama_insert() -> None:
    """UI label ``suggest`` reflects Ollama ``insert`` (fill-in-middle)."""
    entry: AiModelEntry = {
        "id": "3",
        "provider": "ollama",
        "label": "Coder",
        "model": "ollama/deepseek-coder-v2:latest",
        "base_url": "http://127.0.0.1:11434",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "tools": True,
        "vision": False,
        "text": False,
        "insert": True,
    }
    assert capability_flags_for_entry(entry) == "suggest · tools"
    tags = capability_tags_for_entry(entry)
    assert [t["label"] for t in tags] == ["suggest", "tools"]
    assert [t["kind"] for t in tags] == ["suggest", "tools"]


def test_ollama_tools_only_row() -> None:
    """Ollama rows without insert or vision show tools only."""
    entry: AiModelEntry = {
        "id": "5",
        "provider": "ollama",
        "label": "Chat model",
        "model": "ollama/qwen3:latest",
        "base_url": "http://127.0.0.1:11434",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "tools": True,
        "vision": False,
        "text": True,
        "insert": False,
    }
    tags = capability_tags_for_entry(entry)
    assert [t["label"] for t in tags] == ["tools"]


def test_catalog_fallback_tags() -> None:
    """Catalog models without persisted flags use static spec insert/tools/vision."""
    tags = capability_tags_for_entry({"model": "openai/gpt-4o"})
    assert [t["label"] for t in tags] == ["tools", "vision"]
