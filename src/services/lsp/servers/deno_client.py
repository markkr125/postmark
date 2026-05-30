"""Factory for Deno language server transport + client."""

from __future__ import annotations

import subprocess

from PySide6.QtCore import QObject

from services.lsp.client import LspClient
from services.lsp.servers.spawn import LspSpawnSpec, prepare_js_spawn, spawn_lsp_process
from services.lsp.transport import LspTransport


def client_from_spawn(
    spec: LspSpawnSpec,
    proc: subprocess.Popen[bytes],
    parent: QObject | None = None,
) -> LspClient:
    """Wire a Deno :class:`LspClient` around an already-spawned process."""
    transport = LspTransport(spec.argv, cwd=spec.cwd, parent=parent, _proc=proc)
    client = LspClient(transport, spec.root_uri, parent=parent)
    client.set_init_options(dict(spec.init_options))
    return client


def make_deno_client(parent: QObject | None = None) -> LspClient | None:
    """Spawn Deno LSP synchronously (tests); production uses :mod:`spawn` workers."""
    spec = prepare_js_spawn()
    if spec is None:
        return None
    proc = spawn_lsp_process(spec)
    if proc is None:
        return None
    return client_from_spawn(spec, proc, parent=parent)
