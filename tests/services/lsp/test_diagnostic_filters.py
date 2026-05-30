"""Tests for LSP diagnostic filtering."""

from __future__ import annotations

from services.lsp.client import Diagnostic
from services.lsp.diagnostic_filters import (
    should_publish_lsp_diagnostic,
    should_suppress_unused_local_require_diagnostic,
)
from services.scripting.local_dependency_diagnostics import RequireSite


def test_keeps_commonjs_to_esm_hint() -> None:
    """CommonJS→ESM hints are shown again (user-facing script editor guidance)."""
    raw = {
        "code": 80001,
        "message": "File is a CommonJS module; it may be converted to an ES module.",
        "severity": 4,
    }
    assert should_publish_lsp_diagnostic(raw)


def test_keeps_unrelated_diagnostics() -> None:
    """Other LSP issues are still published."""
    raw = {"code": 2304, "message": "Cannot find name 'foo'.", "severity": 1}
    assert should_publish_lsp_diagnostic(raw)


def test_filters_implicit_any_hints_on_js_only() -> None:
    """CheckJs inference nudges are dropped for ``.js``, kept for ``.ts``."""
    raw = {
        "message": (
            "Parameter 'str' implicitly has an 'any' type, "
            "but a better type may be inferred from usage."
        ),
        "severity": 4,
        "source": "deno-ts",
    }
    js_uri = "file:///tmp/script.js"
    ts_uri = "file:///tmp/script.ts"
    assert not should_publish_lsp_diagnostic(raw, document_uri=js_uri)
    assert should_publish_lsp_diagnostic(raw, document_uri=ts_uri)


def test_suppresses_unused_local_require_binding() -> None:
    """Unused-variable hints on ``pm.require('local:…')`` bindings are dropped."""
    sites = [RequireSite(rel_path="home/x.js", line=6, column=7, binding_name="local")]
    diag = Diagnostic(
        line=5,
        column=6,
        end_line=5,
        end_column=11,
        severity="hint",
        message="'local' is declared but its value is never read.",
        source="deno-ts",
    )
    assert should_suppress_unused_local_require_diagnostic(diag, sites)


def test_keeps_unused_on_other_lines() -> None:
    """Unused hints on unrelated lines are kept."""
    sites = [RequireSite(rel_path="home/x.js", line=6, column=7, binding_name="local")]
    diag = Diagnostic(
        line=9,
        column=1,
        end_line=9,
        end_column=5,
        severity="hint",
        message="'other' is declared but its value is never read.",
        source="deno-ts",
    )
    assert not should_suppress_unused_local_require_diagnostic(diag, sites)
