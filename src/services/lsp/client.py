"""LSP client: initialize handshake and typed document helpers."""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from services.lsp.diagnostic_filters import should_publish_lsp_diagnostic
from services.lsp.transport import LspFuture, LspTransport


@dataclass
class Diagnostic:
    """Normalized diagnostic from ``textDocument/publishDiagnostics``."""

    line: int
    column: int
    end_line: int
    end_column: int
    severity: str
    message: str
    source: str
    related_local_path: str | None = None
    related_local_script_id: int | None = None
    related_line: int | None = None
    related_column: int | None = None


@dataclass
class CompletionItem:
    """Completion entry derived from LSP ``CompletionItem``."""

    label: str
    kind: str
    detail: str | None
    documentation: str | None
    insert_text: str | None


@dataclass
class SignatureInfo:
    """Signature help summary."""

    label: str
    parameters: list[str]
    active_parameter: int
    documentation: str | None


@dataclass
class Location:
    """Go-to-definition target."""

    uri: str
    line: int
    column: int


_KIND_MAP: dict[int, str] = {
    1: "text",
    2: "class",
    3: "function",
    4: "field",
    5: "variable",
    6: "class",
    9: "keyword",
    18: "module",
}


class ClientFuture:
    """Wraps a transport :class:`LspFuture` with a ``result`` mapper.

    Callbacks registered via :meth:`add_done_callback` are dispatched on
    *gui_target*'s owning thread (default: the LSP client itself, which
    lives on the GUI thread). Without this hop, callbacks would run on
    the reader thread and any QObject mutation would assert.
    """

    def __init__(
        self,
        inner: LspFuture,
        mapper: Callable[[Any], Any],
        gui_target: QObject | None = None,
    ) -> None:
        """Wrap *inner* and apply *mapper* to each ``result`` payload."""
        self._inner = inner
        self._mapper = mapper
        self._gui_target = gui_target

    @property
    def raw(self) -> LspFuture:
        """Underlying JSON-RPC future (for cancel identity)."""
        return self._inner

    def add_done_callback(self, cb: Callable[[ClientFuture], None]) -> None:
        """Chain *cb* on the GUI thread once the inner future resolves."""
        target = self._gui_target

        def _wrap(_: LspFuture) -> None:
            if target is None:
                cb(self)
                return
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, target, lambda: cb(self))

        self._inner.add_done_callback(_wrap)

    def result(self, timeout_s: float | None = None) -> Any:
        """Return mapped payload."""
        return self._mapper(self._inner.result(timeout_s))

    def cancel(self) -> None:
        """Forward cancellation."""
        self._inner.cancel()

    def cancelled(self) -> bool:
        """Forward cancellation state."""
        return self._inner.cancelled()


