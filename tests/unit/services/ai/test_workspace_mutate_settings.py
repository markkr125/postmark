"""Tests for allowlisted settings mutate."""

from __future__ import annotations

from services.ai.chat.tools.workspace_mutate.settings_ops import (
    apply_settings_mutation,
    filter_settings_fields,
)
from services.scripting.runtime_settings import RuntimeSettings


class TestSettingsMutate:
    """Allowlisted settings writes; AI keys rejected."""

    def test_rejects_ai_key(self) -> None:
        """AI credential fields must be rejected."""
        _fields, err = filter_settings_fields("update", {"ai/models": "[]"})
        assert err is not None
        text = err.to_text() if hasattr(err, "to_text") else str(err)
        assert "forbidden" in text or "unsupported_field" in text

    def test_updates_lsp_enabled(self) -> None:
        """Allowlisted boolean prefs update via RuntimeSettings."""
        before = RuntimeSettings.lsp_enabled()
        fields, err = filter_settings_fields("update", {"lsp_enabled": not before})
        assert err is None
        assert fields is not None
        obs = apply_settings_mutation(fields=fields)
        text = obs.to_text() if hasattr(obs, "to_text") else str(obs)
        assert "ok: true" in text
        assert RuntimeSettings.lsp_enabled() is (not before)
        # Restore
        apply_settings_mutation(fields={"lsp_enabled": before})
