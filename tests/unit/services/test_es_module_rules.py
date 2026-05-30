"""Tests for ESM vs CommonJS editor rules and Deno stderr cleanup."""

from __future__ import annotations

import pytest

from esprima_test_util import deno_and_esprima_available  # type: ignore[import-not-found]
from services.scripting.engine import ScriptLinter
from services.scripting.es_module_rules import format_process_stderr, strip_ansi

_deno_for_js = deno_and_esprima_available


def test_strip_ansi_removes_sgr_codes() -> None:
    """ANSI colour codes are removed for UI display."""
    raw = "\x1b[0m\x1b[32mInitialize\x1b[0m lodash@4.18.1\n\x1b[31merror\x1b[0m: boom"
    assert strip_ansi(raw) == "Initialize lodash@4.18.1\nerror: boom"


def test_format_process_stderr_trims_and_strips() -> None:
    """Process stderr helper strips ANSI and enforces max length."""
    text = "\x1b[31m" + ("x" * 50) + "\x1b[0m"
    assert "\x1b" not in format_process_stderr(text, max_len=20)
    assert len(format_process_stderr(text, max_len=20)) == 20


@pytest.mark.skipif(not _deno_for_js(), reason="Deno + Esprima required for JS syntax walk")
def test_commonjs_editor_allows_module_exports() -> None:
    """Local CJS buffers skip ESM rules but still allow ``module.exports``."""
    script = "module.exports = { replaceStr: 1 };"
    assert ScriptLinter.check_es_module(script, "javascript")
    assert ScriptLinter.check_commonjs_local_script(script) == []


@pytest.mark.skipif(not _deno_for_js(), reason="Deno + Esprima required for JS syntax walk")
def test_commonjs_editor_flags_syntax_errors() -> None:
    """Broken JS in a CJS buffer still gets Esprima syntax diagnostics."""
    script = "function foo( {"
    diags = ScriptLinter.check_commonjs_local_script(script)
    assert diags
    assert diags[0]["severity"] == "error"


def test_commonjs_import_export_warning() -> None:
    """``import`` / ``export`` in CJS bodies produce a legacy-editor warning."""
    from services.scripting.es_module_rules import collect_commonjs_esm_syntax_warnings

    diags = collect_commonjs_esm_syntax_warnings("import x from 'y';\nexport default 1;")
    assert len(diags) == 2
    assert all(d["severity"] == "warning" for d in diags)
    assert "import/export" in diags[0]["message"]


@pytest.mark.skipif(not _deno_for_js(), reason="Deno + Esprima required for JS AST walk")
def test_module_exports_is_error() -> None:
    """``module.exports`` is flagged before run."""
    script = "module.exports = { replaceStr: () => {} }"
    diags = ScriptLinter.check_es_module(script, "javascript")
    assert diags
    assert diags[0]["severity"] == "error"
    assert "module.exports" in diags[0]["message"]


@pytest.mark.skipif(not _deno_for_js(), reason="Deno + Esprima required for JS AST walk")
def test_pm_require_is_not_flagged() -> None:
    """``pm.require`` must not be treated as CommonJS ``require``."""
    script = 'const x = pm.require("npm:lodash@4.18.1");'
    assert ScriptLinter.check_es_module(script, "javascript") == []


@pytest.mark.skipif(not _deno_for_js(), reason="Deno + Esprima required for JS AST walk")
def test_vendor_require_is_allowed() -> None:
    """Legacy built-in ``require('lodash')`` stays valid."""
    script = "const _ = require('lodash');"
    assert ScriptLinter.check_es_module(script, "javascript") == []


@pytest.mark.skipif(not _deno_for_js(), reason="Deno + Esprima required for JS AST walk")
def test_unknown_require_is_error() -> None:
    """Non-vendor ``require('pkg')`` is flagged."""
    script = "const m = require('my-private-pkg');"
    diags = ScriptLinter.check_es_module(script, "javascript")
    assert diags and "require()" in diags[0]["message"]


def test_typescript_module_exports_regex() -> None:
    """TypeScript buffers use regex fallback for CommonJS."""
    script = "module.exports = {}"
    diags = ScriptLinter.check_es_module(script, "typescript")
    assert diags and "module.exports" in diags[0]["message"]
