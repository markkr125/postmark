"""Round-trip + migration tests for AiConfig (QSettings auto-isolated)."""

from __future__ import annotations

import json

from PySide6.QtCore import QSettings

from services.ai.ai_config import AiConfig, AiModelEntry, model_entry_enabled


def _entry(**kw: object) -> AiModelEntry:
    base: AiModelEntry = {
        "id": "id1",
        "provider": "anthropic",
        "label": "L",
        "model": "anthropic/claude-sonnet-4-5-20250929",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
    }
    base.update(kw)  # type: ignore[typeddict-item]
    return base


def test_round_trip() -> None:
    """Models and default id round-trip through QSettings."""
    AiConfig.set_models([_entry()])
    AiConfig.set_default_model_id("id1")
    got = AiConfig.get_models()
    assert len(got) == 1
    assert got[0]["model"] == "anthropic/claude-sonnet-4-5-20250929"
    assert AiConfig.get_default_model_id() == "id1"


def test_empty() -> None:
    """Clearing models returns an empty list."""
    AiConfig.set_models([])
    assert AiConfig.get_models() == []


def test_drops_rows_without_model() -> None:
    """Rows with an empty model field are dropped on read."""
    QSettings("Postmark", "Postmark").setValue(
        "ai/models",
        json.dumps([{"id": "x", "model": ""}, {"id": "y", "model": "openai/gpt-4o"}]),
    )
    got = AiConfig.get_models()
    assert [e["model"] for e in got] == ["openai/gpt-4o"]


def test_id_migration_persists() -> None:
    """Legacy rows without id get a stable id written back to QSettings."""
    QSettings("Postmark", "Postmark").setValue(
        "ai/models", json.dumps([{"model": "openai/gpt-4o", "label": "G"}])
    )
    first = AiConfig.get_models()
    assert first[0]["id"]
    second = AiConfig.get_models()
    assert second[0]["id"] == first[0]["id"]


def test_enabled_migration_defaults_false() -> None:
    """Legacy rows without enabled are migrated to disabled."""
    QSettings("Postmark", "Postmark").setValue(
        "ai/models",
        json.dumps([{"id": "a", "model": "openai/gpt-4o", "label": "G"}]),
    )
    got = AiConfig.get_models()
    assert got[0]["enabled"] is False
    assert model_entry_enabled(got[0]) is False


def test_save_all_clears_legacy_default() -> None:
    """save_all persists models and clears any stored default model id."""
    AiConfig.set_default_model_id("id1")
    AiConfig.save_all([_entry()])
    assert AiConfig.get_default_model_id() == ""
