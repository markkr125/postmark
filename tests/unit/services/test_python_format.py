"""Tests for :mod:`services.scripting.python_format`."""

from __future__ import annotations

from services.scripting.python_format import format_python_source


class TestFormatPythonSource:
    """Ruff-backed Python formatting."""

    def test_formats_unstyled_source(self) -> None:
        """Ruff normalises spacing in a one-line dict literal."""
        raw = 'x={"a":1,"b":2}'
        out = format_python_source(raw)
        assert out is not None
        assert out != raw
        assert " = " in out

    def test_returns_none_for_invalid_syntax(self) -> None:
        """Broken Python must not be rewritten."""
        assert format_python_source("def f(:\n") is None
