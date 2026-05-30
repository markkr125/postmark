"""Service bridge for local script folders and scripts (UI must use this, not DB)."""

from __future__ import annotations

from typing import Any, TypedDict

from database.database import get_session
from database.models.local_scripts.local_script_query_repository import (
    fetch_all_local_scripts_tree,
    get_local_script_breadcrumb,
    get_script_by_id,
)
from database.models.local_scripts.path_index import list_virtual_paths
from database.models.local_scripts.local_script_repository import (
    create_folder,
    create_script,
    delete_folder,
    delete_script,
    move_script_and_rewrite_refs,
    rename_folder_and_rewrite_refs,
    rename_script_and_rewrite_refs,
    update_folder_parent,
    update_local_script_debug_metadata,
    update_script_content,
)
from database.models.local_scripts.model.local_script_folder_model import LocalScriptFolderModel
from database.models.local_scripts.model.local_script_model import LocalScriptModel


class LocalScriptLoadDict(TypedDict, total=False):
    """Payload for opening a local script in the centre editor."""

    id: int
    name: str
    language: str
    module_format: str
    content: str
    debug_metadata: dict[str, Any]


class LocalScriptService:
    """Static API for the local-scripts sidebar and editor tabs."""

    _path_index_cache: dict[str, int] | None = None

    @staticmethod
    def _refresh_mirror(*, script_id: int | None = None, full: bool = False) -> None:
        """Sync the Deno ``local/`` mirror after DB mutations."""
        from services.scripting.local_scripts_project.deno_config import ensure_ambient_pm
        from services.scripting.local_scripts_project.mirror import (
            remove_mirrored_script,
            sync_all,
            sync_script,
        )

        ensure_ambient_pm()
        if full:
            sync_all()
            return
        if script_id is not None and sync_script(script_id) is None:
            remove_mirrored_script(script_id)

    @staticmethod
    def invalidate_path_index_cache() -> None:
        """Clear cached ``rel_path → script_id`` map after tree mutations."""
        LocalScriptService._path_index_cache = None

    @staticmethod
    def resolve_script_id_by_virtual_path(rel: str) -> int | None:
        """Resolve a virtual ``local:…`` or bare rel path to a script primary key."""
        from services.scripting.local_script_modules import build_module_index

        path = rel.strip()
        if path.lower().startswith("local:"):
            path = path[6:].lstrip("/")
        if not path:
            return None
        if LocalScriptService._path_index_cache is None:
            with get_session() as session:
                index = build_module_index(session)
            LocalScriptService._path_index_cache = {
                rel: mod.script_id for rel, mod in index.items()
            }
        return LocalScriptService._path_index_cache.get(path)

    @staticmethod
    def fetch_all() -> dict[str, Any]:
        """Return the nested tree dict for :class:`CollectionTree`."""
        return fetch_all_local_scripts_tree()

    @staticmethod
    def list_virtual_paths(*, language: str) -> list[str]:
        """Return path-safe virtual paths for ``pm.require("local:…")`` autocomplete."""
        return list_virtual_paths(language=language)

    @staticmethod
    def get_script(script_id: int) -> LocalScriptModel | None:
        """Load one script row."""
        return get_script_by_id(script_id)

    @staticmethod
    def get_script_breadcrumb(script_id: int) -> list[dict[str, Any]]:
        """Return breadcrumb path segments for a local script tab."""
        return get_local_script_breadcrumb(script_id)

    @staticmethod
    def get_script_load_dict(script_id: int) -> LocalScriptLoadDict | None:
        """Build editor load payload for *script_id*."""
        row = get_script_by_id(script_id)
        if row is None:
            return None
        payload = LocalScriptLoadDict(
            id=row.id,
            name=row.name,
            language=row.language or "javascript",
            module_format=row.module_format or "esm",
            content=row.content or "",
        )
        if isinstance(row.debug_metadata, dict):
            payload["debug_metadata"] = row.debug_metadata
        return payload

    @staticmethod
    def create_folder(name: str, parent_id: int | None = None) -> LocalScriptFolderModel:
        """Create a folder."""
        return create_folder(name, parent_id)

    @staticmethod
    def create_script(
        folder_id: int,
        name: str,
        *,
        language: str = "javascript",
        module_format: str = "esm",
        content: str = "",
    ) -> LocalScriptModel:
        """Create a script under *folder_id*."""
        row = create_script(
            folder_id,
            name,
            language=language,
            module_format=module_format,
            content=content,
        )
        LocalScriptService.invalidate_path_index_cache()
        LocalScriptService._refresh_mirror(full=True)
        return row

    @staticmethod
    def rename_folder(folder_id: int, new_name: str) -> int:
        """Rename a folder and rewrite ``pm.require("local:…")`` references."""
        count = rename_folder_and_rewrite_refs(folder_id, new_name)
        LocalScriptService.invalidate_path_index_cache()
        LocalScriptService._refresh_mirror(full=True)
        return count

    @staticmethod
    def delete_folder(folder_id: int) -> None:
        """Delete a folder."""
        delete_folder(folder_id)
        LocalScriptService.invalidate_path_index_cache()
        LocalScriptService._refresh_mirror(full=True)

    @staticmethod
    def move_folder(folder_id: int, new_parent_id: int | None) -> None:
        """Reparent a folder."""
        update_folder_parent(folder_id, new_parent_id)
        LocalScriptService.invalidate_path_index_cache()
        LocalScriptService._refresh_mirror(full=True)

    @staticmethod
    def rename_script(
        script_id: int,
        new_name: str,
        *,
        language: str | None = None,
        module_format: str | None = None,
    ) -> int:
        """Rename a script and rewrite ``pm.require("local:…")`` references."""
        count = rename_script_and_rewrite_refs(
            script_id,
            new_name,
            language=language,
            module_format=module_format,
        )
        LocalScriptService.invalidate_path_index_cache()
        LocalScriptService._refresh_mirror(full=True)
        return count

    @staticmethod
    def delete_script(script_id: int) -> None:
        """Delete a script."""
        delete_script(script_id)
        LocalScriptService.invalidate_path_index_cache()
        LocalScriptService._refresh_mirror(script_id=script_id, full=True)

    @staticmethod
    def move_script(script_id: int, new_folder_id: int) -> int:
        """Move a script to another folder and rewrite ``local:`` references."""
        count = move_script_and_rewrite_refs(script_id, new_folder_id)
        LocalScriptService.invalidate_path_index_cache()
        LocalScriptService._refresh_mirror(full=True)
        return count

    @staticmethod
    def save_script_content(
        script_id: int,
        content: str,
        language: str | None = None,
        module_format: str | None = None,
    ) -> None:
        """Persist script body from the editor."""
        update_script_content(script_id, content, language, module_format=module_format)
        LocalScriptService._refresh_mirror(script_id=script_id)

    @staticmethod
    def merge_debug_metadata(script_id: int, metadata: dict[str, Any] | None) -> None:
        """Persist flat breakpoints/watches for a local script."""
        update_local_script_debug_metadata(script_id, metadata)
