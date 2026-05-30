"""Bridge :class:`CodeEditorWidget` to a shared :class:`services.lsp.client.LspClient`."""

from __future__ import annotations

import contextlib
import hashlib
import time
import uuid
import warnings
from pathlib import Path
from typing import Any, ClassVar
from weakref import WeakSet

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QPlainTextEdit
from shiboken6 import Shiboken

from services.lsp.client import ClientFuture, CompletionItem, Diagnostic, LspClient
from services.lsp.diagnostic_filters import should_suppress_unused_local_require_diagnostic
from services.scripting.local_dependency_diagnostics import (
    LocalDependencyDiagnosticBundle,
    collect_direct_local_dependency_diagnostics,
    iter_pm_require_local_sites,
)
from services.lsp.local_script_lsp_prep import LocalScriptLspPrepResult
from services.lsp.pm_require_types import (
    pm_require_index_path,
    sync_pm_require_closure_buffers,
    sync_pm_require_types,
    unregister_pm_require_buffer,
)
from services.lsp.js_lsp_preamble import (
    editor_position_to_lsp,
    lsp_line_to_editor_line,
    shift_diagnostics_to_editor,
    wrap_script_for_lsp,
)
from services.lsp.qt_lsp_offsets import lsp_to_qpos
from services.lsp.server_registry import LspRegistry
from services.lsp.servers._workspace import ensure_js_workspace, ensure_py_workspace
from services.scripting.runtime_settings import RuntimeSettings
from ui.widgets.code_editor.gutter import SyntaxError_, normalize_validation_severity

# Ignore empty ``publishDiagnostics`` briefly after edits / buffer republish.
_DIAG_CLEAR_IDLE_S = 2.0


def _disconnect_connection(signal: object, connection: object | None) -> None:
    """Disconnect *connection* from *signal* without Qt RuntimeWarning noise."""
    if connection is None:
        return
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=".*[Ff]ailed to disconnect.*",
            category=RuntimeWarning,
        )
        with contextlib.suppress(RuntimeError, TypeError):
            signal.disconnect(connection)  # type: ignore[attr-defined]


