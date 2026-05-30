"""Tests for ESM import-graph resolution between local scripts."""

from __future__ import annotations

from database.models.local_scripts.local_script_repository import create_folder, create_script
from services.scripting.local_scripts_project.import_graph import (
    esm_import_string_tail,
    iter_static_relative_import_specs,
    relative_import_suggestions,
    resolve_import_closure,
)


def test_iter_static_relative_import_specs_ts() -> None:
    """Regex scanner picks up ``import type`` from TypeScript."""
    src = "import type { Foo } from './types.ts';\nexport { x } from '../lib/a.js';\n"
    specs = iter_static_relative_import_specs(src)
    assert "./types.ts" in specs
    assert "../lib/a.js" in specs


def test_resolve_import_closure_transitive() -> None:
    """Import graph follows static imports transitively."""
    root = create_folder("graph")
    create_script(root.id, "leaf", language="javascript", content="export default { v: 1 };")
    create_script(
        root.id,
        "main",
        language="javascript",
        content='import x from "./leaf.js";\nconsole.log(x);\n',
    )
    mods = resolve_import_closure("graph/main.js", "javascript")
    assert "graph/main.js" in mods
    assert "graph/leaf.js" in mods


def test_resolve_import_cycle_includes_both_modules() -> None:
    """ESM import cycles are allowed (Deno runs them); closure lists each file once."""
    root = create_folder("cycle")
    create_script(
        root.id,
        "a",
        language="javascript",
        content='import "./b.js";',
    )
    create_script(
        root.id,
        "b",
        language="javascript",
        content='import "./a.js";',
    )
    mods = resolve_import_closure("cycle/a.js", "javascript")
    assert "cycle/a.js" in mods
    assert "cycle/b.js" in mods


def test_esm_import_string_tail() -> None:
    """Unclosed import strings yield the typed path tail at the cursor."""
    assert esm_import_string_tail("import { x } from './ma") == "./ma"
    assert esm_import_string_tail('import { x } from "./ma') == "./ma"
    assert esm_import_string_tail("export * from '../") == "../"
    assert esm_import_string_tail("import './side") == "./side"
    assert esm_import_string_tail("const x = './not-an-import") is None
    assert esm_import_string_tail("import { x } from './done.js';") is None


def test_relative_import_suggestions(monkeypatch) -> None:
    """Sibling paths are relative to *from_rel*, filtered and sorted."""
    paths = [
        "home2/test.js",
        "home2/mapper.js",
        "home2/sub/deep.ts",
        "home/utils.js",
        "skip.py",
    ]
    monkeypatch.setattr(
        "services.local_script_service.LocalScriptService.list_virtual_paths",
        lambda *, language: paths,
    )
    got = relative_import_suggestions("home2/test.js", "", "javascript")
    assert got == ["./mapper.js", "./sub/deep.ts", "../home/utils.js"]
    assert relative_import_suggestions("home2/test.js", "../", "javascript") == ["../home/utils.js"]
    assert relative_import_suggestions(None, "", "javascript") == []
