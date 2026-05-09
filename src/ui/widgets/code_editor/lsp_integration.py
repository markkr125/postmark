"""Bridge :class:`CodeEditorWidget` to a shared :class:`services.lsp.client.LspClient`."""

from __future__ import annotations

import contextlib
import uuid
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QPlainTextEdit

from services.lsp.client import ClientFuture, CompletionItem, Diagnostic, LspClient
from services.lsp.qt_lsp_offsets import qpos_to_lsp
from services.lsp.server_registry import LspRegistry
from services.lsp.servers._workspace import ensure_js_workspace, ensure_py_workspace
from services.scripting.runtime_settings import RuntimeSettings
from ui.widgets.code_editor.gutter import SyntaxError_, normalize_validation_severity


class EditorLspAdapter(QObject):
    """Per-editor LSP document sync and diagnostics."""

    def __init__(self, editor: QPlainTextEdit, parent: QObject | None = None) -> None:
        """Attach timers and state for syncing *editor* with an :class:`LspClient`."""
        super().__init__(parent)
        self._editor = editor
        self._client: LspClient | None = None
        self._uri: str | None = None
        self._version = 0
        self._language_id: str | None = None
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(150)
        self._sync_timer.timeout.connect(self._flush_did_change)
        self._contents_slot_connected = False
        self._opened = False

    def attach(self, language: str) -> bool:
        """Bind the editor to the registry client for *language*.

        Does not block on the LSP handshake. When the client is still
        ``starting`` the document is opened lazily via the
        ``state_changed`` signal once the server emits ``ready``.
        """
        if not RuntimeSettings.lsp_enabled():
            return False
        lang = language.lower().strip()
        lookup = "javascript" if lang == "typescript" else lang
        client = LspRegistry.instance().for_language(lookup)
        if client is None:
            return False
        ext = {"javascript": "js", "typescript": "ts", "python": "py"}.get(lang, "txt")
        # Deno LSP only type-checks ``file://`` URIs inside its workspace,
        # so virtual buffers must live under the seeded workspace dir.
        workspace = ensure_py_workspace() if lang == "python" else ensure_js_workspace()
        virtual_path = Path(workspace) / f"_buffer_{uuid.uuid4().hex}.{ext}"
        self._uri = virtual_path.as_uri()
        self._language_id = lang
        self._client = client
        self._version = 0
        self._opened = False
        client.state_changed.connect(self._on_client_state)
        client.diagnostics_published.connect(self._on_diagnostics)
        self._editor.document().contentsChanged.connect(self._on_contents_changed)
        self._contents_slot_connected = True
        if getattr(client, "is_ready", False):
            self._send_initial_open()
        return True

    @property
    def is_ready(self) -> bool:
        """Return True only after the server completed the initialize handshake."""
        return self._client is not None and bool(getattr(self._client, "is_ready", False))

    @property
    def language(self) -> str | None:
        """Current attached language id (``javascript`` / ``typescript`` / ``python``)."""
        return self._language_id

    def can_swap_to(self, language: str) -> bool:
        """True when *language* maps to the same shared LSP client as the current one."""
        if self._client is None:
            return False
        target = language.lower().strip()
        current = (self._language_id or "").lower().strip()
        js_family = {"javascript", "typescript"}
        return (current in js_family and target in js_family) or (
            current == "python" and target == "python"
        )

    def swap_language(self, language: str) -> bool:
        """Re-open the buffer under *language* on the same LSP client.

        Avoids the full detach + recreate cost when only the language id
        changes within a shared family (JS ↔ TS). The signal connections
        on the shared client are reused.
        """
        if self._client is None or not self.can_swap_to(language):
            return False
        new_lang = language.lower().strip()
        if new_lang == self._language_id:
            return True
        # Close the previous buffer on the server (best-effort).
        if self._uri is not None and self._opened:
            with contextlib.suppress(Exception):
                self._client.did_close(self._uri)
        editor = self._editor
        if hasattr(editor, "notify_lsp_diagnostics"):
            editor.notify_lsp_diagnostics([])
        ext = {"javascript": "js", "typescript": "ts", "python": "py"}.get(new_lang, "txt")
        workspace = ensure_py_workspace() if new_lang == "python" else ensure_js_workspace()
        virtual_path = Path(workspace) / f"_buffer_{uuid.uuid4().hex}.{ext}"
        self._uri = virtual_path.as_uri()
        self._language_id = new_lang
        self._version = 0
        self._opened = False
        if self.is_ready:
            self._send_initial_open()
        return True

    def _on_client_state(self, state: str) -> None:
        """Send the deferred ``did_open`` once the server transitions to ready."""
        if state == "ready" and not self._opened:
            self._send_initial_open()
        if state == "ready":
            editor = self._editor
            if hasattr(editor, "_on_lsp_ready"):
                editor._on_lsp_ready()

    def _send_initial_open(self) -> None:
        if self._client is None or self._uri is None or self._language_id is None:
            return
        if self._opened:
            return
        text = self._editor.toPlainText()
        try:
            self._client.did_open(self._uri, self._language_id, self._version, text)
        except BrokenPipeError:
            return
        self._opened = True

    def detach(self) -> None:
        """Close the virtual document and disconnect."""
        self._sync_timer.stop()
        if self._contents_slot_connected:
            with contextlib.suppress(Exception):
                self._editor.document().contentsChanged.disconnect(self._on_contents_changed)
            self._contents_slot_connected = False
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.state_changed.disconnect(self._on_client_state)
            with contextlib.suppress(Exception):
                self._client.diagnostics_published.disconnect(self._on_diagnostics)
            if self._uri is not None and self._opened:
                with contextlib.suppress(Exception):
                    self._client.did_close(self._uri)
        self._client = None
        self._uri = None
        self._language_id = None
        self._opened = False
        editor = self._editor
        if hasattr(editor, "notify_lsp_diagnostics"):
            editor.notify_lsp_diagnostics([])

    def _on_contents_changed(self) -> None:
        self._sync_timer.start()

    def _flush_did_change(self) -> None:
        if self._client is None or self._uri is None:
            return
        if not self._opened:
            # Server not yet ready; the next ``state_changed("ready")``
            # will open with the current snapshot.
            return
        self._version += 1
        self._client.did_change(self._uri, self._version, self._editor.toPlainText())

    def _on_diagnostics(self, uri: str, diags: list) -> None:
        if uri != self._uri:
            return
        lsp_only = [d for d in diags if isinstance(d, Diagnostic)]
        cast_editor = self._editor
        if hasattr(cast_editor, "notify_lsp_diagnostics"):
            cast_editor.notify_lsp_diagnostics(list(lsp_only))
        mapped: list[SyntaxError_] = []
        for d in diags:
            if not isinstance(d, Diagnostic):
                continue  # defensive; client emits dataclass instances
            line_1 = max(1, d.line + 1)
            col_1 = max(1, d.column + 1)
            sev = normalize_validation_severity(d.severity)
            mapped.append(
                SyntaxError_(
                    line=line_1,
                    column=col_1,
                    message=f"[{d.source}] {d.message}",
                    severity=sev,
                )
            )
        if hasattr(cast_editor, "apply_validation_errors"):
            cast_editor.apply_validation_errors(mapped)

    def request_completion(self) -> ClientFuture | None:
        """Return a completion future, or ``None`` if LSP is not active."""
        if self._client is None or self._uri is None or not self.is_ready:
            return None
        cur = self._editor.textCursor()
        line, col = qpos_to_lsp(self._editor.document(), cur.position())
        return self._client.completion(self._uri, line, col)

    def request_hover(self) -> ClientFuture | None:
        """Return a hover future for the cursor position, or ``None``."""
        if self._client is None or self._uri is None or not self.is_ready:
            return None
        cur = self._editor.textCursor()
        line, col = qpos_to_lsp(self._editor.document(), cur.position())
        return self._client.hover(self._uri, line, col)

    def request_signature(self) -> ClientFuture | None:
        """Return signature-help future for the cursor position, or ``None``."""
        if self._client is None or self._uri is None or not self.is_ready:
            return None
        cur = self._editor.textCursor()
        line, col = qpos_to_lsp(self._editor.document(), cur.position())
        return self._client.signature_help(self._uri, line, col)

    def request_definition(self) -> ClientFuture | None:
        """Return go-to-definition future for the cursor position, or ``None``."""
        if self._client is None or self._uri is None or not self.is_ready:
            return None
        cur = self._editor.textCursor()
        line, col = qpos_to_lsp(self._editor.document(), cur.position())
        return self._client.definition(self._uri, line, col)

    def request_format(self) -> ClientFuture | None:
        """Return full-document format future, or ``None``."""
        if self._client is None or self._uri is None or not self.is_ready:
            return None
        tab = 2
        raw = getattr(self._editor, "_detected_indent", None)
        if isinstance(raw, int) and raw > 0:
            tab = raw
        return self._client.formatting(self._uri, tab)


def merge_completion_items(
    schema_items: list[Any],
    lsp_items: list[CompletionItem],
) -> list[Any]:
    """Append LSP items after schema ones, de-duplicating by label."""
    labels = {getattr(i, "label", str(i)) for i in schema_items}
    out = list(schema_items)
    for it in lsp_items:
        if it.label in labels:
            continue
        labels.add(it.label)
        out.append(it)
    return out
