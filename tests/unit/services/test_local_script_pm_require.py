"""Tests for ``pm.require("local:…")`` resolution and JS bundling."""

from __future__ import annotations

import pytest

from database.models.local_scripts.local_script_repository import create_folder, create_script
from services.scripting.js_runtime import (
    _pm_require_local_imports_block,
    prepare_pm_require_bundle,
)
from services.scripting.local_script_modules import resolve_required
from services.scripting.runtime_settings import RuntimeSettings


def _deno_runtime_available() -> bool:
    """Return True when Deno is available for integration tests."""
    st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
    return bool(st.get("available"))


def test_resolve_local_module_transitive() -> None:
    """Resolver follows ``pm.require("local:…")`` in local script sources."""
    root = create_folder("lib")
    leaf = create_script(
        root.id,
        "leaf",
        language="javascript",
        content="export default { v: 1 };",
    )
    main = create_script(
        root.id,
        "main",
        language="javascript",
        content='const m = pm.require("local:lib/leaf.js");',
    )

    mods = resolve_required(
        'const x = pm.require("local:lib/main.js");',
        "javascript",
    )
    assert "lib/main.js" in mods
    assert "lib/leaf.js" in mods
    assert mods["lib/leaf.js"].script_id == leaf.id
    assert mods["lib/main.js"].script_id == main.id


def test_resolve_follows_static_imports_from_required_module() -> None:
    """A ``pm.require``-d module's static ESM imports are mirrored (regression).

    A ``.ts`` module pulled in via ``pm.require`` that uses ``import … from`` to
    reach a sibling must have that sibling included in the closure — otherwise
    Deno fails at runtime with ``Module not found``.
    """
    root = create_folder("lib")
    dep = create_script(
        root.id,
        "dep",
        language="javascript",
        content="export const v = 1;",
    )
    main = create_script(
        root.id,
        "main",
        language="typescript",
        content='import { v } from "./dep.js";\nexport default v;',
    )

    mods = resolve_required('const x = pm.require("local:lib/main.ts");', "javascript")

    assert "lib/main.ts" in mods
    assert "lib/dep.js" in mods  # static import followed, not only pm.require
    assert mods["lib/dep.js"].script_id == dep.id
    assert mods["lib/main.ts"].script_id == main.id


def test_resolve_cycle_raises() -> None:
    """Cycles must raise with ``cycle`` in the message."""
    root = create_folder("a")
    create_script(
        root.id,
        "one",
        language="javascript",
        content='pm.require("local:a/two.js");',
    )
    create_script(
        root.id,
        "two",
        language="javascript",
        content='pm.require("local:a/one.js");',
    )
    with pytest.raises(ValueError, match="cycle"):
        resolve_required('pm.require("local:a/one.js");', "javascript")


def test_local_imports_block_registers_specifiers() -> None:
    """Bundle preamble maps ``local:`` paths to static imports."""
    auth = create_folder("auth")
    create_script(auth.id, "helper", language="javascript", content="export default {};")
    mods = resolve_required('pm.require("local:auth/helper.js");', "javascript")
    block = _pm_require_local_imports_block(mods)
    assert './local/auth/helper.js"' in block or "./local/auth/helper.js" in block
    assert '"local:auth/helper.js"' in block


