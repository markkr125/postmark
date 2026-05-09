"""Factory for Deno language server transport + client."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject

from services.lsp.client import LspClient
from services.lsp.servers._workspace import ensure_js_workspace
from services.lsp.transport import LspTransport
from services.scripting.runtime_settings import RuntimeSettings


def make_deno_client(parent: QObject | None = None) -> LspClient | None:
    """Spawn Deno LSP or return ``None`` if the binary is unavailable."""
    deno_path = RuntimeSettings.deno_path()
    if not deno_path or not Path(deno_path).is_file():
        return None
    workspace = ensure_js_workspace()
    transport = LspTransport([deno_path, "lsp"], cwd=str(workspace), parent=parent)
    root_uri = Path(workspace).as_uri()
    client = LspClient(transport, root_uri, parent=parent)
    # Deno LSP is disabled by default; without ``enable: true`` it returns no
    # diagnostics, no completions, no hover. ``lint: true`` adds the deno
    # linter pass on top of TypeScript diagnostics.
    client.set_init_options(
        {
            "enable": True,
            "lint": True,
            "unstable": False,
            # Point Deno explicitly at our workspace ``deno.json`` so
            # ``checkJs: true`` actually applies. Without this Deno
            # ignores the file and ``.js`` buffers go un-type-checked.
            "config": str(workspace / "deno.json"),
        }
    )
    return client
