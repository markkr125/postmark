"""Singleton registry for shared :class:`LspClient` instances."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from typing import Any, ClassVar

from PySide6.QtCore import QObject, Signal

from services.lsp.client import LspClient
from services.lsp.servers._workspace import ensure_js_workspace, ensure_py_workspace
from services.lsp.servers.deno_client import client_from_spawn as deno_client_from_spawn
from services.lsp.servers.jedi_client import client_from_spawn as jedi_client_from_spawn
from services.lsp.servers.spawn import LspSpawnSpec, LspSpawnWorker, language_to_bucket


class LspRegistry(QObject):
    """Owns one LSP client per language family (JS/TS share Deno)."""

    _instance: ClassVar[LspRegistry | None] = None

    language_unavailable = Signal(str, str)  # bucket, short message
    bucket_ready = Signal(str)  # bucket key once client is installed and starting

    def __init__(self, parent: QObject | None = None) -> None:
        """Create registry maps (clients are started lazily)."""
        super().__init__(parent)
        self._clients: dict[str, LspClient] = {}
        self._disabled: set[str] = set()
        self._toast_sent: set[str] = set()
        self._warming: set[str] = set()
        self._warm_lock = threading.Lock()
        self._spawn_workers: list[LspSpawnWorker] = []
        self._ready_callbacks: dict[str, list[Callable[[], None]]] = {}

    @classmethod
    def instance(cls) -> LspRegistry:
        """Return the process-wide registry singleton."""
        if cls._instance is None:
            cls._instance = LspRegistry()
        return cls._instance

    @staticmethod
    def bucket_for_language(lang: str) -> str | None:
        """Return registry bucket for *lang*, or ``None`` if unsupported."""
        return language_to_bucket(lang)

    def for_language(self, lang: str) -> LspClient | None:
        """Return an existing client for *lang*, starting spawn if needed."""
        bucket = self.bucket_for_language(lang)
        if bucket is None:
            return None
        self.warm_async(bucket)
        return self._clients.get(bucket)

    def warm(self, bucket: str | None = None) -> None:
        """Schedule background spawn for *bucket* (``None`` → both buckets).

        Idempotent. Does not block the GUI thread.
        """
        self.warm_async(bucket)

    def warm_async(self, bucket: str | None = None) -> None:
        """Spawn language-server subprocess(es) on a worker thread."""
        if bucket is None:
            self._start_warm_async("js")
            self._start_warm_async("python")
            return
        self._start_warm_async(bucket)

    def when_bucket_ready(self, bucket: str, callback: Callable[[], None]) -> None:
        """Invoke *callback* on the GUI thread once *bucket* has a client."""
        if bucket in self._clients:
            callback()
            return
        self._ready_callbacks.setdefault(bucket, []).append(callback)
        self.warm_async(bucket)

    def _start_warm_async(self, bucket: str) -> None:
        with self._warm_lock:
            if bucket in self._clients or bucket in self._disabled or bucket in self._warming:
                return
            self._warming.add(bucket)
        worker = LspSpawnWorker(bucket, parent=self)
        worker.finished_with.connect(self._on_spawn_finished)
        self._spawn_workers.append(worker)

        def _drop_worker() -> None:
            with contextlib.suppress(ValueError):
                self._spawn_workers.remove(worker)

        worker.finished.connect(_drop_worker)
        worker.start()

    def _on_spawn_finished(
        self,
        bucket: str,
        proc: Any,
        spec: Any,
    ) -> None:
        """Install a client after the worker thread returns a subprocess handle."""
        with self._warm_lock:
            self._warming.discard(bucket)
        if bucket in self._clients or bucket in self._disabled:
            if proc is not None:
                with contextlib.suppress(Exception):
                    proc.terminate()
            return
        if proc is None or not isinstance(spec, LspSpawnSpec):
            if bucket not in self._toast_sent:
                self._toast_sent.add(bucket)
                self.language_unavailable.emit(bucket, "Language server unavailable")
            self._disabled.add(bucket)
            self._flush_ready_callbacks(bucket)
            return
        client = self._client_from_spec(spec, proc)
        if client is None:
            if bucket not in self._toast_sent:
                self._toast_sent.add(bucket)
                self.language_unavailable.emit(bucket, "Language server unavailable")
            self._disabled.add(bucket)
            self._flush_ready_callbacks(bucket)
            return
        self._install_client(bucket, client)
        self.bucket_ready.emit(bucket)
        self._flush_ready_callbacks(bucket)

    def _client_from_spec(
        self,
        spec: LspSpawnSpec,
        proc: Any,
    ) -> LspClient | None:
        try:
            if spec.bucket == "js":
                return deno_client_from_spawn(spec, proc, parent=self)
            if spec.bucket == "python":
                return jedi_client_from_spawn(spec, proc, parent=self)
        except Exception:
            with contextlib.suppress(Exception):
                proc.terminate()
            return None
        return None

    def _install_client(self, bucket: str, client: LspClient) -> None:
        self._clients[bucket] = client

        def _on_state(state: str) -> None:
            if state == "disabled":
                self._disabled.add(bucket)
                if bucket not in self._toast_sent:
                    self._toast_sent.add(bucket)
                    self.language_unavailable.emit(bucket, "Language server stopped")
            elif state == "ready":
                self._open_pm_stub(bucket, client)

        client.state_changed.connect(_on_state)
        client.start()

    def _flush_ready_callbacks(self, bucket: str) -> None:
        callbacks = self._ready_callbacks.pop(bucket, [])
        for cb in callbacks:
            with contextlib.suppress(Exception):
                cb()

    @staticmethod
    def _open_pm_stub(bucket: str, client: LspClient) -> None:
        """Make the ``pm`` stub part of the language server's program graph."""
        if bucket == "js":
            ws = ensure_js_workspace()
            stub = ws / "stubs" / "pm.d.ts"
            language_id = "typescript"
        else:
            ws = ensure_py_workspace()
            stub = ws / "stubs" / "pm.pyi"
            language_id = "python"
        if not stub.is_file():
            return
        text = stub.read_text(encoding="utf-8")
        with contextlib.suppress(Exception):
            client.did_open(stub.as_uri(), language_id, 1, text)

    def shutdown(self) -> None:
        """Stop all clients (``aboutToQuit``), including spawned-but-unused servers."""
        for worker in list(self._spawn_workers):
            with contextlib.suppress(Exception):
                worker.wait(500)
        self._spawn_workers.clear()
        with self._warm_lock:
            self._warming.clear()
        for c in list(self._clients.values()):
            with contextlib.suppress(Exception):
                c.stop()
        self._clients.clear()
        self._ready_callbacks.clear()


def reset_registry_for_tests() -> None:
    """Clear singleton (tests only)."""
    inst = LspRegistry._instance
    if inst is not None:
        inst.shutdown()
    LspRegistry._instance = None
