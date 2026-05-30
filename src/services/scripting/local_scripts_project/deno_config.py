"""Workspace-level ambient ``pm`` types for the local scripts project."""

from __future__ import annotations

import re
from pathlib import Path

from services.lsp.servers._workspace import ensure_js_workspace

_AMBIENT_NAMESPACE_RE = re.compile(r"(?m)^declare namespace")


def _stubs_pm_path(workspace: Path) -> Path:
    return workspace / "stubs" / "pm.d.ts"


def ambient_pm_text_from_stub(stub_text: str) -> str:
    """Build ``ambient_pm.d.ts`` body from ``stubs/pm.d.ts`` (valid inside ``declare global``)."""
    inner = _AMBIENT_NAMESPACE_RE.sub("namespace", stub_text)
    return (
        "/** Ambient globals — generated from stubs/pm.d.ts for Deno LSP. */\n"
        "export {};\n"
        f"declare global {{\n{inner}\n}}\n"
    )


def ensure_ambient_pm(workspace: Path | None = None) -> Path:
    """Write ``ambient_pm.d.ts`` so ``pm`` is global without per-buffer preamble."""
    ws = workspace or ensure_js_workspace()
    src = _stubs_pm_path(ws)
    out = ws / "ambient_pm.d.ts"
    if not src.is_file():
        out.write_text(
            "export {};\ndeclare global { namespace pm { } }\n",
            encoding="utf-8",
        )
        return out
    out.write_text(ambient_pm_text_from_stub(src.read_text(encoding="utf-8")), encoding="utf-8")
    return out


def ensure_local_project_config() -> None:
    """Seed ambient types and sync the local mirror (call after DB init)."""
    ensure_ambient_pm()
    from services.scripting.local_scripts_project.mirror import sync_all

    sync_all()
