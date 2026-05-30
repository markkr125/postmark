"""Display names and extensions for local script tree rows (basename in DB)."""

from __future__ import annotations

import re

from PySide6.QtCore import QRect

from database.models.local_scripts.virtual_paths import (
    MODULE_FORMAT_COMMONJS,
    MODULE_FORMAT_ESM,
    script_virtual_extension,
)
from services.scripting.local_path_policy import (
    is_path_safe_folder_name,
    is_path_safe_script_basename,
)
from ui.request.request_editor.scripts.script_language import (
    code_to_display,
    normalise_script_code,
)

_KNOWN_EXTENSIONS: frozenset[str] = frozenset({".cjs", ".js", ".ts", ".py"})

_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".js": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".py": "python",
}

_EXTENSION_TO_MODULE_FORMAT: dict[str, str] = {
    ".js": MODULE_FORMAT_ESM,
    ".cjs": MODULE_FORMAT_COMMONJS,
}

# Invalid path-like characters in a script basename.
_INVALID_BASENAME = re.compile(r'[\\/:*?"<>|]')

# Layout shared by delegate painting and inline rename overlay.
SCRIPT_TREE_ICON_SIZE = 16
SCRIPT_TREE_LEFT_PADDING = 2
SCRIPT_TREE_ICON_NAME_GAP = 6


def script_file_extension(language: str, module_format: str = MODULE_FORMAT_ESM) -> str:
    """Return the file suffix for *language* and *module_format*."""
    return script_virtual_extension(language, module_format)


def script_display_name(
    basename: str,
    language: str,
    module_format: str = MODULE_FORMAT_ESM,
) -> str:
    """Return ``basename`` + language extension for UI labels."""
    base = script_basename_from_stored(basename)
    if not base:
        return script_file_extension(language, module_format)
    return f"{base}{script_file_extension(language, module_format)}"


def script_basename_from_stored(name: str) -> str:
    """Strip a trailing known extension from a DB or legacy stored name."""
    text = (name or "").strip()
    lower = text.lower()
    for ext in _KNOWN_EXTENSIONS:
        if lower.endswith(ext) and len(text) > len(ext):
            return text[: -len(ext)].rstrip()
    return text


def script_language_from_extension(extension: str) -> str | None:
    """Map a file suffix to a script language code, or ``None`` if unknown."""
    return _EXTENSION_TO_LANGUAGE.get((extension or "").lower())


def script_module_format_from_extension(extension: str) -> str:
    """Map a file suffix to ``esm`` or ``commonjs``."""
    return _EXTENSION_TO_MODULE_FORMAT.get((extension or "").lower(), MODULE_FORMAT_ESM)


def script_parse_filename_input(
    text: str,
    fallback_language: str,
    fallback_module_format: str = MODULE_FORMAT_ESM,
) -> tuple[str, str, str] | None:
    """Parse inline rename input into ``(basename, language, module_format)``.

    A trailing ``.js`` / ``.cjs`` / ``.ts`` / ``.py`` selects language and format.
    When no suffix is present, *fallback_language* and *fallback_module_format* apply.
    """
    raw = (text or "").strip()
    if not raw:
        return None

    language = normalise_script_code(fallback_language)
    module_format = fallback_module_format or MODULE_FORMAT_ESM
    lower = raw.lower()
    basename = raw
    for ext, code in _EXTENSION_TO_LANGUAGE.items():
        if lower.endswith(ext) and len(raw) > len(ext):
            basename = raw[: -len(ext)].rstrip()
            language = code
            module_format = script_module_format_from_extension(ext)
            break
    else:
        basename = script_basename_from_stored(raw)

    if not basename or _INVALID_BASENAME.search(basename):
        return None
    if not basename.replace(".", "").replace("_", "").replace("-", ""):
        return None
    if not is_path_safe_script_basename(basename, language):
        return None
    if module_format == MODULE_FORMAT_COMMONJS and language != "javascript":
        return None
    return (basename, language, module_format)


def folder_name_from_input(text: str) -> str | None:
    """Validate folder create/rename input; return stripped name or ``None``."""
    raw = (text or "").strip()
    if not raw or _INVALID_BASENAME.search(raw):
        return None
    if not is_path_safe_folder_name(raw):
        return None
    return raw


def script_basename_from_input(text: str, language: str) -> str:
    """Normalize rename/create input to a basename (no extension, validated)."""
    parsed = script_parse_filename_input(text, language)
    return parsed[0] if parsed else ""


def script_rename_stem_length(
    display: str,
    language: str,
    module_format: str = MODULE_FORMAT_ESM,
) -> int:
    """Character count of the basename stem in *display* (excludes language extension)."""
    ext = script_file_extension(language, module_format)
    if ext and display.endswith(ext):
        return max(len(display) - len(ext), 0)
    return len(display)


def script_name_rect(item_rect: QRect) -> QRect:
    """Return the QRect for the basename+extension label (after the language icon)."""
    name_x = (
        item_rect.left()
        + SCRIPT_TREE_LEFT_PADDING
        + SCRIPT_TREE_ICON_SIZE
        + SCRIPT_TREE_ICON_NAME_GAP
    )
    return QRect(name_x, item_rect.top(), item_rect.right() - name_x + 1, item_rect.height())


def script_folder_label_rect(tree, item, item_rect: QRect) -> QRect:
    """Return label bounds for a folder row (branch + folder icon)."""
    from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

    if not isinstance(tree, QTreeWidget) or not isinstance(item, QTreeWidgetItem):
        return item_rect
    depth = 0
    parent = item.parent()
    while parent is not None:
        depth += 1
        parent = parent.parent()
    left = item_rect.left() + 8 + depth * tree.indentation()
    return QRect(left, item_rect.top(), max(40, item_rect.right() - left - 8), item_rect.height())


def script_tooltip(basename: str, language: str, module_format: str = MODULE_FORMAT_ESM) -> str:
    """Tooltip text for a script tree row."""
    display = script_display_name(basename, language, module_format)
    if module_format == MODULE_FORMAT_COMMONJS and language == "javascript":
        label = "JavaScript (CommonJS)"
    else:
        label = code_to_display(language)
    return f"{label} · {display}"
