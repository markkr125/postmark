"""Build virtual path lists for ``pm.require("local:…")`` completion and resolve."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.database import get_session

from .model.local_script_folder_model import LocalScriptFolderModel
from .model.local_script_model import LocalScriptModel
from .path_policy import is_path_safe_folder_name, is_path_safe_script_basename
from .virtual_paths import (
    MODULE_FORMAT_ESM,
    _script_basename_from_stored,
    script_virtual_extension,
)


def _folder_chain_names(session: Session, folder_id: int) -> list[str]:
    """Return folder segment names from root to *folder_id*."""
    parts: list[str] = []
    current_id: int | None = folder_id
    while current_id is not None:
        folder = session.get(LocalScriptFolderModel, current_id)
        if folder is None:
            break
        parts.insert(0, folder.name)
        current_id = folder.parent_id
    return parts


def _is_path_safe_chain(folder_names: list[str], basename: str, language: str) -> bool:
    """Return whether every segment in a virtual path is path-safe."""
    if not is_path_safe_script_basename(basename, language):
        return False
    return all(is_path_safe_folder_name(name) for name in folder_names)


def _virtual_path_for_row(
    folder_names: list[str],
    script_name: str,
    language: str,
    module_format: str = MODULE_FORMAT_ESM,
) -> str | None:
    """Return the virtual file path for a script row, or ``None`` if not path-safe."""
    basename = _script_basename_from_stored(script_name)
    lang = language or "javascript"
    if not _is_path_safe_chain(folder_names, basename, lang):
        return None
    ext = script_virtual_extension(lang, module_format)
    filename = f"{basename}{ext}"
    if folder_names:
        return "/".join(folder_names) + "/" + filename
    return filename


def _language_matches_extension(language: str, ext: str) -> bool:
    """Return whether a running script language may import *ext*."""
    code = (language or "javascript").strip().lower()
    if code in ("python", "py"):
        return ext == ".py"
    if code in ("typescript", "ts"):
        return ext in (".js", ".ts", ".cjs")
    return ext in (".js", ".ts", ".cjs")


def list_virtual_paths_in_session(session: Session, *, language: str) -> list[str]:
    """Return sorted unique virtual paths for path-safe scripts matching *language*."""
    folder_names_by_id: dict[int, list[str]] = {}

    folder_stmt = select(
        LocalScriptFolderModel.id,
        LocalScriptFolderModel.name,
        LocalScriptFolderModel.parent_id,
    )
    folders: dict[int, tuple[str, int | None]] = {}
    for fid, fname, pid in session.execute(folder_stmt):
        folders[fid] = (fname, pid)

    def names_for(fid: int) -> list[str]:
        if fid in folder_names_by_id:
            return folder_names_by_id[fid]
        fname, pid = folders[fid]
        chain = [*names_for(pid), fname] if pid is not None and pid in folders else [fname]
        folder_names_by_id[fid] = chain
        return chain

    script_stmt = select(
        LocalScriptModel.folder_id,
        LocalScriptModel.name,
        LocalScriptModel.language,
        LocalScriptModel.module_format,
    )
    paths: set[str] = set()
    for folder_id, sname, slang, mod_fmt in session.execute(script_stmt):
        if folder_id not in folders:
            continue
        chain = names_for(folder_id)
        lang = slang or "javascript"
        fmt = mod_fmt or MODULE_FORMAT_ESM
        rel = _virtual_path_for_row(chain, sname, lang, fmt)
        if rel is None:
            continue
        ext = rel[rel.rfind(".") :]
        if _language_matches_extension(language, ext):
            paths.add(rel)
    return sorted(paths)


def list_virtual_paths(*, language: str) -> list[str]:
    """Return sorted virtual paths for completion (path-safe rows only)."""
    with get_session() as session:
        return list_virtual_paths_in_session(session, language=language)
