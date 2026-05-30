"""Tests for local script folder/script repositories."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from database import database as db_module
from database.database import get_session, init_db
from database.models.local_scripts.local_script_query_repository import (
    fetch_all_local_scripts_tree,
    get_local_script_breadcrumb,
)
from database.models.local_scripts.local_script_repository import (
    create_folder,
    create_script,
    delete_script,
    rename_script,
)
from services.local_script_service import LocalScriptService


def test_create_folder_and_script_tree() -> None:
    """Folders and scripts appear in the nested tree dict."""
    root = create_folder("Scripts")
    script = create_script(
        root.id,
        "Helper",
        language="javascript",
        module_format="esm",
        content="// hi",
    )

    tree = fetch_all_local_scripts_tree()
    assert str(root.id) in tree
    children = tree[str(root.id)]["children"]
    assert str(script.id) in children
    assert children[str(script.id)]["type"] == "script"
    assert children[str(script.id)]["language"] == "javascript"
    assert children[str(script.id)]["module_format"] == "esm"

    loaded = LocalScriptService.get_script_load_dict(script.id)
    assert loaded is not None
    assert loaded["module_format"] == "esm"
    assert loaded["content"] == "// hi"

    rename_script(script.id, "Renamed")
    delete_script(script.id)
    assert LocalScriptService.get_script(script.id) is None


def test_local_script_breadcrumb_includes_folder_chain() -> None:
    """Breadcrumb walks folder parents from script to ``Local scripts`` root."""
    root = create_folder("Scripts")
    nested = create_folder("Nested", parent_id=root.id)
    script = create_script(nested.id, "Helper", language="javascript")

    crumbs = get_local_script_breadcrumb(script.id)
    names = [c["name"] for c in crumbs]
    assert names == ["Local scripts", "Scripts", "Nested", "Helper"]
    assert crumbs[-1]["type"] == "script"
    assert crumbs[0]["type"] == "local_scripts_root"
    assert crumbs[0]["id"] == 0


def test_create_commonjs_script() -> None:
    """CommonJS scripts persist ``module_format`` and use ``.cjs`` virtual paths."""
    from database.models.local_scripts.virtual_paths import script_virtual_rel_path
    from database.database import get_session

    root = create_folder("auth")
    script = create_script(
        root.id,
        "helper",
        language="javascript",
        module_format="commonjs",
        content="module.exports = {};",
    )
    with get_session() as session:
        assert script_virtual_rel_path(session, script.id) == "auth/helper.cjs"


def test_commonjs_rejected_for_non_javascript() -> None:
    """``module_format='commonjs'`` is invalid for TypeScript."""
    root = create_folder("lib")
    with pytest.raises(ValueError, match="commonjs"):
        create_script(root.id, "bad", language="typescript", module_format="commonjs")


def test_migration_adds_module_format_default(tmp_path) -> None:
    """Legacy DBs without ``module_format`` get ``NOT NULL DEFAULT 'esm'`` on upgrade."""
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE local_script_folders ("
                "id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, parent_id INTEGER)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE local_scripts ("
                "id INTEGER PRIMARY KEY, folder_id INTEGER NOT NULL, "
                "name VARCHAR(255) NOT NULL, language VARCHAR(32) DEFAULT 'javascript', "
                "content TEXT)"
            )
        )
        conn.execute(text("INSERT INTO local_script_folders (id, name) VALUES (1, 'f')"))
        conn.execute(
            text(
                "INSERT INTO local_scripts (id, folder_id, name, language, content) "
                "VALUES (1, 1, 'legacy', 'javascript', '// old')"
            )
        )

    db_module._engine = None
    db_module._SessionLocal = None
    init_db(db_path)

    with get_session() as session:
        row = session.execute(
            text("SELECT module_format FROM local_scripts WHERE id = 1")
        ).scalar_one()
    assert row == "esm"
