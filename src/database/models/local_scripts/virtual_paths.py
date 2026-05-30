"""Virtual POSIX paths for local scripts (folder chain + basename + extension)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .model.local_script_folder_model import LocalScriptFolderModel
from .model.local_script_model import LocalScriptModel

MODULE_FORMAT_ESM = "esm"
MODULE_FORMAT_COMMONJS = "commonjs"

_KNOWN_STRIP_EXTENSIONS: tuple[str, ...] = (".cjs", ".js", ".ts", ".py")


def script_virtual_extension(language: str, module_format: str = MODULE_FORMAT_ESM) -> str:
    """Return the virtual file suffix for *language* and *module_format*."""
    code = (language or "javascript").strip().lower()
    fmt = (module_format or MODULE_FORMAT_ESM).strip().lower()
    if code in ("typescript", "ts"):
        return ".ts"
    if code in ("python", "py"):
        return ".py"
    if fmt == MODULE_FORMAT_COMMONJS:
        return ".cjs"
    return ".js"


def _script_basename_from_stored(name: str) -> str:
    """Strip a trailing known extension from a stored script name."""
    text = (name or "").strip()
    lower = text.lower()
    for ext in _KNOWN_STRIP_EXTENSIONS:
        if lower.endswith(ext) and len(text) > len(ext):
            return text[: -len(ext)].rstrip()
    return text


def folder_virtual_prefix(session: Session, folder_id: int) -> str:
    """Return the virtual path prefix for a folder (no trailing slash)."""
    parts: list[str] = []
    current_id: int | None = folder_id
    while current_id is not None:
        folder = session.get(LocalScriptFolderModel, current_id)
        if folder is None:
            break
        parts.insert(0, folder.name)
        current_id = folder.parent_id
    return "/".join(parts)


def script_virtual_rel_path(session: Session, script_id: int) -> str:
    """Return the full virtual file path for a script (e.g. ``auth/utils/helper.cjs``)."""
    script = session.get(LocalScriptModel, script_id)
    if script is None:
        raise ValueError(f"No local script found with id={script_id}")
    basename = _script_basename_from_stored(script.name)
    lang = script.language or "javascript"
    fmt = script.module_format or MODULE_FORMAT_ESM
    ext = script_virtual_extension(lang, fmt)
    filename = f"{basename}{ext}"
    prefix = folder_virtual_prefix(session, script.folder_id)
    if prefix:
        return f"{prefix}/{filename}"
    return filename