def _script_fingerprint(text: str) -> str:
    """Stable hash of editor buffer text for stale diagnostic suppression."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class EditorLspAdapter(QObject):
    """Per-editor LSP document sync and diagnostics."""

    _INSTANCES: ClassVar[WeakSet[EditorLspAdapter]] = WeakSet()

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
        self._sync_timer.setInterval(RuntimeSettings.lsp_did_change_debounce_ms())
        self._sync_timer.timeout.connect(self._flush_did_change)
        self._npm_types_timer = QTimer(self)
        self._npm_types_timer.setSingleShot(True)
        self._npm_types_timer.setInterval(RuntimeSettings.lsp_pm_require_debounce_ms())
        self._npm_types_timer.timeout.connect(self._flush_pm_require_types)
        self._contents_slot_connected = False
        self._opened = False
        self._index_uri: str | None = None
        self._index_version = 0
        self._index_opened = False
        self._js_workspace: Path | None = None
        self._cached_problems: list[Diagnostic] = []
        self._cached_validation: list[SyntaxError_] = []
        self._diag_fingerprint: str = ""
        self._last_edit_mono: float = 0.0
        self._suspend_clear_until: float = 0.0
        self._diag_clear_timer = QTimer(self)
        self._diag_clear_timer.setSingleShot(True)
        self._diag_clear_timer.setInterval(RuntimeSettings.lsp_diag_clear_debounce_ms())
        self._diag_clear_timer.timeout.connect(self._apply_deferred_diagnostic_clear)
        self._dep_timer = QTimer(self)
        self._dep_timer.setSingleShot(True)
        self._dep_timer.setInterval(RuntimeSettings.lsp_dep_diag_debounce_ms())
        self._dep_timer.timeout.connect(self._flush_dependency_diagnostics)
        self._cached_host_problems: list[Diagnostic] = []
        self._cached_host_mapped: list[SyntaxError_] = []
        self._cached_dep_bundle = LocalDependencyDiagnosticBundle([], [], [])
        self._cached_closure_problems: list[Diagnostic] = []
        self._closure_problems_by_uri: dict[str, list[Diagnostic]] = {}
        self._closure_diagnostic_uris: set[str] = set()
        self._mirrored_local_uri = False
        self._state_changed_connection: object | None = None
        self._diagnostics_connection: object | None = None
        self._contents_connection: object | None = None
        self._sync_suspended = False
        self._sync_dirty = False
        self._prep_skip_sync = False

    def suspend_sync(self) -> None:
        """Stop debounced LSP/diagnostic work while a debug session is active."""
        self._sync_suspended = True
        self._sync_timer.stop()
        self._npm_types_timer.stop()
        self._dep_timer.stop()
        self._diag_clear_timer.stop()

    def resume_sync(self) -> None:
        """Resume LSP sync and flush one ``didChange`` if the buffer changed while suspended."""
        if not self._sync_suspended:
            return
        self._sync_suspended = False
        dirty = self._sync_dirty
        self._sync_dirty = False
        if dirty and self._opened:
            self._flush_did_change()
            self._schedule_pm_require_types_sync()
            if self._language_id in ("javascript", "typescript", "python"):
                self._dep_timer.start()

    def attach(
        self,
        language: str,
        *,
        prep: LocalScriptLspPrepResult | None = None,
    ) -> bool:
        """Bind the editor to the registry client for *language*.

        When *prep* succeeded, mirror/index/closure work is skipped on attach.

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
        workspace = ensure_py_workspace() if lang == "python" else ensure_js_workspace()
        self._js_workspace = None if lang == "python" else workspace
        self._mirrored_local_uri = False
        self._prep_skip_sync = prep is not None and prep.ok
        local_script_id = getattr(self._editor, "_local_script_id", None)
        if local_script_id is not None and lang in ("javascript", "typescript"):
            from services.scripting.local_scripts_project.mirror import (
                mirror_path_for_script_id,
                sync_script,
            )

            if prep is not None and prep.ok and prep.target_uri:
                self._uri = prep.target_uri
                self._mirrored_local_uri = True
                self._closure_diagnostic_uris = set(prep.closure_diagnostic_uris)
            else:
                sync_script(local_script_id)
                mirror_path = mirror_path_for_script_id(local_script_id)
                if mirror_path is not None:
                    self._uri = mirror_path.as_uri()
                    self._mirrored_local_uri = True
                else:
                    virtual_path = Path(workspace) / f"_buffer_{uuid.uuid4().hex}.{ext}"
                    self._uri = virtual_path.as_uri()
        else:
            virtual_path = Path(workspace) / f"_buffer_{uuid.uuid4().hex}.{ext}"
            self._uri = virtual_path.as_uri()
        self._language_id = lang
        self._client = client
        self._version = 0
        self._opened = False
        self._index_uri = None
        self._index_version = 0
        self._index_opened = False
        if self._js_workspace is not None:
            self._index_uri = pm_require_index_path(self._js_workspace).as_uri()
        self._state_changed_connection = client.state_changed.connect(self._on_client_state)
        self._diagnostics_connection = client.diagnostics_published.connect(self._on_diagnostics)
        self._contents_connection = self._editor.document().contentsChanged.connect(
            self._on_contents_changed
        )
        self._contents_slot_connected = True
        if getattr(client, "is_ready", False):
            self._send_initial_open()
        EditorLspAdapter._INSTANCES.add(self)
        return True

    @classmethod
    def live_js_buffer_keys(cls) -> set[tuple[str, str]]:
        """Return ``(workspace_key, buffer_uri)`` for every attached JS/TS adapter."""
        live: set[tuple[str, str]] = set()
        for adapter in cls._INSTANCES:
            if adapter._uri and adapter._js_workspace is not None:
                live.add((str(adapter._js_workspace.resolve()), adapter._uri))
        return live

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
        if getattr(self._editor, "_local_script_id", None) is not None:
            return False
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
        self._js_workspace = None if new_lang == "python" else workspace
        virtual_path = Path(workspace) / f"_buffer_{uuid.uuid4().hex}.{ext}"
        self._uri = virtual_path.as_uri()
        self._language_id = new_lang
        self._version = 0
        self._opened = False
        self._index_uri = None
        self._index_version = 0
        self._index_opened = False
        if self._js_workspace is not None:
            self._index_uri = pm_require_index_path(self._js_workspace).as_uri()
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
        if self._js_workspace is not None and not self._prep_skip_sync:
            sync_pm_require_types(
                text,
                self._js_workspace,
                buffer_uri=self._uri or "",
                after_cache=self._on_pm_require_cache_finished,
            )
            self._ensure_pm_require_index_open()
        elif self._js_workspace is not None and self._prep_skip_sync:
            self._ensure_pm_require_index_open()
        from services.scripting.local_scripts_project.lsp_uri_registry import acquire_uri

        should_open = acquire_uri(self._uri) if self._mirrored_local_uri else True
        if should_open:
            try:
                self._client.did_open(
                    self._uri,
                    self._language_id,
                    self._version,
                    self._lsp_document_text(text),
                )
            except BrokenPipeError:
                if self._mirrored_local_uri:
                    from services.scripting.local_scripts_project.lsp_uri_registry import (
                        release_uri,
                    )

                    release_uri(self._uri)
                return
        self._opened = True
        if getattr(self._editor, "_local_script_id", None) is not None and not self._prep_skip_sync:
            self._refresh_local_project_closure()
        if self._js_workspace is not None and not self._index_opened:
            self._ensure_pm_require_index_open()

    def _ensure_pm_require_index_open(self) -> None:
        """Open ``pm_require_index.ts`` in Deno LSP (npm/jsr ``pm.require`` overloads)."""
        if (
            self._client is None
            or self._index_uri is None
            or self._js_workspace is None
            or self._index_opened
        ):
            return
        index_path = pm_require_index_path(self._js_workspace)
        if not index_path.is_file():
            return
        try:
            self._client.did_open(
                self._index_uri,
                "typescript",
                self._index_version,
                index_path.read_text(encoding="utf-8"),
            )
        except BrokenPipeError:
            return
        self._index_opened = True

    def _notify_pm_require_index_change(self) -> None:
        if (
            self._client is None
            or self._index_uri is None
            or self._js_workspace is None
            or not self._index_opened
        ):
            return
        index_path = pm_require_index_path(self._js_workspace)
        if not index_path.is_file():
            return
        self._index_version += 1
        with contextlib.suppress(BrokenPipeError):
            self._client.did_change(
                self._index_uri,
                self._index_version,
                index_path.read_text(encoding="utf-8"),
            )

    def detach(self) -> None:
        """Close the virtual document and disconnect."""
        EditorLspAdapter._INSTANCES.discard(self)
        self._sync_timer.stop()
        self._npm_types_timer.stop()
        self._diag_clear_timer.stop()
        self._dep_timer.stop()
        self._cached_problems = []
        self._cached_validation = []
        self._cached_host_problems = []
        self._cached_host_mapped = []
        self._cached_dep_bundle = LocalDependencyDiagnosticBundle([], [], [])
        self._cached_closure_problems = []
        self._closure_problems_by_uri = {}
        self._closure_diagnostic_uris = set()
        if self._js_workspace is not None and self._uri:
            unregister_pm_require_buffer(self._js_workspace, self._uri)
        if self._contents_connection is not None:
            _disconnect_connection(
                self._editor.document().contentsChanged,
                self._contents_connection,
            )
            self._contents_connection = None
            self._contents_slot_connected = False
        if self._client is not None:
            _disconnect_connection(self._client.state_changed, self._state_changed_connection)
            self._state_changed_connection = None
            _disconnect_connection(
                self._client.diagnostics_published,
                self._diagnostics_connection,
            )
            self._diagnostics_connection = None
            if self._index_uri is not None and self._index_opened:
                with contextlib.suppress(Exception):
                    self._client.did_close(self._index_uri)
            if self._uri is not None and self._opened:
                from services.scripting.local_scripts_project.lsp_uri_registry import (
                    release_uri,
                )

                if not self._mirrored_local_uri or release_uri(self._uri):
                    with contextlib.suppress(Exception):
                        self._client.did_close(self._uri)
        self._client = None
        self._uri = None
        self._language_id = None
        self._opened = False
        self._index_uri = None
        self._index_version = 0
        self._index_opened = False
        self._js_workspace = None
        self._mirrored_local_uri = False
        self._prep_skip_sync = False
        editor = self._editor
        if hasattr(editor, "notify_lsp_diagnostics"):
            editor.notify_lsp_diagnostics([])

    def _on_contents_changed(self) -> None:
        self._last_edit_mono = time.monotonic()
        if self._sync_suspended:
            self._sync_dirty = True
            return
        self._sync_timer.start()
        self._schedule_pm_require_types_sync()
        if self._language_id in ("javascript", "typescript", "python"):
            self._dep_timer.start()

    def refresh_dependency_diagnostics(self) -> None:
        """Re-scan direct ``local:`` dependencies and refresh Problems + gutter."""
        self._flush_dependency_diagnostics()

    def _mark_suspend_diagnostic_clear(self, seconds: float = _DIAG_CLEAR_IDLE_S) -> None:
        """Ignore empty ``publishDiagnostics`` until *seconds* elapse (republish/npm cache)."""
        self._suspend_clear_until = max(
            self._suspend_clear_until,
            time.monotonic() + seconds,
        )

    def _schedule_pm_require_types_sync(self) -> None:
        if self._js_workspace is None or self._language_id not in ("javascript", "typescript"):
            return
        self._npm_types_timer.start()

    def _flush_pm_require_types(self) -> None:
        if self._js_workspace is None:
            return
        changed = sync_pm_require_types(
            self._editor.toPlainText(),
            self._js_workspace,
            buffer_uri=self._uri or "",
            after_cache=self._on_pm_require_cache_finished,
        )
        if changed and not self._index_opened:
            self._ensure_pm_require_index_open()
        if not self._opened:
            return
        if changed:
            if self._index_opened:
                self._notify_pm_require_index_change()
            self._republish_script_buffer()

    def _on_pm_require_cache_finished(self) -> None:
        """After background ``deno cache``, refresh the index and re-check the script."""
        QTimer.singleShot(0, self._apply_after_pm_require_cache)

    def _apply_after_pm_require_cache(self) -> None:
        """Main-thread hook: LSP picks up types once ``deno cache`` finishes."""
        if self._js_workspace is None or not self._opened:
            return
        self._notify_pm_require_index_change()
        self._republish_script_buffer()

    def _republish_script_buffer(self) -> None:
        """Nudge Deno to re-check the script after ``pm_require_index.ts`` changes."""
        if self._client is None or self._uri is None or not self._opened:
            return
        try:
            self._version += 1
            self._mark_suspend_diagnostic_clear()
            self._client.did_change(
                self._uri,
                self._version,
                self._lsp_document_text(self._editor.toPlainText()),
            )
        except BrokenPipeError:
            return

    def _lsp_document_text(self, user_text: str) -> str:
        """Text sent to LSP (preamble + user script for Deno JS/TS buffers)."""
        if self._js_workspace is not None:
            return wrap_script_for_lsp(user_text, workspace=self._js_workspace)
        return user_text

    def _flush_pending_did_change(self) -> None:
        """Send any debounced ``didChange`` now so position queries hit the live buffer.

        Completion/hover/definition are requested on the keystroke, but the
        ``didChange`` carrying that edit is debounced — without this, Deno
        answers against stale text and member completion returns globals.
        """
        if self._sync_timer.isActive():
            self._sync_timer.stop()
            self._flush_did_change()

    def _flush_did_change(self) -> None:
        if self._client is None or self._uri is None:
            return
        if not self._opened:
            # Server not yet ready; the next ``state_changed("ready")``
            # will open with the current snapshot.
            return
        self._version += 1
        self._mark_suspend_diagnostic_clear()
        self._client.did_change(
            self._uri,
            self._version,
            self._lsp_document_text(self._editor.toPlainText()),
        )

    def _apply_deferred_diagnostic_clear(self) -> None:
        """Clear Problems/gutter once editing has been idle and the buffer is stable."""
        if time.monotonic() < self._suspend_clear_until:
            self._diag_clear_timer.start()
            return
        if time.monotonic() - self._last_edit_mono < _DIAG_CLEAR_IDLE_S:
            self._diag_clear_timer.start()
            return
        script_text = self._editor.toPlainText()
        if script_text and _script_fingerprint(script_text) != self._diag_fingerprint:
            return
        if not self._cached_problems and not self._dependency_problem_rows():
            return
        self._cached_host_problems = []
        self._cached_host_mapped = []
        self._diag_fingerprint = ""
        self._republish_merged()

    def _restore_cached_diagnostics(self) -> None:
        """Re-apply the last known Problems + gutter markers."""
        if not self._cached_problems and not self._dependency_problem_rows():
            return
        self._republish_merged()

    def _dependency_problem_rows(self) -> list[Diagnostic]:
        """Problems-tab rows from direct local dependencies and closure files."""
        dep = self._cached_dep_bundle
        return [*dep.dependency_rows, *dep.resolution_rows, *self._cached_closure_problems]

    def _flush_dependency_diagnostics(self) -> None:
        """Load direct ``local:`` lint results and merge with cached host diagnostics."""
        if not Shiboken.isValid(self._editor):
            return
        if self._language_id not in ("javascript", "typescript", "python"):
            return
        script_text = self._editor.toPlainText()
        self._cached_dep_bundle = collect_direct_local_dependency_diagnostics(
            script_text,
            self._language_id or "javascript",
        )
        self._refresh_local_project_closure()
        self._republish_merged()

    def _refresh_local_project_closure(self) -> None:
        """Mirror import closure, register npm types, track URIs for diag aggregation."""
        sid = getattr(self._editor, "_local_script_id", None)
        if sid is None or self._js_workspace is None or self._uri is None:
            self._closure_diagnostic_uris = set()
            return
        from services.scripting.local_scripts_project.import_graph import resolve_union_closure
        from services.scripting.local_scripts_project.mirror import (
            mirror_path_for_rel,
            rel_path_for_script_id,
            sync_closure,
        )

        rel = rel_path_for_script_id(sid)
        if rel is None:
            self._closure_diagnostic_uris = set()
            return
        lang = self._language_id or "javascript"
        try:
            mods = resolve_union_closure(rel, lang, entry_source=self._editor.toPlainText())
        except ValueError:
            self._closure_diagnostic_uris = set()
            return
        sync_closure(mods)
        buffers: list[tuple[str, str]] = []
        uris: set[str] = set()
        for mod in mods.values():
            path = mirror_path_for_rel(mod.rel_path)
            uri = path.as_uri()
            uris.add(uri)
            buffers.append((uri, mod.source))
        self._closure_diagnostic_uris = {u for u in uris if u != self._uri}
        sync_pm_require_closure_buffers(
            self._js_workspace,
            buffers,
            after_cache=self._on_pm_require_cache_finished,
        )

    def _merge_closure_diagnostics(self, uri: str, diags: list) -> None:
        """Aggregate Problems rows for unopened files in the import closure."""
        from services.scripting.local_scripts_project.mirror import local_mirror_root

        from urllib.parse import unquote, urlparse

        rel_label = uri
        parsed = urlparse(uri)
        if parsed.scheme == "file":
            disk = Path(unquote(parsed.path))
            with contextlib.suppress(ValueError):
                rel_label = disk.relative_to(local_mirror_root()).as_posix()
        shifted = shift_diagnostics_to_editor(
            [x for x in diags if isinstance(x, Diagnostic)],
            language_id=self._language_id,
            workspace=self._js_workspace,
        )
        prefix = f"[{rel_label}] " if rel_label else ""
        self._closure_problems_by_uri[uri] = [
            Diagnostic(
                line=d.line,
                column=d.column,
                end_line=d.end_line,
                end_column=d.end_column,
                severity=d.severity,
                message=prefix + d.message,
                source=d.source,
            )
            for d in shifted
        ]
        self._cached_closure_problems = [
            row for rows in self._closure_problems_by_uri.values() for row in rows
        ]
        self._republish_merged()

    def _anchors_to_syntax_errors(
        self,
        anchors: list,
    ) -> list[SyntaxError_]:
        from services.scripting.local_dependency_diagnostics import RequireAnchorDiagnostic

        out: list[SyntaxError_] = []
        for anchor in anchors:
            if not isinstance(anchor, RequireAnchorDiagnostic):
                continue
            out.append(
                SyntaxError_(
                    line=anchor.line,
                    column=anchor.column,
                    message=anchor.message,
                    severity=normalize_validation_severity(anchor.severity),
                )
            )
        return out

    def _republish_merged(self) -> None:
        """Merge host LSP/ESM diagnostics with direct local-dependency rows."""
        problems_tab = [
            *self._cached_host_problems,
            *self._dependency_problem_rows(),
        ]
        mapped = [
            *self._cached_host_mapped,
            *self._anchors_to_syntax_errors(self._cached_dep_bundle.require_anchors),
        ]
        self._cached_problems = problems_tab
        self._cached_validation = mapped
        self._publish_diagnostics_to_editor(problems_tab, mapped)

    def _publish_diagnostics_to_editor(
        self,
        problems_tab: list[Diagnostic],
        mapped: list[SyntaxError_],
    ) -> None:
        """Push Problems tab + gutter markers for the current diagnostic snapshot."""
        cast_editor = self._editor
        if hasattr(cast_editor, "notify_lsp_diagnostics"):
            cast_editor.notify_lsp_diagnostics(problems_tab)
        if hasattr(cast_editor, "apply_validation_errors"):
            cast_editor.apply_validation_errors(mapped)

    def _on_diagnostics(self, uri: str, diags: list) -> None:
        if uri != self._uri:
            if uri in self._closure_diagnostic_uris:
                self._merge_closure_diagnostics(uri, diags)
            return
        from services.scripting.engine import ScriptLinter
        from services.scripting.es_module_rules import es_module_to_lsp_diagnostics

        cast_editor = self._editor
        script_text = cast_editor.toPlainText()
        lang = self._language_id or "javascript"
        require_sites = iter_pm_require_local_sites(script_text)
        shifted = shift_diagnostics_to_editor(
            [x for x in diags if isinstance(x, Diagnostic)],
            language_id=self._language_id,
            workspace=self._js_workspace,
        )
        lsp_only = [
            d
            for d in shifted
            if not should_suppress_unused_local_require_diagnostic(d, require_sites)
        ]
        host_problems = list(lsp_only) + es_module_to_lsp_diagnostics(script_text, lang)
        host_mapped: list[SyntaxError_] = []
        for d in lsp_only:
            line_1 = max(1, d.line + 1)
            col_1 = max(1, d.column + 1)
            sev = normalize_validation_severity(d.severity)
            host_mapped.append(
                SyntaxError_(
                    line=line_1,
                    column=col_1,
                    message=f"[{d.source}] {d.message}",
                    severity=sev,
                )
            )
        mod_fmt = getattr(self._editor, "_script_module_format", "esm")
        if lang in ("javascript", "typescript") and script_text.strip():
            seen = {(e.line, e.column, e.message) for e in host_mapped}
            legacy_items = (
                ScriptLinter.check_commonjs_local_script(script_text)
                if mod_fmt == "commonjs"
                else ScriptLinter.check_es_module(script_text, lang)
            )
            for item in legacy_items:
                key = (item["line"], item["column"], item["message"])
                if key in seen:
                    continue
                seen.add(key)
                host_mapped.append(
                    SyntaxError_(
                        line=item["line"],
                        column=item["column"],
                        message=item["message"],
                        severity=item.get("severity", "error"),
                    )
                )

        self._cached_host_problems = host_problems
        self._cached_host_mapped = host_mapped

        if host_problems:
            self._diag_clear_timer.stop()
            self._diag_fingerprint = _script_fingerprint(script_text)
        elif not self._dependency_problem_rows():
            if not self._cached_problems:
                self._republish_merged()
                return

            if time.monotonic() < self._suspend_clear_until:
                self._restore_cached_diagnostics()
                return
            if _script_fingerprint(script_text) != self._diag_fingerprint:
                self._restore_cached_diagnostics()
                return
            if time.monotonic() - self._last_edit_mono < _DIAG_CLEAR_IDLE_S:
                self._restore_cached_diagnostics()
                self._diag_clear_timer.start()
                return

            self._diag_clear_timer.start()
            return

        self._flush_dependency_diagnostics()

    def request_completion(self) -> ClientFuture | None:
        """Return a completion future, or ``None`` if LSP is not active."""
        if self._sync_suspended or self._client is None or self._uri is None or not self.is_ready:
            return None
        self._flush_pending_did_change()
        cur = self._editor.textCursor()
        line, col = editor_position_to_lsp(
            self._editor.document(),
            cur.position(),
            language_id=self._language_id,
        )
        return self._client.completion(self._uri, line, col)

    def request_hover(self) -> ClientFuture | None:
        """Return a hover future for the cursor position, or ``None``."""
        if self._sync_suspended or self._client is None or self._uri is None or not self.is_ready:
            return None
        self._flush_pending_did_change()
        cur = self._editor.textCursor()
        line, col = editor_position_to_lsp(
            self._editor.document(),
            cur.position(),
            language_id=self._language_id,
        )
        return self._client.hover(self._uri, line, col)

    def request_signature(self) -> ClientFuture | None:
        """Return signature-help future for the cursor position, or ``None``."""
        if self._sync_suspended or self._client is None or self._uri is None or not self.is_ready:
            return None
        self._flush_pending_did_change()
        cur = self._editor.textCursor()
        line, col = editor_position_to_lsp(
            self._editor.document(),
            cur.position(),
            language_id=self._language_id,
        )
        return self._client.signature_help(self._uri, line, col)

    def request_definition(self) -> ClientFuture | None:
        """Return go-to-definition future for the cursor position, or ``None``."""
        if self._sync_suspended or self._client is None or self._uri is None or not self.is_ready:
            return None
        self._flush_pending_did_change()
        cur = self._editor.textCursor()
        line, col = editor_position_to_lsp(
            self._editor.document(),
            cur.position(),
            language_id=self._language_id,
        )
        return self._client.definition(self._uri, line, col)

    def lsp_location_to_editor_position(self, lsp_line: int, lsp_column: int) -> int | None:
        """Map an LSP position on this buffer back to a QTextDocument offset."""
        editor_line = lsp_line_to_editor_line(lsp_line, language_id=self._language_id)
        if editor_line is None:
            return None
        return lsp_to_qpos(self._editor.document(), editor_line, lsp_column)

    def request_format(self) -> ClientFuture | None:
        """Return full-document format future, or ``None``."""
        if self._client is None or self._uri is None or not self.is_ready:
            return None
        return self._client.formatting(self._uri, self._format_tab_size())

    def request_format_range(self) -> ClientFuture | None:
        """Return range-format future for the current selection, or ``None``."""
        if self._client is None or self._uri is None or not self.is_ready:
            return None
        cur = self._editor.textCursor()
        if not cur.hasSelection():
            return None
        doc = self._editor.document()
        sl, sc = editor_position_to_lsp(doc, cur.selectionStart(), language_id=self._language_id)
        el, ec = editor_position_to_lsp(doc, cur.selectionEnd(), language_id=self._language_id)
        return self._client.range_formatting(self._uri, self._format_tab_size(), sl, sc, el, ec)

    def _format_tab_size(self) -> int:
        """Indent width used for LSP format requests."""
        tab = 2
        raw = getattr(self._editor, "_detected_indent", None)
        if isinstance(raw, int) and raw > 0:
            tab = raw
        return tab


def merge_completion_items(
    schema_items: list[Any],
    lsp_items: list[CompletionItem],
) -> list[Any]:
    """Append LSP items after schema ones, de-duplicating by label."""
    from ui.widgets.code_editor.completion.engine import CompletionItem as EngineItem

    labels = {getattr(i, "label", str(i)) for i in schema_items}
    out: list[Any] = list(schema_items)
    valid_kinds = frozenset({"property", "method", "object", "variable", "keyword"})
    for it in lsp_items:
        if it.label in labels:
            continue
        labels.add(it.label)
        kind = it.kind if it.kind in valid_kinds else "property"
        doc = (it.documentation or "") if it.documentation else ""
        out.append(
            EngineItem(
                label=it.label,
                kind=kind,
                type_str=it.detail or "",
                doc=doc,
                signature="",
                insert_text=it.insert_text or it.label,
            )
        )
    return out
