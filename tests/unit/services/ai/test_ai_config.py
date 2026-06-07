"""Round-trip + migration tests for AiConfig (QSettings auto-isolated)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings

from services.ai.ai_config import (
    AiConfig,
    AiModelEntry,
    merge_tier_backfill_results,
    model_entry_enabled,
)


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


def test_reasoning_fields_round_trip_and_clamp() -> None:
    """Reasoning metadata persists and stale effort values are clamped."""
    AiConfig.set_models(
        [
            _entry(
                reasoning=True,
                reasoning_efforts=["low", "medium", "high"],
                reasoning_default="medium",
                reasoning_effort="invalid",
            )
        ]
    )
    got = AiConfig.get_models()
    assert got[0]["reasoning"] is True
    assert got[0]["reasoning_effort"] == "medium"

    AiConfig.set_model_reasoning_effort("id1", "high")
    got2 = AiConfig.get_models()
    assert got2[0]["reasoning_effort"] == "high"


def test_chat_model_id_round_trip() -> None:
    """Chat composer model selection round-trips through QSettings."""
    AiConfig.set_chat_model_id("ollama-1")
    assert AiConfig.get_chat_model_id() == "ollama-1"
    AiConfig.set_chat_model_id("")
    assert AiConfig.get_chat_model_id() == ""


def test_chat_session_id_round_trip() -> None:
    """Active chat session id round-trips through QSettings."""
    session_id = "49889e20-780e-441b-915d-845d0f72bfb9"
    AiConfig.set_chat_session_id(session_id)
    assert AiConfig.get_chat_session_id() == session_id
    AiConfig.set_chat_session_id("")
    assert AiConfig.get_chat_session_id() == ""


def test_save_all_clears_legacy_default() -> None:
    """save_all persists models and clears any stored default model id."""
    AiConfig.set_default_model_id("id1")
    AiConfig.save_all([_entry()])
    assert AiConfig.get_default_model_id() == ""


def test_get_models_pure_read_skips_tier_backfill() -> None:
    """Default get_models does not add tiers_checked or context_tiers from LiteLLM."""
    QSettings("Postmark", "Postmark").setValue(
        "ai/models",
        json.dumps(
            [
                {
                    "id": "open1",
                    "provider": "openai",
                    "model": "openai/gpt-4o",
                    "label": "G",
                    "enabled": True,
                }
            ]
        ),
    )

    with patch(
        "services.ai.ai_config.litellm_context_tier_thresholds",
        side_effect=AssertionError("litellm must not run on default get_models"),
    ):
        got = AiConfig.get_models()

    assert len(got) == 1
    assert "tiers_checked" not in got[0]
    assert "context_tiers" not in got[0]


def test_backfill_tiers_persists_tiers_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    """backfill_tiers=True with persist=True marks checked and writes QSettings."""
    QSettings("Postmark", "Postmark").setValue(
        "ai/models",
        json.dumps(
            [
                {
                    "id": "open1",
                    "provider": "openai",
                    "model": "openai/gpt-4o",
                    "label": "G",
                    "enabled": True,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        "services.ai.ai_config.litellm_context_tier_thresholds",
        lambda _model: (272_000,),
    )

    first = AiConfig.get_models(backfill_tiers=True)
    assert first[0].get("tiers_checked") is True
    assert first[0].get("context_tiers") == [272_000]

    second = AiConfig.get_models()
    assert second[0].get("tiers_checked") is True
    assert second[0].get("context_tiers") == [272_000]


def test_backfill_tiers_persist_false_does_not_write_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """persist=False returns tiers_checked in memory but does not write QSettings."""
    QSettings("Postmark", "Postmark").setValue(
        "ai/models",
        json.dumps(
            [
                {
                    "id": "open1",
                    "provider": "openai",
                    "model": "openai/gpt-4o",
                    "label": "G",
                    "enabled": True,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        "services.ai.ai_config.litellm_context_tier_thresholds",
        lambda _model: (),
    )
    set_value_calls: list[tuple[str, object]] = []
    original_set_value = QSettings.setValue

    def _tracking_set_value(self: QSettings, key: str, value: object) -> None:
        if key == "ai/models":
            set_value_calls.append((key, value))
        original_set_value(self, key, value)

    with patch.object(QSettings, "setValue", _tracking_set_value):
        got = AiConfig.get_models(backfill_tiers=True, persist=False)

    assert got[0].get("tiers_checked") is True
    assert not set_value_calls

    plain = AiConfig.get_models()
    assert "tiers_checked" not in plain[0]


def test_backfill_tiers_skips_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama models are not marked tiers_checked by the backfill block."""
    QSettings("Postmark", "Postmark").setValue(
        "ai/models",
        json.dumps(
            [
                {
                    "id": "oll1",
                    "provider": "ollama",
                    "model": "ollama/llama3",
                    "label": "L",
                    "enabled": True,
                }
            ]
        ),
    )
    called: list[str] = []

    def _fake_tiers(model_id: str) -> tuple[int, ...]:
        called.append(model_id)
        return ()

    monkeypatch.setattr(
        "services.ai.ai_config.litellm_context_tier_thresholds",
        _fake_tiers,
    )

    got = AiConfig.get_models(backfill_tiers=True, persist=False)
    assert called == []
    assert "tiers_checked" not in got[0]


def test_merge_tier_backfill_preserves_user_edits() -> None:
    """Merge copies tiers/tiers_checked only; does not overwrite other fields."""
    current: list[AiModelEntry] = [
        _entry(
            id="a",
            context_limit=50_000,
            thinking_enabled="off",
        )
    ]
    backfilled: list[AiModelEntry] = [
        _entry(
            id="a",
            context_tiers=[272_000],
            tiers_checked=True,
            context_limit=128_000,
            thinking_enabled="on",
        )
    ]
    merge_tier_backfill_results(current, backfilled)
    assert current[0].get("context_tiers") == [272_000]
    assert current[0].get("tiers_checked") is True
    assert current[0].get("context_limit") == 50_000
    assert current[0].get("thinking_enabled") == "off"


def test_merge_tier_backfill_skips_missing_context_tiers_on_current() -> None:
    """When current already has context_tiers, backfill does not replace them."""
    current: list[AiModelEntry] = [_entry(id="a", context_tiers=[100_000])]
    backfilled: list[AiModelEntry] = [_entry(id="a", context_tiers=[272_000], tiers_checked=True)]
    merge_tier_backfill_results(current, backfilled)
    assert current[0].get("context_tiers") == [100_000]
    assert current[0].get("tiers_checked") is True


def test_entries_from_model_specs_sets_tiers_checked() -> None:
    """Settings-saved rows are marked checked (including ollama)."""
    from services.ai.provider_catalog import ModelSpec
    from ui.dialogs.settings.ai_page_actions import entries_from_model_specs

    template: AiModelEntry = {
        "id": "tpl",
        "provider": "ollama",
        "label": "Ollama",
        "model": "ollama/llama3",
        "base_url": "http://localhost:11434",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
    }
    spec = ModelSpec(
        model="ollama/llama3",
        label="Llama",
        context=32_000,
        tools=False,
        vision=False,
    )
    rows = entries_from_model_specs(template, (spec,), provider_display_name="Ollama")
    assert rows[0].get("tiers_checked") is True
