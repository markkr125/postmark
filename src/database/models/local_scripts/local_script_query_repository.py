"""Read-only queries for the local scripts sidebar tree."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from database.database import get_session

from .model.local_script_folder_model import LocalScriptFolderModel
from .model.local_script_model import LocalScriptModel

_YIELD_CHUNK = 500


def fetch_all_local_scripts_tree() -> dict[str, Any]:
    """Return root folders as a nested dict (same shape as collections tree).

    Folders use ``type="folder"``.  Scripts use ``type="script"`` with a
    ``language`` field (javascript | typescript | python).
    """
    folder_by_id: dict[int, dict[str, Any]] = {}

    with get_session() as session:
        folder_stmt = select(
            LocalScriptFolderModel.id,
            LocalScriptFolderModel.name,
            LocalScriptFolderModel.parent_id,
        )
        for fid, fname, pid in session.execute(folder_stmt).yield_per(_YIELD_CHUNK):
            folder_by_id[fid] = {
                "id": fid,
                "name": fname,
                "parent_id": pid,
                "type": "folder",
                "children": {},
            }

        script_stmt = select(
            LocalScriptModel.id,
            LocalScriptModel.name,
            LocalScriptModel.language,
            LocalScriptModel.module_format,
            LocalScriptModel.folder_id,
        )
        for sid, sname, lang, mod_fmt, folder_id in session.execute(script_stmt).yield_per(
            _YIELD_CHUNK
        ):
            parent = folder_by_id.get(folder_id)
            if parent is not None:
                parent["children"][str(sid)] = {
                    "type": "script",
                    "id": sid,
                    "name": sname,
                    "language": lang or "javascript",
                    "module_format": mod_fmt or "esm",
                }

    roots: dict[str, Any] = {}
    for fid, node in folder_by_id.items():
        pid = node.pop("parent_id")
        if pid is None:
            roots[str(fid)] = node
        else:
            parent = folder_by_id.get(pid)
            if parent is not None:
                parent["children"][str(fid)] = node

    return roots


def get_script_by_id(script_id: int) -> LocalScriptModel | None:
    """Return the script row for *script_id*, or ``None``."""
    with get_session() as session:
        return session.get(LocalScriptModel, script_id)


def get_local_script_breadcrumb(script_id: int) -> list[dict[str, Any]]:
    """Return breadcrumb segments from ``Local scripts`` root to *script_id*.

    Each entry has ``id``, ``name``, and ``type`` (``folder`` or ``script``).
    The synthetic root uses ``id`` ``0``.
    """
    with get_session() as session:
        script = session.get(LocalScriptModel, script_id)
        if script is None:
            return [{"id": 0, "name": "Local scripts", "type": "local_scripts_root"}]
        path: list[dict[str, Any]] = [
            {"id": script.id, "name": script.name, "type": "script"},
        ]
        current_folder_id: int | None = script.folder_id
        while current_folder_id is not None:
            folder = session.get(LocalScriptFolderModel, current_folder_id)
            if folder is None:
                break
            path.insert(0, {"id": folder.id, "name": folder.name, "type": "folder"})
            current_folder_id = folder.parent_id
        path.insert(0, {"id": 0, "name": "Local scripts", "type": "local_scripts_root"})
        return path
