"""Tests for console ``source_line`` capture helpers."""

from __future__ import annotations

from services.scripting.py_runtime import python_console_frame_to_editor_line


def test_python_console_frame_to_editor_line_outside_call() -> None:
    """Without a ``<script>`` frame the helper returns ``None``."""

    def outer() -> int | None:
        return python_console_frame_to_editor_line()

    assert outer() is None
