"""Unit tests for script output strip tab persistence and focus rules."""

from __future__ import annotations

from ui.request.request_editor.scripts.script_output_tab_prefs import (
    load_output_sub_tab_slug,
    output_has_visible_content,
    save_output_sub_tab_slug,
)


def test_output_has_visible_content_detects_logs_and_tests() -> None:
    """Console logs, test rows, and variable changes count as visible output."""
    assert output_has_visible_content({"console_logs": [{"message": "hi"}]})
    assert output_has_visible_content({"test_results": [{"name": "t", "passed": True}]})
    assert output_has_visible_content({"variable_changes": {"x": "1"}})
    assert not output_has_visible_content({})
    assert not output_has_visible_content({"console_logs": [], "test_results": []})


def test_output_sub_tab_slug_roundtrip() -> None:
    """Persist and load the output-strip tab slug per script type."""
    save_output_sub_tab_slug("pre_request", "debugger")
    assert load_output_sub_tab_slug("pre_request") == "debugger"
    save_output_sub_tab_slug("test", "iterations")
    assert load_output_sub_tab_slug("test") == "iterations"
    save_output_sub_tab_slug("pre_request", "not_a_tab")
    assert load_output_sub_tab_slug("pre_request") == "debugger"
