"""Singleton registry for shared :class:`LspClient` instances."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import ClassVar

from PySide6.QtCore import QObject, Signal

from services.lsp.client import LspClient
from services.lsp.servers._workspace import ensure_js_workspace, ensure_py_workspace
from services.lsp.servers.deno_client import make_deno_client
from services.lsp.servers.jedi_client import make_jedi_client


class LspRegistry(QObject):
    """Owns one LSP client per language family (JS/TS share Deno)."""

    _instance: ClassVar[LspRegistry | None] = None

    language_unavailable = Signal(str, str)  # lang key, short message

    def __init__(self, parent: QObject | None = None) -> None:
        """Create registry maps (clients are started lazily)."""
        super().__init__(parent)
        self._clients: dict[str, LspClient] = {}
        self._disabled: set[str] = set()
        self._toast_sent: set[str] = set()

    @classmethod
    def instance(cls) -> LspRegistry:
        """Return the process-wide registry singleton."""
        if cls._instance is None:
            cls._instance = LspRegistry()
        return cls._instance

    def for_language(self, lang: str) -> LspClient | None:
        """Return a started client for *lang*, or ``None`` if unavailable."""
        key = self._normalize(lang)
        if key is None:
            return None
        if key in ("javascript", "typescript"):
            return self._get_or_create("js", make_deno_client)
        if key == "python":
            return self._get_or_create("python", make_jedi_client)
        return None

    def warm(self) -> None:
        """Spawn both shared clients eagerly so subsequent attaches are instant.

        Idempotent — already-spawned clients are not restarted. Errors
        are swallowed; failure surfaces normally on the first
        :meth:`for_language` call instead.
        """
        with contextlib.suppress(Exception):
            self._get_or_create("js", make_deno_client)
        with contextlib.suppress(Exception):
            self._get_or_create("python", make_jedi_client)

    def _normalize(self, lang: str) -> str | None:
        key = lang.lower().strip()
        if key in ("javascript", "typescript", "python"):
            return key
        return None

    def _get_or_create(
        self,
        bucket: str,
        factory: Callable[[QObject | None], LspClient | None],
    ) -> LspClient | None:
        if bucket in self._disabled:
            return None
        if bucket in self._clients:
            return self._clients[bucket]
        client = factory(self)
        if client is None:
            if bucket not in self._toast_sent:
                self._toast_sent.add(bucket)
                self.language_unavailable.emit(bucket, "Language server unavailable")
            self._disabled.add(bucket)
            return None
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
        return client

    @staticmethod
    def _open_pm_stub(bucket: str, client: LspClient) -> None:
        """Make the ``pm`` stub part of the language server's program graph.

        Without an explicit ``did_open`` for the stub, Deno LSP and jedi
        treat the global ``pm`` namespace as undeclared even though the
        file lives in the workspace.
        """
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
        """Stop all clients (``aboutToQuit``)."""
        for c in list(self._clients.values()):
            with contextlib.suppress(Exception):
                c.stop()
        self._clients.clear()


def reset_registry_for_tests() -> None:
    """Clear singleton (tests only)."""
    LspRegistry._instance = None
