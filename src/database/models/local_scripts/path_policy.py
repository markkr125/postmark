"""Path-safe segment rules for local-script virtual paths (no UI imports)."""

from __future__ import annotations

import re

JS_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_][\w.-]*$")
PY_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _normalise_language(language: str) -> str:
    """Map language codes to javascript | typescript | python."""
    code = (language or "javascript").strip().lower()
    if code in ("typescript", "ts"):
        return "typescript"
    if code in ("python", "py"):
        return "python"
    return "javascript"


def is_path_safe_folder_name(name: str) -> bool:
    """Return whether *name* is valid as a local-scripts folder segment."""
    text = (name or "").strip()
    return bool(text) and JS_PATH_SEGMENT_RE.match(text) is not None


def is_path_safe_script_basename(basename: str, language: str) -> bool:
    """Return whether *basename* (no extension) is valid for *language*."""
    text = (basename or "").strip()
    if not text:
        return False
    if _normalise_language(language) == "python":
        return PY_PATH_SEGMENT_RE.match(text) is not None
    return JS_PATH_SEGMENT_RE.match(text) is not None


def validate_folder_name(name: str) -> str:
    """Return stripped *name* or raise ``ValueError`` when not path-safe."""
    text = (name or "").strip()
    if not is_path_safe_folder_name(text):
        raise ValueError(
            f"Folder name {name!r} is not path-safe "
            "(use letters, digits, underscore; dots allowed; no spaces)"
        )
    return text


def validate_script_basename(basename: str, language: str) -> str:
    """Return stripped *basename* or raise ``ValueError`` when not path-safe."""
    text = (basename or "").strip()
    if not is_path_safe_script_basename(text, language):
        raise ValueError(
            f"Script name {basename!r} is not path-safe for {language} "
            "(no spaces or path separators)"
        )
    return text
