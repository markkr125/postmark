"""Per-user LSP workspace directories (seeded from packaged ``data/lsp``)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def _repo_data_lsp() -> Path:
    return Path(__file__).resolve().parents[4] / "data" / "lsp"


def user_lsp_root() -> Path:
    """Return ``~/.local/share/postmark/lsp-workspace`` (created)."""
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    root = base / "postmark" / "lsp-workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root


_DENO_CONFIG = """{
  "compilerOptions": {
    "checkJs": true,
    "allowJs": true,
    "noImplicitAny": false,
    "strict": false
  }
}
"""


def ensure_js_workspace() -> Path:
    """Seed JS workspace with the ``pm.d.ts`` stub and a ``deno.json``.

    The ``deno.json`` enables ``checkJs`` so Deno LSP type-checks
    ``.js`` buffers (default behaviour only checks ``.ts``).
    """
    ws = user_lsp_root() / "js"
    ws.mkdir(parents=True, exist_ok=True)
    # Drop any tsconfig left from earlier installs — its ``lib`` setting
    # would override Deno's defaults and hide ``console``.
    legacy_ts = ws / "tsconfig.json"
    if legacy_ts.is_file():
        legacy_ts.unlink()
    (ws / "deno.json").write_text(_DENO_CONFIG, encoding="utf-8")
    stubs = _repo_data_lsp() / "stubs"
    dst_stubs = ws / "stubs"
    dst_stubs.mkdir(exist_ok=True)
    for name in ("pm.d.ts",):
        src = stubs / name
        if src.is_file():
            shutil.copy2(src, dst_stubs / name)
    return ws


def ensure_py_workspace() -> Path:
    """Seed Python workspace with ``pm.pyi``."""
    ws = user_lsp_root() / "py"
    ws.mkdir(parents=True, exist_ok=True)
    stubs = _repo_data_lsp() / "stubs"
    dst = ws / "stubs"
    dst.mkdir(exist_ok=True)
    src = stubs / "pm.pyi"
    if src.is_file():
        shutil.copy2(src, dst / "pm.pyi")
    return ws
