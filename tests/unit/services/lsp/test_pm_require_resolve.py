"""Unit tests for :mod:`services.lsp.pm_require_resolve`."""

from __future__ import annotations

from unittest.mock import patch

from services.lsp.pm_require_resolve import types_specifier
from services.scripting.js_runtime import PmRequireSpec


class TestTypesSpecifier:
    """``types_specifier`` pins registry latest when version is omitted."""

    def test_versioned_unchanged(self) -> None:
        spec = PmRequireSpec("npm", "lodash", "4.17.21")
        assert types_specifier(spec) == "npm:lodash@4.17.21"

    def test_unversioned_npm_resolves_latest(self) -> None:
        spec = PmRequireSpec("npm", "lodash", "")
        npm_meta = {"dist-tags": {"latest": "4.17.21"}}
        with patch(
            "services.lsp.pm_require_resolve._fetch_json",
            return_value=npm_meta,
        ):
            assert types_specifier(spec) == "npm:lodash@4.17.21"

    def test_unversioned_jsr_resolves_latest(self) -> None:
        spec = PmRequireSpec("jsr", "@std/assert", "")
        with patch(
            "services.lsp.pm_require_resolve._fetch_json",
            return_value={"latest": "1.0.0"},
        ):
            assert types_specifier(spec) == "jsr:@std/assert@1.0.0"

    def test_registry_failure_falls_back_to_bare_specifier(self) -> None:
        spec = PmRequireSpec("npm", "lodash", "")
        with patch("services.lsp.pm_require_resolve._fetch_json", return_value=None):
            assert types_specifier(spec) == "npm:lodash"
