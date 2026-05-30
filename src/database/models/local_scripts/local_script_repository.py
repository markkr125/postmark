"""CRUD for local script folders and scripts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from database.database import get_session

from .model.local_script_folder_model import LocalScriptFolderModel
from .model.local_script_model import LocalScriptModel
from .path_policy import validate_folder_name, validate_script_basename
from .import_refs_rewrite import rewrite_relative_imports_in_db_session
from .require_refs_rewrite import rewrite_local_requires_in_db_session
from .virtual_paths import (
    MODULE_FORMAT_COMMONJS,
    MODULE_FORMAT_ESM,
    folder_virtual_prefix,
    script_virtual_rel_path,
)


def _normalize_module_format(language: str, module_format: str) -> str:
    """Return a valid module format for *language* (commonjs only on JavaScript)."""
    fmt = (module_format or MODULE_FORMAT_ESM).strip().lower()
    if fmt not in (MODULE_FORMAT_ESM, MODULE_FORMAT_COMMONJS):
        raise ValueError(
            f"module_format {module_format!r} must be {MODULE_FORMAT_ESM!r} "
            f"or {MODULE_FORMAT_COMMONJS!r}"
        )
    lang = (language or "javascript").strip().lower()
    if lang in ("typescript", "ts", "python", "py"):
        if fmt == MODULE_FORMAT_COMMONJS:
            raise ValueError("module_format 'commonjs' is only valid for JavaScript scripts")
        return MODULE_FORMAT_ESM
    return fmt


def _assert_folder_sibling_name_available(
    session: Session,
    parent_id: int | None,
    name: str,
    *,
    exclude_folder_id: int | None = None,
) -> None:
    """Raise when another folder under *parent_id* already uses *name*."""
    stmt = select(LocalScriptFolderModel.id).where(
        LocalScriptFolderModel.parent_id == parent_id,
        LocalScriptFolderModel.name == name,
    )
    if exclude_folder_id is not None:
        stmt = stmt.where(LocalScriptFolderModel.id != exclude_folder_id)
    if session.execute(stmt).first() is not None:
        raise ValueError(f"Folder name {name!r} already exists at this level")


def _assert_script_sibling_name_available(
    session: Session,
    folder_id: int,
    name: str,
    *,
    exclude_script_id: int | None = None,
) -> None:
    """Raise when another script in *folder_id* already uses *name*."""
    stmt = select(LocalScriptModel.id).where(
        LocalScriptModel.folder_id == folder_id,
        LocalScriptModel.name == name,
    )
    if exclude_script_id is not None:
        stmt = stmt.where(LocalScriptModel.id != exclude_script_id)
    if session.execute(stmt).first() is not None:
        raise ValueError(f"Script name {name!r} already exists in this folder")


def create_folder(name: str, parent_id: int | None = None) -> LocalScriptFolderModel:
    """Create a folder in the local-scripts tree."""
    safe_name = validate_folder_name(name)
    with get_session() as session:
        _assert_folder_sibling_name_available(session, parent_id, safe_name)
        folder = LocalScriptFolderModel(name=safe_name, parent_id=parent_id)
        session.add(folder)
        session.flush()
        session.refresh(folder)
        return folder


def rename_folder(folder_id: int, new_name: str) -> None:
    """Rename a local script folder (no reference rewrite)."""
    rename_folder_and_rewrite_refs(folder_id, new_name)


def rename_folder_and_rewrite_refs(folder_id: int, new_name: str) -> int:
    """Rename a folder and rewrite ``pm.require("local:…")`` prefix references."""
    safe_name = validate_folder_name(new_name)
    with get_session() as session:
        folder = session.get(LocalScriptFolderModel, folder_id)
        if folder is None:
            raise ValueError(f"No local script folder found with id={folder_id}")
        if folder.name == safe_name:
            return 0
        _assert_folder_sibling_name_available(
            session,
            folder.parent_id,
            safe_name,
            exclude_folder_id=folder_id,
        )
        old_prefix = folder_virtual_prefix(session, folder_id)
        parts = old_prefix.split("/") if old_prefix else []
        if parts:
            parts[-1] = safe_name
            new_prefix = "/".join(parts)
        else:
            new_prefix = safe_name
        folder.name = safe_name
        session.flush()
        n = rewrite_local_requires_in_db_session(
            session,
            old_prefix,
            new_prefix,
            prefix=True,
        )
        n += rewrite_relative_imports_in_db_session(
            session,
            old_prefix,
            new_prefix,
            prefix=True,
        )
        return n


def delete_folder(folder_id: int) -> None:
    """Delete a folder and its descendants (cascade)."""
    with get_session() as session:
        folder = session.get(LocalScriptFolderModel, folder_id)
        if folder is None:
            raise ValueError(f"No local script folder found with id={folder_id}")
        session.delete(folder)


def update_folder_parent(folder_id: int, new_parent_id: int | None) -> None:
    """Move a folder under a different parent."""
    with get_session() as session:
        folder = session.get(LocalScriptFolderModel, folder_id)
        if folder is None:
            raise ValueError(f"No local script folder found with id={folder_id}")
        stmt = (
            update(LocalScriptFolderModel)
            .where(LocalScriptFolderModel.id == folder_id)
            .values(parent_id=new_parent_id)
        )
        session.execute(stmt)


def create_script(
    folder_id: int,
    name: str,
    *,
    language: str = "javascript",
    module_format: str = MODULE_FORMAT_ESM,
    content: str = "",
) -> LocalScriptModel:
    """Create a script under *folder_id*."""
    safe_name = validate_script_basename(name, language)
    fmt = _normalize_module_format(language, module_format)
    with get_session() as session:
        folder = session.get(LocalScriptFolderModel, folder_id)
        if folder is None:
            raise ValueError(f"No local script folder found with id={folder_id}")
        _assert_script_sibling_name_available(session, folder_id, safe_name)
        script = LocalScriptModel(
            folder_id=folder_id,
            name=safe_name,
            language=language,
            module_format=fmt,
            content=content,
        )
        session.add(script)
        session.flush()
        session.refresh(script)
        return script


def rename_script(
    script_id: int,
    new_name: str,
    *,
    language: str | None = None,
    module_format: str | None = None,
) -> None:
    """Rename a local script (with reference rewrite when the virtual path changes)."""
    rename_script_and_rewrite_refs(
        script_id, new_name, language=language, module_format=module_format
    )


def rename_script_and_rewrite_refs(
    script_id: int,
    new_name: str,
    *,
    language: str | None = None,
    module_format: str | None = None,
) -> int:
    """Rename a script and rewrite exact ``local:`` path references."""
    with get_session() as session:
        script = session.get(LocalScriptModel, script_id)
        if script is None:
            raise ValueError(f"No local script found with id={script_id}")
        lang = language if language is not None else (script.language or "javascript")
        fmt_in = (
            module_format
            if module_format is not None
            else (script.module_format or MODULE_FORMAT_ESM)
        )
        fmt = _normalize_module_format(lang, fmt_in)
        safe_name = validate_script_basename(new_name, lang)
        _assert_script_sibling_name_available(
            session,
            script.folder_id,
            safe_name,
            exclude_script_id=script_id,
        )
        old_path = script_virtual_rel_path(session, script_id)
        script.name = safe_name
        if language is not None:
            script.language = language
        script.module_format = fmt
        session.flush()
        new_path = script_virtual_rel_path(session, script_id)
        if old_path == new_path:
            return 0
        n = rewrite_local_requires_in_db_session(
            session,
            old_path,
            new_path,
            prefix=False,
        )
        n += rewrite_relative_imports_in_db_session(
            session,
            old_path,
            new_path,
            prefix=False,
        )
        return n


def delete_script(script_id: int) -> None:
    """Delete a local script."""
    with get_session() as session:
        script = session.get(LocalScriptModel, script_id)
        if script is None:
            raise ValueError(f"No local script found with id={script_id}")
        session.delete(script)


def update_script_folder(script_id: int, new_folder_id: int) -> None:
    """Move a script to a different folder (with reference rewrite)."""
    move_script_and_rewrite_refs(script_id, new_folder_id)


def move_script_and_rewrite_refs(script_id: int, new_folder_id: int) -> int:
    """Move a script and rewrite exact ``local:`` path references."""
    with get_session() as session:
        script = session.get(LocalScriptModel, script_id)
        if script is None:
            raise ValueError(f"No local script found with id={script_id}")
        folder = session.get(LocalScriptFolderModel, new_folder_id)
        if folder is None:
            raise ValueError(f"No local script folder found with id={new_folder_id}")
        if script.folder_id == new_folder_id:
            return 0
        _assert_script_sibling_name_available(
            session,
            new_folder_id,
            script.name,
            exclude_script_id=script_id,
        )
        old_path = script_virtual_rel_path(session, script_id)
        script.folder_id = new_folder_id
        session.flush()
        new_path = script_virtual_rel_path(session, script_id)
        if old_path == new_path:
            return 0
        n = rewrite_local_requires_in_db_session(
            session,
            old_path,
            new_path,
            prefix=False,
        )
        n += rewrite_relative_imports_in_db_session(
            session,
            old_path,
            new_path,
            prefix=False,
        )
        return n


def update_script_content(
    script_id: int,
    content: str,
    language: str | None = None,
    module_format: str | None = None,
) -> None:
    """Persist editor body (and optional language / module_format) for a script."""
    with get_session() as session:
        values: dict[str, object] = {"content": content}
        if language is not None or module_format is not None:
            script = session.get(LocalScriptModel, script_id)
            if script is not None:
                lang = language if language is not None else (script.language or "javascript")
                fmt_in = (
                    module_format
                    if module_format is not None
                    else (script.module_format or MODULE_FORMAT_ESM)
                )
                if language is not None:
                    values["language"] = lang
                values["module_format"] = _normalize_module_format(lang, fmt_in)
        stmt = update(LocalScriptModel).where(LocalScriptModel.id == script_id).values(**values)
        session.execute(stmt)


def update_local_script_debug_metadata(script_id: int, metadata: dict[str, Any] | None) -> None:
    """Persist flat breakpoints/watches for a local script."""
    with get_session() as session:
        script = session.get(LocalScriptModel, script_id)
        if script is None:
            raise ValueError(f"No local script found with id={script_id}")
        script.debug_metadata = metadata if metadata else None
