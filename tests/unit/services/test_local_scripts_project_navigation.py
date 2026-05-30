"""Tests for ESM import navigation resolution."""

from __future__ import annotations

from database.models.local_scripts.local_script_repository import create_folder, create_script
from services.local_script_service import LocalScriptService
from services.scripting.local_scripts_project.navigation import resolve_esm_import_target_script_id


def test_resolve_esm_import_target() -> None:
    """Cursor inside a relative import resolves to the target script id."""
    root = create_folder("nav_test")
    target = create_script(
        root.id,
        "lib",
        language="javascript",
        content="export const v = 1;",
    )
    entry = create_script(
        root.id,
        "main",
        language="javascript",
        content="import { v } from './lib.js';\n",
    )
    LocalScriptService.invalidate_path_index_cache()
    source = entry.content or ""
    offset = source.index("./lib.js") + 3
    got = resolve_esm_import_target_script_id(entry.id, source, offset)
    assert got == target.id
