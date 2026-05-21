"""Unit tests for :mod:`services.lsp.pm_require_types`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from services.lsp.pm_require_types import (
    detect_npm_jsr_specs,
    pm_require_index_path,
    sync_pm_require_types,
)
from services.scripting.js_runtime import PmRequireSpec


class TestDetectNpmJsrSpecs:
    """``detect_npm_jsr_specs`` filters npm/jsr and skips invalid literals."""

    def test_empty_script(self) -> None:
        assert detect_npm_jsr_specs("") == []

    def test_npm_spec(self) -> None:
        specs = detect_npm_jsr_specs("const x = pm.require('npm:lodash@4.17.21');")
        assert specs == [PmRequireSpec("npm", "lodash", "4.17.21")]

    def test_jsr_spec(self) -> None:
        specs = detect_npm_jsr_specs("pm.require('jsr:@std/assert@1.0.0');")
        assert specs == [PmRequireSpec("jsr", "@std/assert", "1.0.0")]

    def test_invalid_specifier_is_skipped(self) -> None:
        assert detect_npm_jsr_specs("pm.require('npm:_bad@1.0.0');") == []


class TestPmRequireIndexGeneration:
    """``sync_pm_require_types`` writes ``pm_require_index.ts``."""

    def test_writes_overloads_for_detected_specs(self, tmp_path: Path) -> None:
        (tmp_path / "deno.json").write_text("{}", encoding="utf-8")
        script = "const _ = pm.require('npm:lodash@4.17.21');"
        with (
            patch(
                "services.lsp.pm_require_types.RuntimeSettings.enable_npm_type_resolution",
                return_value=True,
            ),
            patch("services.lsp.pm_require_types._deno_cache_specifiers") as cache_mock,
        ):
            changed = sync_pm_require_types(script, tmp_path)
        assert changed is True
        cache_mock.assert_called_once()
        text = pm_require_index_path(tmp_path).read_text(encoding="utf-8")
        assert "npm:lodash@4.17.21" in text
        assert 'function require(spec: "npm:lodash@4.17.21")' in text
        assert 'function require(spec: "npm:lodash")' in text

    def test_disabled_setting_skips_generation(self, tmp_path: Path) -> None:
        with patch(
            "services.lsp.pm_require_types.RuntimeSettings.enable_npm_type_resolution",
            return_value=False,
        ):
            changed = sync_pm_require_types("pm.require('npm:lodash@4.17.21');", tmp_path)
        assert changed is False
        assert not pm_require_index_path(tmp_path).exists()

    def test_no_change_when_content_matches(self, tmp_path: Path) -> None:
        (tmp_path / "deno.json").write_text("{}", encoding="utf-8")
        script = "pm.require('npm:lodash@4.17.21');"
        with (
            patch(
                "services.lsp.pm_require_types.RuntimeSettings.enable_npm_type_resolution",
                return_value=True,
            ),
            patch("services.lsp.pm_require_types._deno_cache_specifiers"),
        ):
            assert sync_pm_require_types(script, tmp_path) is True
            assert sync_pm_require_types(script, tmp_path) is False
