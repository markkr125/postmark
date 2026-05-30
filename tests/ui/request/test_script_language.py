"""Unit tests for script language detection and display helpers."""

from __future__ import annotations

import pytest

from ui.request.request_editor.scripts.script_language import (
    code_to_display,
    detect_script_language,
    display_to_code,
    normalise_script_code,
)


@pytest.mark.parametrize(
    ("code", "display"),
    [
        ("javascript", "JavaScript"),
        ("JavaScript", "JavaScript"),
        ("typescript", "TypeScript"),
        ("python", "Python"),
        ("PYTHON", "Python"),
    ],
)
def test_code_to_display(code: str, display: str) -> None:
    """``code_to_display`` normalises codes to UI labels."""
    assert code_to_display(code) == display


@pytest.mark.parametrize(
    ("display", "code"),
    [
        ("JavaScript", "javascript"),
        ("TypeScript", "typescript"),
        ("python", "python"),
        ("  Python  ", "python"),
        ("Unknown", "javascript"),
    ],
)
def test_display_to_code(display: str, code: str) -> None:
    """``display_to_code`` maps labels to editor language codes."""
    assert display_to_code(display) == code


def test_normalise_script_code_unknown_defaults_to_javascript() -> None:
    """Unknown stored codes map to ``javascript``."""
    assert normalise_script_code("ruby") == "javascript"
    assert normalise_script_code("PYTHON") == "python"
    assert normalise_script_code("typescript") == "typescript"


def test_detect_empty_uses_default() -> None:
    """Blank text returns the provided default."""
    assert detect_script_language("", default="javascript") == "javascript"
    assert detect_script_language("   \n", default="python") == "python"


def test_detect_pm_test_is_javascript() -> None:
    """Postmark-style tests imply JavaScript."""
    src = "pm.test('x', () => { pm.response.to.have.status(200); });"
    assert detect_script_language(src, default="python") == "javascript"


def test_detect_def_is_python() -> None:
    """A top-level ``def`` implies Python."""
    src = "def foo():\n    pass\n"
    assert detect_script_language(src, default="javascript") == "python"


def test_detect_import_from_is_python() -> None:
    """``from … import`` at line start selects Python."""
    assert detect_script_language("from json import loads\n", default="javascript") == "python"


def test_detect_ambiguous_uses_default() -> None:
    """When neither side dominates, keep *default*."""
    assert detect_script_language("x = 1\n", default="javascript") == "javascript"
    assert detect_script_language("x = 1\n", default="python") == "python"


def test_detect_interface_and_annotations_is_typescript() -> None:
    """TypeScript-only syntax selects ``typescript``."""
    assert (
        detect_script_language("interface Foo { id: number }", default="javascript") == "typescript"
    )


def test_detect_const_without_types_is_javascript() -> None:
    """Plain JS without type syntax stays ``javascript``."""
    assert detect_script_language("const x = 1;", default="python") == "javascript"


def test_detect_import_os_is_python() -> None:
    """``import os`` selects Python over JS."""
    assert detect_script_language("import os", default="javascript") == "python"
