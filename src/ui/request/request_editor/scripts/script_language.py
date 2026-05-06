"""Script editor language codes, display names, and content heuristics."""

from __future__ import annotations

import re

# Supported script languages (code → editor / highlighter id).
_SCRIPT_CODES: frozenset[str] = frozenset({"javascript", "python", "typescript"})

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

# TypeScript-only signals (type syntax, interfaces, enums).
_TS_SNIPPET = re.compile(
    r"(\binterface\s+\w+|"
    r":\s*(string|number|boolean|any|unknown|void|\w+(\[\])?)\s*[=,)]|"
    r"\bas\s+(string|number|boolean|\w+)\b|"
    r"\benum\s+\w+|"
    r"<\w+>\(|"
    r"\btype\s+\w+\s*=)",
)


def code_to_display(code: str) -> str:
    """Return UI label for a language *code*."""
    c = code.lower().strip()
    if c == "python":
        return "Python"
    if c == "typescript":
        return "TypeScript"
    return "JavaScript"


def display_to_code(display: str) -> str:
    """Map a UI label to a language code; unknown labels default to ``javascript``."""
    key = display.strip().lower()
    if key == "python":
        return "python"
    if key == "typescript":
        return "typescript"
    return "javascript"


def normalise_script_code(code: str) -> str:
    """Return a known script code; unknown *code* strings become ``javascript``."""
    c = code.lower().strip()
    return c if c in _SCRIPT_CODES else "javascript"


def detect_script_language(text: str, *, default: str = "javascript") -> str:
    """Infer ``javascript``, ``typescript``, or ``python`` from *text*.

    Used when the user enables **Auto** mode or on debounced edits.  Empty or
    ambiguous content returns *default* (normalised).
    """
    base = normalise_script_code(default)
    stripped = text.strip()
    if not stripped:
        return base

    py_hits = len(_PY_LINE.findall(stripped))
    js_hits = len(_JS_SNIPPET.findall(stripped))
    ts_hits = len(_TS_SNIPPET.findall(stripped))

    # TS is a superset of JS — `js_hits` will usually also fire on TS code.
    # Only call it TS when at least one TS-only token appears AND it isn't
    # outweighed by Python signals.
    if ts_hits > 0 and ts_hits >= py_hits:
        return "typescript"
    if py_hits > 0 and js_hits == 0:
        return "python"
    if js_hits > 0 and py_hits == 0:
        return "javascript"
    if py_hits > js_hits:
        return "python"
    if js_hits > py_hits:
        return "javascript"
    return base
