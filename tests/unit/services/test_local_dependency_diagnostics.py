"""Unit tests for :mod:`services.scripting.local_dependency_diagnostics`."""

from __future__ import annotations

from database.database import get_session
from database.models.local_scripts.local_script_repository import create_folder, create_script
from services.scripting.local_dependency_diagnostics import (
    collect_direct_local_dependency_diagnostics,
    iter_pm_require_local_sites,
)
from services.scripting.local_script_modules import build_module_index


def test_iter_pm_require_local_sites_captures_binding() -> None:
    """Require sites record line and optional binding name."""
    source = "const local = pm.require('local:auth/helper.js');\n"
    sites = iter_pm_require_local_sites(source)
    assert len(sites) == 1
    assert sites[0].rel_path == "auth/helper.js"
    assert sites[0].binding_name == "local"
    assert sites[0].line == 1


def test_direct_commonjs_dependency_produces_anchor() -> None:
    """CJS ``module.exports`` in a direct dependency yields Problems row + require anchor."""
    folder = create_folder("home")
    create_script(
        folder.id,
        "testjs.js",
        language="javascript",
        content="module.exports = { x: 1 };\n",
    )
    with get_session() as session:
        index = build_module_index(session)
    rel = "home/testjs.js"
    assert rel in index

    host = "const local = pm.require('local:home/testjs.js');\n"
    bundle = collect_direct_local_dependency_diagnostics(host, "javascript")
    assert bundle.dependency_rows
    assert any("module.exports" in row.message for row in bundle.dependency_rows)
    assert bundle.require_anchors
    assert bundle.require_anchors[0].line == 1
    assert "Dependency" in bundle.require_anchors[0].message


def test_missing_local_path_anchors_require_line() -> None:
    """Unknown ``local:`` path produces a require-line anchor."""
    host = "pm.require('local:missing/path.js');\n"
    bundle = collect_direct_local_dependency_diagnostics(host, "javascript")
    assert bundle.resolution_rows
    assert bundle.require_anchors
    assert bundle.require_anchors[0].line == 1
    assert "not found" in bundle.require_anchors[0].message.lower()
