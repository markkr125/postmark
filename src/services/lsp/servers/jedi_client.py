"""Factory for jedi-language-server transport + client."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject

from services.lsp.client import LspClient
from services.lsp.servers._workspace import ensure_py_workspace
from services.lsp.transport import LspTransport


def make_jedi_client(parent: QObject | None = None) -> LspClient | None:
    """Spawn jedi-language-server or ``None`` if the package is missing."""
    try:
        import jedi_language_server  # noqa: F401
    except ImportError:
        return None
    workspace = ensure_py_workspace()
    stubs = workspace / "stubs"
    argv = [sys.executable, "-m", "jedi_language_server"]
    transport = LspTransport(argv, cwd=str(workspace), parent=parent)
    root_uri = Path(workspace).as_uri()
    client = LspClient(transport, root_uri, parent=parent)
    client.set_init_options({"workspace": {"extraPaths": [str(stubs)]}})
    return client