def test_lsp_index_emits_local_require_overload(monkeypatch, tmp_path) -> None:
    """``sync_pm_require_types`` types ``pm.require('local:…')`` for the Deno LSP.

    Regression: local: specifiers were filtered out of the index, so the call
    fell through to ``require(spec: string): unknown`` and ``local.`` had no
    members. The index must now carry a ``typeof import('./local/<rel>')``
    overload, and the referenced module (plus its transitive imports) must be
    mirrored so the import resolves.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))  # isolate the LSP workspace
    from services.lsp.pm_require_types import sync_pm_require_types, unregister_pm_require_buffer
    from services.lsp.servers._workspace import ensure_js_workspace

    home = create_folder("home")
    home2 = create_folder("home2")
    create_script(home2.id, "dep", language="javascript", content="export const v = 1;\n")
    create_script(
        home.id,
        "util",
        language="typescript",
        content="import { v } from '../home2/dep.js';\nexport function replaceStr(s: string) { return s + v; }\n",
    )

    ws = ensure_js_workspace()
    buffer_uri = "file:///buf.ts"
    try:
        sync_pm_require_types(
            "const local = pm.require('local:home/util.ts');\n",
            ws,
            buffer_uri=buffer_uri,
        )
        index = (ws / "pm_require_index.ts").read_text(encoding="utf-8")
        assert (
            'function require(spec: "local:home/util.ts"): '
            'typeof import("./local/home/util.ts");' in index
        )
        # The required module AND its transitive sibling import are mirrored,
        # so the generated ``typeof import`` resolves cleanly.
        assert (ws / "local" / "home" / "util.ts").is_file()
        assert (ws / "local" / "home2" / "dep.js").is_file()
    finally:
        unregister_pm_require_buffer(ws, buffer_uri)


def test_prepare_pm_require_bundle_union_scans_nested_npm() -> None:
    """``needs_net`` is true when a local module pulls in npm."""
    root = create_folder("lib")
    create_script(
        root.id,
        "nested",
        language="javascript",
        content='pm.require("npm:lodash@4.17.21");',
    )
    _union, needs_net, _mods = prepare_pm_require_bundle(
        'pm.require("local:lib/nested.js");',
        language="javascript",
    )
    assert needs_net is True


def test_local_imports_block_registers_cjs_specifier() -> None:
    """Bundle preamble maps ``local:…/helper.cjs`` to a static import."""
    auth = create_folder("auth")
    create_script(
        auth.id,
        "helper",
        language="javascript",
        module_format="commonjs",
        content="module.exports = { v: 1 };",
    )
    mods = resolve_required('pm.require("local:auth/helper.cjs");', "javascript")
    block = _pm_require_local_imports_block(mods)
    assert "./local/auth/helper.cjs" in block
    assert '"local:auth/helper.cjs"' in block


@pytest.mark.skipif(
    not _deno_runtime_available(),
    reason="Deno not available for JS runtime",
)
def test_pm_require_local_cjs_module_exports() -> None:
    """``pm.require('local:…/file.cjs')`` loads ``module.exports`` via Deno."""
    from services.scripting import ScriptInput
    from services.scripting.js_runtime import JSRuntime

    root = create_folder("lib")
    create_script(
        root.id,
        "helper",
        language="javascript",
        module_format="commonjs",
        content="module.exports = { v: 42 };",
    )
    script = """
pm.test("local cjs", function() {
    const { v } = pm.require("local:lib/helper.cjs");
    pm.expect(v).to.equal(42);
});
"""
    ctx: ScriptInput = {
        "request": {
            "method": "GET",
            "url": "https://example.com",
            "headers": {},
            "body": "",
        },
        "response": None,
        "variables": {},
        "environment_vars": {},
        "collection_vars": {},
        "info": {"requestName": "test"},
    }
    result = JSRuntime.execute(script, ctx)
    assert result["test_results"][0]["passed"] is True


def test_pm_require_inside_cjs_body_raises() -> None:
    """``.cjs`` locals are leaf modules — nested ``pm.require`` is rejected."""
    root = create_folder("lib")
    create_script(
        root.id,
        "leaf",
        language="javascript",
        module_format="commonjs",
        content="module.exports = {};",
    )
    create_script(
        root.id,
        "bad",
        language="javascript",
        module_format="commonjs",
        content='pm.require("local:lib/leaf.cjs");',
    )
    with pytest.raises(ValueError, match="not available inside .cjs"):
        resolve_required('pm.require("local:lib/bad.cjs");', "javascript")
