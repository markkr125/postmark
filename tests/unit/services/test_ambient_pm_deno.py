"""Live Deno checks for workspace ambient ``pm`` types."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from esprima_test_util import deno_available  # type: ignore[import-not-found]
from services.lsp.servers._workspace import _DENO_CONFIG
from services.scripting.local_scripts_project.deno_config import (
    ambient_pm_text_from_stub,
    ensure_ambient_pm,
)
from services.scripting.runtime_settings import RuntimeSettings


def test_ambient_pm_text_has_no_nested_declare_namespace() -> None:
    """``declare namespace`` must not appear inside ``declare global`` (TS1038)."""
    repo_stub = Path(__file__).resolve().parents[3] / "data" / "lsp" / "stubs" / "pm.d.ts"
    text = ambient_pm_text_from_stub(repo_stub.read_text(encoding="utf-8"))
    global_block = text.split("declare global {", 1)[1]
    assert "declare namespace" not in global_block


@pytest.mark.skipif(not deno_available(), reason="Deno not available")
def test_deno_check_ambient_pm_file(tmp_path: Path) -> None:
    """Generated ``ambient_pm.d.ts`` type-checks under Deno."""
    repo_stub = Path(__file__).resolve().parents[3] / "data" / "lsp" / "stubs" / "pm.d.ts"
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    shutil.copy2(repo_stub, stubs / "pm.d.ts")
    ensure_ambient_pm(tmp_path)
    (tmp_path / "deno.json").write_text(_DENO_CONFIG, encoding="utf-8")
    (tmp_path / "pm_require_index.ts").write_text("export {};\n", encoding="utf-8")
    deno = RuntimeSettings.deno_path() or ""
    assert deno
    proc = subprocess.run(
        [deno, "check", str(tmp_path / "ambient_pm.d.ts")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


@pytest.mark.skipif(not deno_available(), reason="Deno not available")
def test_deno_check_local_script_uses_pm_without_reference(tmp_path: Path) -> None:
    """A bare ``local/*.js`` file resolves ``pm`` via ``compilerOptions.types`` only."""
    repo_stub = Path(__file__).resolve().parents[3] / "data" / "lsp" / "stubs" / "pm.d.ts"
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    shutil.copy2(repo_stub, stubs / "pm.d.ts")
    ensure_ambient_pm(tmp_path)
    (tmp_path / "deno.json").write_text(_DENO_CONFIG, encoding="utf-8")
    (tmp_path / "pm_require_index.ts").write_text("export {};\n", encoding="utf-8")
    local = tmp_path / "local"
    local.mkdir()
    (local / "entry.js").write_text(
        "pm.test('ok', () => { pm.expect(1).to.eql(1); });\n",
        encoding="utf-8",
    )
    deno = RuntimeSettings.deno_path() or ""
    assert deno
    proc = subprocess.run(
        [deno, "check", str(local / "entry.js")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
