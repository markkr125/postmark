"""Factory for jedi-language-server transport + client."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QObject

from services.lsp.client import LspClient
from services.lsp.servers._workspace import ensure_py_workspace
from services.lsp.transport import LspTransport


def _resolve_jedi_argv() -> list[str] | None:
    """Return argv that actually launches jedi-language-server, or ``None``.

    The package ships no ``__main__.py``, so ``python -m jedi_language_server``
    silently fails (server never reaches ``ready`` → empty Problems tab).
    Prefer the installed console-script first, then fall back to invoking the
    ``cli()`` entry point through ``python -c`` so virtualenvs without a
    ``jedi-language-server`` shim still work.
    """
    bin_path = shutil.which("jedi-language-server")
    if bin_path:
        return [bin_path]
    py_bin = Path(sys.executable).resolve().parent / "jedi-language-server"
    if py_bin.is_file():
        return [str(py_bin)]
    return [sys.executable, "-c", "from jedi_language_server.cli import cli; cli()"]


def make_jedi_client(parent: QObject | None = None) -> LspClient | None:
    """Spawn jedi-language-server or ``None`` if the package is missing."""
    try:
        import jedi_language_server  # noqa: F401
    except ImportError:
        return None
    argv = _resolve_jedi_argv()
    if argv is None:
        return None
    workspace = ensure_py_workspace()
    stubs = workspace / "stubs"
    transport = LspTransport(argv, cwd=str(workspace), parent=parent)
    root_uri = Path(workspace).as_uri()
    client = LspClient(transport, root_uri, parent=parent)
    client.set_init_options({"workspace": {"extraPaths": [str(stubs)]}})
    return client
