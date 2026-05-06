"""Script editor language codes, display names, and content heuristics."""

from __future__ import annotations

import re

# Supported script languages (code → editor / highlighter id).
_SCRIPT_CODES: frozenset[str] = frozenset({"javascript", "python"})

# Strong Python signals (start of a line, after optional whitespace).
_PY_LINE = re.compile(
    r"^\s*("
    r"from\s+__future__\s+import|"
    r"from\s+\w+\s+import\s+|"
    r"import\s+\w+|"
    r"def\s+\w+\s*\(|"
    r"class\s+\w+\s*[\(:]|"
    r"if\s+__name__\s*==\s*['\"]__main__['\"]"
    r")",
    re.MULTILINE,
)

# JavaScript / Postmark-style script signals.
_JS_SNIPPET = re.compile(
    r"(pm\.|console\.|=>|\b(const|let|var)\s+\w+|\bfunction\s*\(|\basync\s+function\b)",
)


def code_to_display(code: str) -> str:
    """Return UI label for a language *code* (``javascript`` / ``python``)."""
    c = code.lower().strip()
    if c == "python":
        return "Python"
    return "JavaScript"


def display_to_code(display: str) -> str:
    """Map a UI label to a language code; unknown labels default to ``javascript``."""
    key = display.strip().lower()
    if key == "python":
        return "python"
    return "javascript"


def normalise_script_code(code: str) -> str:
    """Return ``javascript`` or ``python``; unknown *code* strings become ``javascript``."""
    c = code.lower().strip()
    return c if c in _SCRIPT_CODES else "javascript"


def detect_script_language(text: str, *, default: str = "javascript") -> str:
    """Infer ``javascript`` or ``python`` from *text* using lightweight heuristics.

    Used when the user enables **Auto** mode or on debounced edits.  Empty or
    ambiguous content returns *default*.
    """
    base = normalise_script_code(default)
    stripped = text.strip()
    if not stripped:
        return base

    py_hits = len(_PY_LINE.findall(stripped))
    js_hits = len(_JS_SNIPPET.findall(stripped))

    if py_hits > 0 and js_hits == 0:
        return "python"
    if js_hits > 0 and py_hits == 0:
        return "javascript"
    if py_hits > js_hits:
        return "python"
    if js_hits > py_hits:
        return "javascript"
    return base
