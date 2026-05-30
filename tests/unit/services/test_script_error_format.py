"""Tests for :mod:`services.scripting.script_error_format`."""

from __future__ import annotations

from services.scripting.script_error_format import format_script_runtime_error


class TestFormatScriptRuntimeError:
    """User-facing script error summaries."""

    def test_surfaces_pm_response_unavailable_message(self) -> None:
        raw = (
            'Traceback...\nFile "<script>", line 2\n'
            "AttributeError: pm.response is not available: this script runs before"
        )
        out = format_script_runtime_error(raw)
        assert out.startswith("pm.response is not available")

    def test_collapses_to_script_line_and_exception(self) -> None:
        raw = (
            'File "/usr/foo.py", line 1\n'
            'File "<script>", line 2, in <module>\n'
            "ValueError: bad token"
        )
        out = format_script_runtime_error(raw)
        assert 'File "<script>", line 2' in out
        assert out.endswith("ValueError: bad token")