class LspClient(QObject):
    """High-level LSP session over a :class:`LspTransport`."""

    diagnostics_published = Signal(str, list)
    state_changed = Signal(str)
    _init_done = Signal(bool)  # internal: marshals init result to GUI thread

    def __init__(
        self,
        transport: LspTransport,
        root_uri: str,
        parent: QObject | None = None,
    ) -> None:
        """Wire *transport* notifications and idle exit handling."""
        super().__init__(parent)
        self._transport = transport
        self._root_uri = root_uri
        self._init_options: dict[str, Any] = {}
        self._open_docs: set[str] = set()
        self._exit_times: list[float] = []
        self._disabled = False
        self._ready = False
        self._init_timeout: QTimer | None = None
        self._transport.notification_received.connect(self._on_notification)
        self._transport.server_exited.connect(self._on_server_exited)
        # ``_init_done`` carries the success flag from the reader thread
        # (where future callbacks fire) back to the GUI thread (where
        # ``QTimer.stop`` and signal emission must happen).
        self._init_done.connect(self._finalize_initialize)

    @property
    def is_ready(self) -> bool:
        """True after the ``initialize`` handshake completes successfully."""
        return self._ready and not self._disabled

    def set_init_options(self, options: dict[str, Any]) -> None:
        """Merge options into ``initialize`` params (call before :meth:`start`)."""
        self._init_options.update(options)

    def start(self) -> None:
        """Spawn the server and dispatch ``initialize`` asynchronously.

        Returns immediately — the GUI thread is never blocked. State
        transitions land via the ``state_changed`` signal:

        * ``"starting"`` — emitted on entry.
        * ``"ready"``    — when the server replies to ``initialize``.
        * ``"disabled"`` — on timeout (5s) or initialize error.
        """
        if self._disabled or self._ready:
            return
        self._transport.start()
        self.state_changed.emit("starting")
        caps = _client_capabilities()
        params: dict[str, Any] = {
            "processId": os.getpid(),
            "rootUri": self._root_uri,
            "capabilities": caps,
            "initializationOptions": dict(self._init_options),
        }
        fut = self._transport.send_request("initialize", params)
        fut.add_done_callback(self._on_initialize_response)
        self._init_timeout = QTimer(self)
        self._init_timeout.setSingleShot(True)
        self._init_timeout.setInterval(5000)
        self._init_timeout.timeout.connect(lambda: self._on_initialize_timeout(fut))
        self._init_timeout.start()

    def _on_initialize_response(self, fut: Any) -> None:
        """Reader-thread callback: marshal the initialize outcome to GUI."""
        if self._disabled or self._ready:
            return
        try:
            fut.result(timeout_s=0.0)
            ok = True
        except Exception:
            ok = False
        self._init_done.emit(ok)

    def _finalize_initialize(self, ok: bool) -> None:
        """GUI-thread slot: stop the timeout, send ``initialized``, emit state."""
        if self._init_timeout is not None:
            self._init_timeout.stop()
            self._init_timeout = None
        if self._disabled or self._ready:
            return
        if not ok:
            self._disabled = True
            self.state_changed.emit("disabled")
            return
        self._transport.send_notification("initialized", {})
        self._ready = True
        self.state_changed.emit("ready")

    def _on_initialize_timeout(self, fut: Any) -> None:
        """Mark client disabled when initialize did not reply in time."""
        if self._ready or self._disabled:
            return
        with contextlib.suppress(Exception):
            fut.cancel()
        self._disabled = True
        self.state_changed.emit("disabled")

    def stop(self) -> None:
        """Shut down the session."""
        self._transport.send_notification("shutdown", {})
        self._transport.stop()

    def did_open(self, uri: str, language_id: str, version: int, text: str) -> None:
        """Notify ``textDocument/didOpen``."""
        self._open_docs.add(uri)
        self._transport.send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": language_id,
                    "version": version,
                    "text": text,
                }
            },
        )

    def did_change(self, uri: str, version: int, full_text: str) -> None:
        """Send full-document sync."""
        self._transport.send_notification(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": [{"text": full_text}],
            },
        )

    def did_close(self, uri: str) -> None:
        """Notify ``textDocument/didClose``."""
        self._open_docs.discard(uri)
        self._transport.send_notification(
            "textDocument/didClose",
            {"textDocument": {"uri": uri}},
        )

    def completion(self, uri: str, line: int, column: int) -> ClientFuture:
        """Request completions at LSP (0-based UTF-16) position."""
        fut = self._transport.send_request(
            "textDocument/completion",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
            },
        )

        def _map(raw: Any) -> list[CompletionItem]:
            return _parse_completion_list(raw)

        return ClientFuture(fut, _map, gui_target=self)

    def hover(self, uri: str, line: int, column: int) -> ClientFuture:
        """Request hover markdown/plain text."""
        fut = self._transport.send_request(
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
            },
        )

        def _map(raw: Any) -> str | None:
            return _parse_hover(raw)

        return ClientFuture(fut, _map, gui_target=self)

    def signature_help(self, uri: str, line: int, column: int) -> ClientFuture:
        """Request signature help."""
        fut = self._transport.send_request(
            "textDocument/signatureHelp",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
            },
        )

        def _map(raw: Any) -> SignatureInfo | None:
            return _parse_signature_help(raw)

        return ClientFuture(fut, _map, gui_target=self)

    def definition(self, uri: str, line: int, column: int) -> ClientFuture:
        """Request definition location(s)."""
        fut = self._transport.send_request(
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
            },
        )

        def _map(raw: Any) -> list[Location]:
            return _parse_locations(raw)

        return ClientFuture(fut, _map, gui_target=self)

    def formatting(self, uri: str, tab_size: int) -> ClientFuture:
        """Request full-document formatting."""
        fut = self._transport.send_request(
            "textDocument/formatting",
            {
                "textDocument": {"uri": uri},
                "options": {"tabSize": tab_size, "insertSpaces": True},
            },
        )

        def _map(raw: Any) -> list[dict[str, Any]] | None:
            return _parse_format_edits(raw)

        return ClientFuture(fut, _map, gui_target=self)

    def range_formatting(
        self,
        uri: str,
        tab_size: int,
        start_line: int,
        start_column: int,
        end_line: int,
        end_column: int,
    ) -> ClientFuture:
        """Request formatting for a document range."""
        fut = self._transport.send_request(
            "textDocument/rangeFormatting",
            {
                "textDocument": {"uri": uri},
                "range": {
                    "start": {"line": start_line, "character": start_column},
                    "end": {"line": end_line, "character": end_column},
                },
                "options": {"tabSize": tab_size, "insertSpaces": True},
            },
        )

        def _map(raw: Any) -> list[dict[str, Any]] | None:
            return _parse_format_edits(raw)

        return ClientFuture(fut, _map, gui_target=self)

    def _on_notification(self, method: str, params: dict[str, Any]) -> None:
        if method != "textDocument/publishDiagnostics":
            return
        uri = str(params.get("uri", ""))
        raw_list = params.get("diagnostics") or []
        out: list[Diagnostic] = []
        for d in raw_list:
            if not isinstance(d, dict):
                continue
            if not should_publish_lsp_diagnostic(d, document_uri=uri):
                continue
            rng = d.get("range") or {}
            start = rng.get("start") or {}
            end = rng.get("end") or {}
            sev = d.get("severity")
            sev_name = "hint"
            if sev == 1:
                sev_name = "error"
            elif sev == 2:
                sev_name = "warning"
            elif sev == 3:
                sev_name = "info"
            elif sev == 4:
                sev_name = "hint"
            msg = str(d.get("message", ""))
            src = str(d.get("source", "lsp"))
            out.append(
                Diagnostic(
                    line=int(start.get("line", 0)),
                    column=int(start.get("character", 0)),
                    end_line=int(end.get("line", 0)),
                    end_column=int(end.get("character", 0)),
                    severity=sev_name,
                    message=msg,
                    source=src,
                )
            )
        self.diagnostics_published.emit(uri, out)

    def _on_server_exited(self, code: int) -> None:
        """Track crash loops and disable after repeated exits within 60s."""
        _ = code
        now = time.monotonic()
        self._exit_times.append(now)
        self._exit_times = [t for t in self._exit_times if now - t <= 60.0]
        if len(self._exit_times) >= 3:
            self._disabled = True
            self.state_changed.emit("disabled")


