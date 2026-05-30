"""Off-GUI subprocess spawn helpers for language-server buckets."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from services.lsp.servers._workspace import ensure_js_workspace, ensure_py_workspace
from services.scripting.runtime_settings import RuntimeSettings

logger = logging.getLogger(__name__)

_DENO_INIT_OPTIONS: dict[str, Any] = {
    "enable": True,
    "lint": True,
    "unstable": False,
}


@dataclass(frozen=True)
class LspSpawnSpec:
    """Everything needed to wire an :class:`~services.lsp.client.LspClient` after spawn."""

    bucket: str
    argv: list[str]
    cwd: str
    root_uri: str
    init_options: dict[str, Any]


def prepare_js_spawn() -> LspSpawnSpec | None:
    """Resolve Deno LSP argv and workspace (safe on a worker thread)."""
    deno_path = RuntimeSettings.deno_path()
    if not deno_path or not Path(deno_path).is_file():
        return None
    workspace = ensure_js_workspace()
    config = str(workspace / "deno.json")
    return LspSpawnSpec(
        bucket="js",
        argv=[deno_path, "lsp"],
        cwd=str(workspace),
        root_uri=workspace.as_uri(),
        init_options={**_DENO_INIT_OPTIONS, "config": config},
    )


def prepare_python_spawn() -> LspSpawnSpec | None:
    """Resolve jedi-language-server argv and workspace (safe on a worker thread)."""
    try:
        import jedi_language_server  # noqa: F401
    except ImportError:
        return None
    argv = _resolve_jedi_argv()
    if argv is None:
        return None
    workspace = ensure_py_workspace()
    stubs = workspace / "stubs"
    return LspSpawnSpec(
        bucket="python",
        argv=argv,
        cwd=str(workspace),
        root_uri=workspace.as_uri(),
        init_options={"workspace": {"extraPaths": [str(stubs)]}},
    )


def prepare_spawn(bucket: str) -> LspSpawnSpec | None:
    """Return spawn metadata for *bucket* (``js`` or ``python``)."""
    if bucket == "js":
        return prepare_js_spawn()
    if bucket == "python":
        return prepare_python_spawn()
    return None


def spawn_lsp_process(spec: LspSpawnSpec) -> subprocess.Popen[bytes] | None:
    """Start the language-server subprocess (call from a worker thread).

    ``close_fds=True`` avoids inheriting Qt's file descriptors on Linux.
    The returned :class:`~subprocess.Popen` is safe to use from the GUI thread.
    """
    try:
        return subprocess.Popen(
            spec.argv,
            cwd=spec.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            text=False,
            close_fds=True,
        )
    except OSError as exc:
        logger.debug("LSP spawn failed for %s: %s", spec.bucket, exc)
        return None


def language_to_bucket(lang: str) -> str | None:
    """Map a script language id to registry bucket (``js`` or ``python``)."""
    key = lang.lower().strip()
    if key in ("javascript", "typescript"):
        return "js"
    if key == "python":
        return "python"
    return None


def _resolve_jedi_argv() -> list[str] | None:
    bin_path = shutil.which("jedi-language-server")
    if bin_path:
        return [bin_path]
    py_bin = Path(sys.executable).resolve().parent / "jedi-language-server"
    if py_bin.is_file():
        return [str(py_bin)]
    return [sys.executable, "-c", "from jedi_language_server.cli import cli; cli()"]


class LspSpawnWorker(QThread):
    """Spawn one LSP bucket on a background thread."""

    finished_with = Signal(str, object, object)  # bucket, proc|None, spec|None

    def __init__(self, bucket: str, parent: Any | None = None) -> None:
        """Remember which registry bucket this worker spawns."""
        super().__init__(parent)
        self._bucket = bucket

    def run(self) -> None:
        """Prepare workspace metadata and ``Popen`` the server off the GUI thread."""
        spec = prepare_spawn(self._bucket)
        if spec is None:
            self.finished_with.emit(self._bucket, None, None)
            return
        proc = spawn_lsp_process(spec)
        self.finished_with.emit(self._bucket, proc, spec)


__all__ = [
    "LspSpawnSpec",
    "LspSpawnWorker",
    "language_to_bucket",
    "prepare_spawn",
    "spawn_lsp_process",
]
