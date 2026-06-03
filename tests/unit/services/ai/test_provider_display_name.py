"""Provider display name allocation and migration."""

from __future__ import annotations

from services.ai.ai_config import AiModelEntry
from services.ai.provider_catalog import (
    allocate_provider_display_name,
    catalog_provider_label,
    migrate_provider_display_names,
    model_row_label,
    provider_group_label,
)
from services.ai.provider_catalog import ModelSpec


def test_allocate_unique_display_name() -> None:
    """Second Ollama connection gets a numbered suffix."""
    used = {catalog_provider_label("ollama")}
    assert allocate_provider_display_name("ollama", used) == "Ollama (local) 2"


def test_provider_group_label_uses_stored_name() -> None:
    """Tree header reads provider_display_name, not model label."""
    entry: AiModelEntry = {
        "id": "1",
        "provider": "ollama",
        "label": "devstral",
        "provider_display_name": "Home GPU",
        "model": "ollama/devstral:latest",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "ai:1",
    }
    assert provider_group_label(entry) == "Home GPU"


def test_model_row_label_from_model_id_when_label_empty() -> None:
    """Model rows derive a short name from the model id, not the provider display name."""
    spec = ModelSpec("ollama/devstral:latest", "", 8192, True, False)
    assert model_row_label(spec) == "devstral"


def test_migrate_assigns_per_connection_group() -> None:
    """Legacy rows without provider_display_name get a catalog default."""
    rows: list[dict[str, object]] = [
        {
            "id": "a",
            "provider": "ollama",
            "label": "devstral",
            "model": "ollama/devstral:latest",
            "base_url": "http://127.0.0.1:11434",
            "api_version": "",
            "auth_kind": "none",
            "auth_ref": "ai:one",
        },
        {
            "id": "b",
            "provider": "ollama",
            "label": "llama3",
            "model": "ollama/llama3:latest",
            "base_url": "http://127.0.0.1:11434",
            "api_version": "",
            "auth_kind": "none",
            "auth_ref": "ai:one",
        },
    ]
    assert migrate_provider_display_names(rows) is True
    assert rows[0]["provider_display_name"] == "Ollama (local)"
    assert rows[1]["provider_display_name"] == "Ollama (local)"
