"""Tests for local script virtual path index (completion)."""

from __future__ import annotations

from database.models.local_scripts.local_script_repository import create_folder, create_script
from database.models.local_scripts.path_index import list_virtual_paths


def test_list_virtual_paths_filters_by_language() -> None:
    """JavaScript completion lists ``.js`` / ``.ts`` but not ``.py``."""
    root = create_folder("lib")
    create_script(root.id, "helper", language="javascript")
    create_script(root.id, "util", language="typescript")
    create_script(root.id, "mod", language="python")

    js_paths = list_virtual_paths(language="javascript")
    assert "lib/helper.js" in js_paths
    assert "lib/util.ts" in js_paths
    assert "lib/mod.py" not in js_paths

    create_script(
        root.id,
        "cjsmod",
        language="javascript",
        module_format="commonjs",
        content="module.exports = {};",
    )
    js_paths = list_virtual_paths(language="javascript")
    assert "lib/cjsmod.cjs" in js_paths

    py_paths = list_virtual_paths(language="python")
    assert py_paths == ["lib/mod.py"]


def test_list_virtual_paths_skips_unsafe_folder_names() -> None:
    """Legacy folder names with spaces are omitted from the index."""
    from database.database import get_session
    from database.models.local_scripts.model.local_script_folder_model import LocalScriptFolderModel

    with get_session() as session:
        session.add(LocalScriptFolderModel(name="Bad Folder", parent_id=None))
        session.flush()
    safe = create_folder("ok")
    create_script(safe.id, "a", language="javascript")

    paths = list_virtual_paths(language="javascript")
    assert paths == ["ok/a.js"]
    assert not any(" " in p for p in paths)
