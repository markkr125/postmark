"""Tests for local script display names and basename normalization."""

from __future__ import annotations

from ui.local_scripts.script_filename import (
    script_basename_from_input,
    script_basename_from_stored,
    script_display_name,
    script_file_extension,
    script_parse_filename_input,
    script_rename_stem_length,
)


def test_script_file_extension() -> None:
    """Each language maps to the expected suffix."""
    assert script_file_extension("javascript") == ".js"
    assert script_file_extension("javascript", "commonjs") == ".cjs"
    assert script_file_extension("typescript") == ".ts"
    assert script_file_extension("python") == ".py"
    assert script_file_extension("js") == ".js"


def test_script_display_name() -> None:
    """Display name joins basename and extension."""
    assert script_display_name("helper", "typescript") == "helper.ts"
    assert script_display_name("helper.ts", "typescript") == "helper.ts"


def test_script_rename_stem_length() -> None:
    """Inline rename selects only the basename, not the language extension."""
    display = script_display_name("helper", "typescript")
    assert script_rename_stem_length(display, "typescript") == len("helper")
    assert script_rename_stem_length("auth.cjs", "javascript", "commonjs") == len("auth")


def test_script_basename_from_stored_strips_extension() -> None:
    """Legacy DB values with extensions are normalized to basename."""
    assert script_basename_from_stored("foo.js") == "foo"
    assert script_basename_from_stored("foo.cjs") == "foo"
    assert script_basename_from_stored("bar.ts") == "bar"
    assert script_basename_from_stored("baz.py") == "baz"


def test_script_basename_from_input_strips_typed_extension() -> None:
    """Rename input may include an extension; only basename is kept."""
    assert script_basename_from_input("helper.ts", "typescript") == "helper"
    assert script_basename_from_input("helper", "typescript") == "helper"


def test_script_basename_from_input_rejects_invalid() -> None:
    """Path-like or empty names are rejected."""
    assert script_basename_from_input("", "javascript") == ""
    assert script_basename_from_input("bad/name", "javascript") == ""
    assert script_basename_from_input("...", "javascript") == ""


def test_script_parse_filename_input_extension_sets_language() -> None:
    """A typed extension selects language; basename is stored without suffix."""
    assert script_parse_filename_input("helper.ts", "javascript") == (
        "helper",
        "typescript",
        "esm",
    )
    assert script_parse_filename_input("helper", "typescript") == ("helper", "typescript", "esm")
    assert script_parse_filename_input("renamed.py", "javascript") == ("renamed", "python", "esm")
    assert script_parse_filename_input("auth.cjs", "javascript") == (
        "auth",
        "javascript",
        "commonjs",
    )


def test_script_parse_filename_input_rejects_invalid() -> None:
    """Invalid names return ``None``."""
    assert script_parse_filename_input("", "javascript") is None
    assert script_parse_filename_input("bad/name.js", "javascript") is None
    assert script_parse_filename_input("has space.js", "javascript") is None


def test_script_parse_filename_input_allows_multi_dot_basename() -> None:
    """``helper.test.js`` round-trips to basename ``helper.test``."""
    assert script_parse_filename_input("helper.test.js", "javascript") == (
        "helper.test",
        "javascript",
        "esm",
    )


def test_script_display_name_commonjs() -> None:
    """CommonJS JavaScript scripts use a ``.cjs`` suffix."""
    assert script_display_name("helper", "javascript", "commonjs") == "helper.cjs"
