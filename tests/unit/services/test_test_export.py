"""Unit tests for script test-result export helpers."""

from __future__ import annotations

from ui.request.request_editor.scripts.test_export import (
    export_test_results_json,
    export_test_results_junit,
)


def test_export_json_round_trip() -> None:
    """JSON export preserves test result fields."""
    rows = [
        {
            "name": "status ok",
            "passed": True,
            "error": None,
            "duration_ms": 12.5,
            "source_name": "inline",
        },
    ]
    import json

    parsed = json.loads(export_test_results_json(rows))
    assert parsed[0]["name"] == "status ok"


def test_export_junit_escapes_special_chars() -> None:
    """JUnit XML escapes failure messages."""
    rows = [
        {
            "name": 'check "quotes"',
            "passed": False,
            "error": "bad <xml>",
            "duration_ms": 1000,
            "source_name": "suite-a",
        },
    ]
    xml = export_test_results_junit(rows, suite_name="My Request")
    assert 'name="check &quot;quotes&quot;"' in xml
    assert "bad &lt;xml&gt;" in xml
    assert 'time="1.000"' in xml
