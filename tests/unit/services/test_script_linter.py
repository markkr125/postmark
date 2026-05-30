"""Tests for :class:`ScriptLinter` syntax and pm-API checking."""

from __future__ import annotations

import pytest

from esprima_test_util import deno_and_esprima_available  # type: ignore[import-not-found]
from services.scripting.engine import ScriptLinter

_deno_for_js_lint = deno_and_esprima_available


# ===================================================================
# JavaScript
# ===================================================================


class TestJavaScriptLinting:
    """Tests for JavaScript validation via Esprima (Deno subprocess)."""

    def test_valid_js_returns_empty(self) -> None:
        """Valid JavaScript produces no diagnostics."""
        assert ScriptLinter.check("var x = 1;", "javascript") == []

    def test_valid_js_multiline(self) -> None:
        """Valid multiline JavaScript produces no diagnostics."""
        script = "var x = 1;\nif (x > 0) {\n  console.log(x);\n}"
        assert ScriptLinter.check(script, "javascript") == []

    @pytest.mark.skipif(not _deno_for_js_lint(), reason="Deno required for JS Esprima parse")
    def test_syntax_error_missing_brace(self) -> None:
        """Missing closing brace is detected."""
        script = "if (true {"
        result = ScriptLinter.check(script, "javascript")
        assert len(result) == 1
        assert result[0]["severity"] == "error"
        assert result[0]["line"] == 1
        assert "Unexpected" in result[0]["message"]

    @pytest.mark.skipif(not _deno_for_js_lint(), reason="Deno required for JS Esprima parse")
    def test_syntax_error_line_2(self) -> None:
        """Error on line 2 reports the correct line."""
        script = "var x = 1;\nif (true {"
        result = ScriptLinter.check(script, "javascript")
        assert len(result) == 1
        assert result[0]["line"] == 2

    @pytest.mark.skipif(not _deno_for_js_lint(), reason="Deno required for JS Esprima parse")
    def test_syntax_error_line_3(self) -> None:
        """Error on line 3 reports the correct line."""
        script = "var a = 1;\nvar b = 2;\nvar c = {;"
        result = ScriptLinter.check(script, "javascript")
        assert len(result) == 1
        assert result[0]["line"] == 3

    def test_empty_script_returns_empty(self) -> None:
        """Empty or whitespace-only script produces no diagnostics."""
        assert ScriptLinter.check("", "javascript") == []
        assert ScriptLinter.check("   ", "javascript") == []

    def test_undefined_function_not_caught(self) -> None:
        """Undefined function calls are valid syntax (runtime error only)."""
        assert ScriptLinter.check("undefinedFunction();", "javascript") == []


def _msgs(diags: list) -> list[str]:
    return [d["message"] for d in diags]


@pytest.mark.skipif(not _deno_for_js_lint(), reason="Deno + Esprima required for JS pm lint")
def test_js_unknown_pm_member() -> None:
    """Flag unknown ``pm.*`` members in JavaScript."""
    diags = ScriptLinter.check("pm.nope();", "javascript")
    assert any("Unknown property `nope`" in m for m in _msgs(diags))


@pytest.mark.skipif(not _deno_for_js_lint(), reason="Deno + Esprima required for JS pm lint")
def test_js_namespace_called_as_function() -> None:
    """Warn when a ``pm`` namespace is invoked like a function."""
    diags = ScriptLinter.check("pm.execution();", "javascript")
    assert any("is a namespace, not a function" in m for m in _msgs(diags))
    assert diags[0]["severity"] == "warning"


def test_js_valid_usage_no_diags() -> None:
    """Valid ``pm`` usage produces no diagnostics."""
    code = 'pm.environment.set("k","v"); pm.test("t", function(){});'
    assert ScriptLinter.check(code, "javascript") == []


def test_js_postman_shim_ok() -> None:
    """Legacy ``postman`` shim calls lint clean."""
    diags = ScriptLinter.check('postman.setEnvironmentVariable("k","v")', "javascript")
    assert diags == []


@pytest.mark.skipif(not _deno_for_js_lint(), reason="Deno required for JS Esprima parse")
def test_js_parse_error_is_error_severity() -> None:
    """Syntax errors in JS are reported with error severity."""
    diags = ScriptLinter.check("function (", "javascript")
    assert diags and diags[0]["severity"] == "error"


# ===================================================================
# Python
# ===================================================================


class TestPythonLinting:
    """Tests for Python syntax and pm API via :mod:`ast`."""

    def test_valid_python_returns_empty(self) -> None:
        assert ScriptLinter.check("x = 1", "python") == []

    def test_valid_python_multiline(self) -> None:
        script = "x = 1\nif x > 0:\n    print(x)"
        assert ScriptLinter.check(script, "python") == []

    def test_syntax_error_detected(self) -> None:
        result = ScriptLinter.check("if True", "python")
        assert len(result) == 1
        assert result[0]["severity"] == "error"
        assert result[0]["line"] == 1
        assert result[0]["message"]

    def test_syntax_error_line_number(self) -> None:
        script = "x = 1\ny = 2\nif True"
        result = ScriptLinter.check(script, "python")
        assert len(result) == 1
        assert result[0]["line"] == 3

    def test_empty_script_returns_empty(self) -> None:
        assert ScriptLinter.check("", "python") == []
        assert ScriptLinter.check("   \n  ", "python") == []

    def test_undefined_name_not_caught(self) -> None:
        assert ScriptLinter.check("print(undefined_var)", "python") == []


def test_py_unknown_pm_member() -> None:
    """Flag unknown ``pm.*`` members in Python."""
    diags = ScriptLinter.check("pm.nope()", "python")
    assert any("Unknown property `nope`" in m for m in _msgs(diags))


def test_py_namespace_called() -> None:
    """Warn when a ``pm`` namespace is invoked like a function in Python."""
    diags = ScriptLinter.check("pm.execution()", "python")
    assert any("is a namespace, not a function" in m for m in _msgs(diags))


def test_py_valid_usage_no_diags() -> None:
    """Valid ``pm`` usage in Python produces no diagnostics."""
    assert ScriptLinter.check('pm.environment.set("k","v")', "python") == []


def test_typescript_skips_esprima_until_ts_parser() -> None:
    """Type annotations are accepted (no false Esprima syntax errors)."""
    assert ScriptLinter.check("const x: number = 1;", "typescript") == []
