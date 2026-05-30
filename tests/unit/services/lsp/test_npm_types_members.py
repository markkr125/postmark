"""Unit tests for :mod:`services.lsp.npm_types_members`."""

from __future__ import annotations

from pathlib import Path

from services.lsp.npm_types_members import (
    members_for_npm_specifier,
    members_for_pm_require_spec,
    scan_npm_require_variables,
)
from services.scripting.js_runtime import PmRequireSpec


class TestScanNpmRequireVariables:
    """``scan_npm_require_variables`` maps variables to specifiers."""

    def test_detects_const_assignment(self) -> None:
        script = "const npmVariableName = pm.require('npm:lodash');"
        assert scan_npm_require_variables(script) == {"npmVariableName": "npm:lodash"}


class TestExtractMembers:
    """Member extraction from cached ``@types`` trees."""

    def test_lodash_includes_chunk(self) -> None:
        ws = Path.home() / ".local/share/postmark/lsp-workspace/js"
        labels = members_for_npm_specifier(ws, "npm:lodash")
        assert "chunk" in labels

    def test_prefix_filter(self) -> None:
        ws = Path.home() / ".local/share/postmark/lsp-workspace/js"
        labels = members_for_npm_specifier(ws, "npm:lodash", prefix="chu")
        assert "chunk" in labels
        assert all(label.lower().startswith("chu") for label in labels)


class TestMembersForPmRequireSpec:
    """``members_for_pm_require_spec`` accepts :class:`PmRequireSpec`."""

    def test_spec_object(self) -> None:
        ws = Path.home() / ".local/share/postmark/lsp-workspace/js"
        spec = PmRequireSpec("npm", "lodash", "")
        if not (ws / "node_modules").is_dir():
            return
        labels = members_for_pm_require_spec(ws, spec)
        assert "map" in labels
