"""Tests for persisted script debug metadata."""

from __future__ import annotations

from services.scripting.context import normalize_events
from services.scripting.debug_script_metadata import (
    DEBUG_METADATA_KEY,
    MAX_CONDITION_BYTES,
    merge_debug_into_scripts_dict,
    parse_from_local_metadata,
    parse_from_scripts_dict,
    scripts_dict_has_debug,
    slice_from_editor,
    slice_is_empty,
    slice_to_local_metadata,
    truncate_condition,
)


def test_normalize_events_skips_debug() -> None:
    """``debug`` must not appear as executable script text."""
    out = normalize_events(
        {
            "pre_request": "console.log(1)",
            DEBUG_METADATA_KEY: {
                "pre_request": {"breakpoints": [{"line": 1, "condition": None}], "watches": []},
            },
        }
    )
    assert out == {"pre_request": "console.log(1)"}


def test_parse_and_merge_host_a() -> None:
    """Round-trip nested pre/test debug under scripts dict."""
    scripts = {
        "pre_request": "x",
        DEBUG_METADATA_KEY: {
            "pre_request": {
                "breakpoints": [{"line": 3, "condition": "a > 1"}],
                "watches": ["pm.a"],
            },
            "test": {"breakpoints": [], "watches": []},
        },
    }
    per_type = parse_from_scripts_dict(scripts)
    assert per_type["pre_request"]["breakpoints"][0]["line"] == 3
    merged = merge_debug_into_scripts_dict({"pre_request": "x"}, per_type)
    assert scripts_dict_has_debug(merged)
    assert merged[DEBUG_METADATA_KEY]["pre_request"]["watches"] == ["pm.a"]


def test_debug_only_scripts_dict() -> None:
    """Debug-only payload is non-empty for persistence."""
    per_type = parse_from_scripts_dict(None)
    per_type["pre_request"] = slice_from_editor({5: None}, [])
    per_type["test"] = parse_from_scripts_dict(None)["test"]
    merged = merge_debug_into_scripts_dict(None, per_type)
    assert merged is not None
    assert merged.get("pre_request") is None
    assert scripts_dict_has_debug(merged)


def test_local_flat_metadata() -> None:
    """Local script column uses flat slice shape."""
    blob = {"breakpoints": [{"line": 0, "condition": None}], "watches": ["x"]}
    sl = parse_from_local_metadata(blob)
    assert not slice_is_empty(sl)
    out = slice_to_local_metadata(sl)
    assert out["watches"] == ["x"]


def test_truncate_condition() -> None:
    """Conditions longer than the cap are truncated, not dropped."""
    long_text = "x" * (MAX_CONDITION_BYTES + 50)
    result = truncate_condition(long_text)
    assert result is not None
    assert len(result.encode("utf-8")) <= MAX_CONDITION_BYTES
