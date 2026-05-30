"""Tests for the local scripts Deno project mirror."""

from __future__ import annotations

from database.models.local_scripts.local_script_repository import create_folder, create_script
from services.scripting.local_scripts_project.mirror import (
    local_mirror_root,
    mirror_path_for_rel,
    sync_all,
    sync_script,
)


def test_sync_script_writes_mirror_file() -> None:
    """``sync_script`` materialises a path-safe script under ``local/``."""
    root = create_folder("mirror_test")
    row = create_script(
        root.id,
        "helper",
        language="javascript",
        content="export default { v: 1 };",
    )
    path = sync_script(row.id)
    assert path is not None
    assert path == mirror_path_for_rel("mirror_test/helper.js")
    assert path.read_text(encoding="utf-8") == "export default { v: 1 };\n"


def test_sync_all_prunes_orphan() -> None:
    """``sync_all`` removes mirror files with no DB row."""
    root = create_folder("prune_test")
    row = create_script(root.id, "gone", language="javascript", content="// x")
    sync_script(row.id)
    orphan = local_mirror_root() / "phantom/orphan.js"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("// stale", encoding="utf-8")
    sync_all()
    assert not orphan.is_file()
    assert mirror_path_for_rel("prune_test/gone.js").is_file()
