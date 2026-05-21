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
