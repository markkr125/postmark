"""Tests for :class:`ScriptLinter` syntax and pm-API checking."""

from __future__ import annotations

import pytest

from services.scripting.engine import ScriptLinter

# ===================================================================
# JavaScript
# ===================================================================


class TestJavaScriptLinting:
    """Tests for JavaScript validation via Esprima + V8."""

    def test_valid_js_returns_empty(self) -> None:
        """Valid JavaScript produces no diagnostics."""
        assert ScriptLinter.check("var x = 1;", "javascript") == []

    def test_valid_js_multiline(self) -> None:
        """Valid multiline JavaScript produces no diagnostics."""
        script = "var x = 1;\nif (x > 0) {\n  console.log(x);\n}"
        assert ScriptLinter.check(script, "javascript") == []

    def test_syntax_error_missing_brace(self) -> None:
        """Missing closing brace is detected."""
        script = "if (true {"
        result = ScriptLinter.check(script, "javascript")
        assert len(result) == 1
        assert result[0]["severity"] == "error"
        assert result[0]["line"] == 1
        assert "Unexpected" in result[0]["message"]

    def test_syntax_error_line_2(self) -> None:
        """Error on line 2 reports the correct line."""
        script = "var x = 1;\nif (true {"
        result = ScriptLinter.check(script, "javascript")
        assert len(result) == 1
        assert result[0]["line"] == 2

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


def test_js_unknown_pm_member() -> None:
    pytest.importorskip("py_mini_racer")
    diags = ScriptLinter.check("pm.nope();", "javascript")
    assert any("Unknown property `nope`" in m for m in _msgs(diags))


def test_js_namespace_called_as_function() -> None:
    pytest.importorskip("py_mini_racer")
    diags = ScriptLinter.check("pm.execution();", "javascript")
    assert any("is a namespace, not a function" in m for m in _msgs(diags))
    assert diags[0]["severity"] == "warning"


def test_js_valid_usage_no_diags() -> None:
    code = 'pm.environment.set("k","v"); pm.test("t", function(){});'
    assert ScriptLinter.check(code, "javascript") == []


def test_js_postman_shim_ok() -> None:
    diags = ScriptLinter.check('postman.setEnvironmentVariable("k","v")', "javascript")
    assert diags == []


def test_js_parse_error_is_error_severity() -> None:
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
    diags = ScriptLinter.check("pm.nope()", "python")
    assert any("Unknown property `nope`" in m for m in _msgs(diags))


def test_py_namespace_called() -> None:
    diags = ScriptLinter.check("pm.execution()", "python")
    assert any("is a namespace, not a function" in m for m in _msgs(diags))


def test_py_valid_usage_no_diags() -> None:
    assert ScriptLinter.check('pm.environment.set("k","v")', "python") == []
