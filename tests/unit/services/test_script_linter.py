"""Tests for :class:`ScriptLinter` syntax checking.

Verifies that JavaScript and Python scripts are validated without
execution, producing correct line/column/message tuples for errors
and ``None`` for valid scripts.
"""

from __future__ import annotations

from services.scripting.engine import ScriptLinter

# ===================================================================
# JavaScript syntax checking
# ===================================================================


class TestJavaScriptLinting:
    """Tests for JavaScript syntax validation via V8 ``new Function()``."""

    def test_valid_js_returns_none(self) -> None:
        """Valid JavaScript produces no error."""
        result = ScriptLinter.check("var x = 1;", "javascript")
        assert result is None

    def test_valid_js_multiline(self) -> None:
        """Valid multiline JavaScript produces no error."""
        script = "var x = 1;\nif (x > 0) {\n  console.log(x);\n}"
        result = ScriptLinter.check(script, "javascript")
        assert result is None

    def test_syntax_error_missing_brace(self) -> None:
        """Missing closing brace is detected."""
        script = "if (true {"
        result = ScriptLinter.check(script, "javascript")
        assert result is not None
        msg, line, col = result
        assert line == 1
        assert "Unexpected" in msg

    def test_syntax_error_line_number(self) -> None:
        """Error on line 2 reports the correct line."""
        script = "var x = 1;\nif (true {"
        result = ScriptLinter.check(script, "javascript")
        assert result is not None
        _, line, _ = result
        assert line == 2

    def test_syntax_error_line_3(self) -> None:
        """Error on line 3 reports the correct line."""
        script = "var a = 1;\nvar b = 2;\nvar c = {;"
        result = ScriptLinter.check(script, "javascript")
        assert result is not None
        _, line, _ = result
        assert line == 3

    def test_empty_script_returns_none(self) -> None:
        """Empty or whitespace-only script produces no error."""
        assert ScriptLinter.check("", "javascript") is None
        assert ScriptLinter.check("   ", "javascript") is None

    def test_undefined_function_not_caught(self) -> None:
        """Undefined function calls are valid syntax (runtime error only)."""
        result = ScriptLinter.check("undefinedFunction();", "javascript")
        assert result is None


# ===================================================================
# Python syntax checking
# ===================================================================


class TestPythonLinting:
    """Tests for Python syntax validation via ``ast.parse()``."""

    def test_valid_python_returns_none(self) -> None:
        """Valid Python produces no error."""
        result = ScriptLinter.check("x = 1", "python")
        assert result is None

    def test_valid_python_multiline(self) -> None:
        """Valid multiline Python produces no error."""
        script = "x = 1\nif x > 0:\n    print(x)"
        result = ScriptLinter.check(script, "python")
        assert result is None

    def test_syntax_error_detected(self) -> None:
        """Invalid Python syntax is detected."""
        result = ScriptLinter.check("if True", "python")
        assert result is not None
        msg, line, col = result
        assert line == 1
        assert msg  # non-empty message

    def test_syntax_error_line_number(self) -> None:
        """Error on line 3 reports the correct line."""
        script = "x = 1\ny = 2\nif True"
        result = ScriptLinter.check(script, "python")
        assert result is not None
        _, line, _ = result
        assert line == 3

    def test_empty_script_returns_none(self) -> None:
        """Empty or whitespace-only script produces no error."""
        assert ScriptLinter.check("", "python") is None
        assert ScriptLinter.check("   \n  ", "python") is None

    def test_undefined_name_not_caught(self) -> None:
        """Undefined names are valid syntax (runtime error only)."""
        result = ScriptLinter.check("print(undefined_var)", "python")
        assert result is None