def _client_capabilities() -> dict[str, Any]:
    return {
        "textDocument": {
            "publishDiagnostics": {},
            "completion": {"completionItem": {"snippetSupport": True}},
            "hover": {"contentFormat": ["markdown", "plaintext"]},
            "signatureHelp": {
                "signatureInformation": {"documentationFormat": ["markdown", "plaintext"]}
            },
            "definition": {},
            "formatting": {},
            "rangeFormatting": {},
            "synchronization": {"dynamicRegistration": False},
        },
        "workspace": {},
    }


def _parse_completion_list(raw: Any) -> list[CompletionItem]:
    if raw is None:
        return []
    items = raw
    if isinstance(raw, dict) and "items" in raw:
        items = raw["items"]
    if not isinstance(items, list):
        return []
    out: list[CompletionItem] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        label = str(it.get("label", ""))
        k = int(it.get("kind", 0))
        kind = _KIND_MAP.get(k, "variable")
        detail = it.get("detail")
        detail_s = str(detail) if detail is not None else None
        doc = it.get("documentation")
        doc_s: str | None
        if isinstance(doc, str):
            doc_s = doc
        elif isinstance(doc, dict) and "value" in doc:
            doc_s = str(doc.get("value"))
        else:
            doc_s = None
        insert = it.get("insertText") or it.get("textEdit", {}).get("newText")
        insert_s = str(insert) if isinstance(insert, str) else None
        out.append(
            CompletionItem(
                label=label,
                kind=kind,
                detail=detail_s,
                documentation=doc_s,
                insert_text=insert_s,
            )
        )
    return out


def _parse_hover(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    contents = raw.get("contents")
    if isinstance(contents, str):
        return contents
    if isinstance(contents, dict) and "value" in contents:
        return str(contents.get("value"))
    if isinstance(contents, list) and contents:
        parts: list[str] = []
        for block in contents:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "value" in block:
                parts.append(str(block.get("value")))
        return "\n".join(parts) if parts else None
    return None


def _parse_signature_help(raw: Any) -> SignatureInfo | None:
    if not isinstance(raw, dict):
        return None
    sigs = raw.get("signatures") or []
    if not sigs or not isinstance(sigs, list):
        return None
    sig0 = sigs[0]
    if not isinstance(sig0, dict):
        return None
    label = str(sig0.get("label", ""))
    params_raw = sig0.get("parameters") or []
    params: list[str] = []
    if isinstance(params_raw, list):
        for p in params_raw:
            if isinstance(p, dict):
                params.append(str(p.get("label", "")))
    active = int(raw.get("activeSignature", 0))
    active_param = int(raw.get("activeParameter", 0))
    doc = sig0.get("documentation")
    doc_s: str | None
    if isinstance(doc, str):
        doc_s = doc
    elif isinstance(doc, dict) and "value" in doc:
        doc_s = str(doc.get("value"))
    else:
        doc_s = None
    _ = active
    return SignatureInfo(
        label=label,
        parameters=params,
        active_parameter=active_param,
        documentation=doc_s,
    )


def _parse_locations(raw: Any) -> list[Location]:
    if raw is None:
        return []
    locs = raw if isinstance(raw, list) else [raw]
    out: list[Location] = []
    for loc in locs:
        if not isinstance(loc, dict):
            continue
        uri = str(loc.get("uri", ""))
        rng = loc.get("range") or {}
        start = rng.get("start") or {}
        out.append(
            Location(
                uri=uri,
                line=int(start.get("line", 0)),
                column=int(start.get("character", 0)),
            )
        )
    return out


def _parse_format_edits(raw: Any) -> list[dict[str, Any]] | None:
    """Return LSP ``TextEdit`` dicts from a formatting response, or ``None``."""
    if not isinstance(raw, list) or not raw:
        return None
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and "range" in item:
            out.append(item)
    return out or None


def _parse_formatting(raw: Any) -> str | None:
    """Legacy helper: first edit ``newText`` only (tests / simple callers)."""
    edits = _parse_format_edits(raw)
    if not edits:
        return None
    return str(edits[0].get("newText", ""))
