"""Tests for LSP diagnostic filtering."""

from __future__ import annotations

from services.lsp.diagnostic_filters import should_publish_lsp_diagnostic


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
