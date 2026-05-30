"""Tests for relative import path rewriting on local script rename."""

from __future__ import annotations

from database.models.local_scripts.import_refs_rewrite import rewrite_relative_imports_in_text
from database.models.local_scripts.local_script_repository import create_folder, create_script


def test_rewrite_import_on_exact_path_rename() -> None:
    """Renaming ``a/old.js`` updates an import that resolved to that file."""
    root = create_folder("imp_rw")
    create_script(
        root.id,
        "consumer",
        language="javascript",
        content="import { x } from './old.js';\n",
    )
    create_script(root.id, "old", language="javascript", content="export const x = 1;\n")
    out = rewrite_relative_imports_in_text(
        "import { x } from './old.js';",
        "imp_rw/consumer.js",
        "imp_rw/old.js",
        "imp_rw/new.js",
        prefix=False,
    )
    assert "./new.js" in out
