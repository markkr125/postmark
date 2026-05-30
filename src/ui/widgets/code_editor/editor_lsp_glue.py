"""Language-server attachment and response helpers for :class:`~editor_widget.CodeEditorWidget`."""

from __future__ import annotations

import html as _html
import logging
import weakref
from typing import TYPE_CHECKING, Any

from shiboken6 import Shiboken

if TYPE_CHECKING:
    from ui.widgets.code_editor.editor_widget import CodeEditorWidget

logger = logging.getLogger(__name__)

_HOST_SCRIPT_EDITORS: weakref.WeakSet[CodeEditorWidget] = weakref.WeakSet()
_DEBUG_SUSPENDED_EDITORS: weakref.WeakSet[CodeEditorWidget] = weakref.WeakSet()


def set_debug_session_active(editor: CodeEditorWidget, active: bool) -> None:
    """Pause LSP sync and other debounced editor work during an active debug session."""
    if getattr(editor, "_debug_session_active", False) == active:
        return
    editor._debug_session_active = active
    if active:
        _DEBUG_SUSPENDED_EDITORS.add(editor)
        editor._validate_timer.stop()
        editor._fold_timer.stop()
        editor._format_on_idle_timer.stop()
        adapter = getattr(editor, "_lsp_adapter", None)
        if adapter is not None and hasattr(adapter, "suspend_sync"):
            adapter.suspend_sync()
    else:
        _DEBUG_SUSPENDED_EDITORS.discard(editor)
        adapter = getattr(editor, "_lsp_adapter", None)
        if adapter is not None and hasattr(adapter, "resume_sync"):
            adapter.resume_sync()
        if not should_skip_script_validation(editor):
            editor._validate_timer.start()


def resume_all_debug_suspended_editors() -> None:
    """Resume every editor still marked suspended (safe when host pin is already cleared)."""
    for editor in list(_DEBUG_SUSPENDED_EDITORS):
        set_debug_session_active(editor, False)


def should_skip_script_validation(editor: CodeEditorWidget) -> bool:
    """Skip ``ScriptLinter`` only after the LSP handshake completes."""
    adapter = getattr(editor, "_lsp_adapter", None)
    return adapter is not None and bool(getattr(adapter, "is_ready", False))


def on_lsp_ready(editor: CodeEditorWidget) -> None:
    """No-op hook retained for adapter compatibility.

    Legacy errors are cleared the first time the LSP publishes
    diagnostics (an empty list on a clean file replaces any stale
    legacy markers via :meth:`apply_validation_errors`). Eagerly
    clearing here would race with diagnostics that arrived ahead of
    the ``state_changed("ready")`` signal.
    """


def set_lsp_attach_deferred(editor: CodeEditorWidget, deferred: bool) -> None:
    """Defer LSP attach until :meth:`materialize_lsp_attachment` (hidden script panes)."""
    editor._lsp_attach_deferred = deferred
    if deferred:
        return
    materialize_lsp_attachment(editor)


def materialize_lsp_attachment(editor: CodeEditorWidget) -> None:
    """Attach LSP when a deferred editor becomes visible."""
    editor._lsp_attach_deferred = False
    sync_script_lsp_attachment(editor)


def sync_script_lsp_attachment(editor: CodeEditorWidget) -> None:
    """Start or stop LSP based on language mode, read-only state, and deferral."""
    if editor._read_only or editor.isReadOnly():
        detach_lsp(editor)
        return
    lang = editor._language
    if lang in ("javascript", "typescript", "python"):
        if getattr(editor, "_lsp_attach_deferred", False):
            return
        _try_attach_lsp(editor, lang)
    else:
        detach_lsp(editor)
        editor._validate_timer.start()


def _try_attach_lsp(editor: CodeEditorWidget, language: str) -> None:
    """Attach when the shared client exists; otherwise wait for background spawn."""
    from services.scripting.runtime_settings import RuntimeSettings
    from services.lsp.server_registry import LspRegistry

    if not RuntimeSettings.lsp_enabled():
        editor._validate_timer.start()
        return
    bucket = LspRegistry.bucket_for_language(language)
    if bucket is None:
        editor._validate_timer.start()
        return
    registry = LspRegistry.instance()
    registry.warm_async(bucket)
    if registry.for_language(language) is not None:
        attach_lsp(editor, language)
        return
    editor_ref = weakref.ref(editor)

    def _retry() -> None:
        ed = editor_ref()
        if ed is None or not Shiboken.isValid(ed):
            return
        if getattr(ed, "_lsp_attach_deferred", False):
            return
        client = registry.for_language(language)
        if client is not None:
            attach_lsp(ed, language)
        else:
            ed._validate_timer.start()

    registry.when_bucket_ready(bucket, _retry)


def attach_lsp(
    editor: CodeEditorWidget,
    language: str,
    *,
    prep: Any | None = None,
) -> None:
    """Attach to the shared language server for *language* (script modes only).

    Reuses the existing adapter when the new language maps to the
    same LSP client family (JS ↔ TS share the Deno server). Avoids
    the detach + signal-reconnect round-trip that previously caused
    a noticeable lag and dropped diagnostics on language toggle.
    """
    from services.lsp.local_script_lsp_prep import LocalScriptLspPrepResult
    from services.scripting.runtime_settings import RuntimeSettings
    from ui.widgets.code_editor.lsp_integration import EditorLspAdapter

    prep_result = prep if isinstance(prep, LocalScriptLspPrepResult) else None
    prev = getattr(editor, "_lsp_adapter", None)
    if getattr(editor, "_local_script_id", None) is not None:
        if prev is not None:
            detach_lsp(editor)
        adapter = EditorLspAdapter(editor)
        editor._lsp_adapter = adapter
        if adapter.attach(language, prep=prep_result):
            editor._validate_timer.stop()
        else:
            editor._lsp_adapter = None
            editor._validate_timer.start()
        return
    if prev is not None and prev.can_swap_to(language) and prev.swap_language(language):
        return
    if prev is not None:
        prev.detach()
    editor._lsp_adapter = None
    if not RuntimeSettings.lsp_enabled():
        editor._validate_timer.start()
        return
    adapter = EditorLspAdapter(editor, parent=editor)
    if adapter.attach(language):
        editor._lsp_adapter = adapter
    else:
        adapter.detach()
        editor._validate_timer.start()


def finalize_local_script_lsp_attach(
    editor: CodeEditorWidget,
    language: str,
    prep: Any,
    *,
    attach_token: int,
) -> None:
    """Complete local-script LSP attach on the GUI thread after background prep."""
    from services.lsp.local_script_lsp_prep import LocalScriptLspPrepResult

    if attach_token != editor.lsp_attach_token():
        return
    if not isinstance(prep, LocalScriptLspPrepResult):
        return
    editor.set_lsp_attach_deferred(False)
    if prep.ok:
        attach_lsp(editor, language, prep=prep)
        return
    if prep.error_message:
        logger.debug(
            "local script LSP prep failed, falling back to sync attach: %s", prep.error_message
        )
    attach_lsp(editor, language)


def detach_lsp(editor: CodeEditorWidget) -> None:
    """Disconnect from the language server and restore legacy validation."""
    editor.next_lsp_attach_token()
    prev = getattr(editor, "_lsp_adapter", None)
    if prev is not None:
        prev.detach()
    editor._lsp_adapter = None


def register_host_script_editor(editor: CodeEditorWidget) -> None:
    """Track request/folder script editors for dependency diagnostic refresh."""
    _HOST_SCRIPT_EDITORS.add(editor)


def unregister_host_script_editor(editor: CodeEditorWidget) -> None:
    """Stop tracking *editor* for dependency diagnostic refresh."""
    _HOST_SCRIPT_EDITORS.discard(editor)


def refresh_dependency_diagnostics(editor: CodeEditorWidget) -> None:
    """Re-scan direct ``local:`` dependencies for *editor*."""
    adapter = getattr(editor, "_lsp_adapter", None)
    if adapter is not None and hasattr(adapter, "refresh_dependency_diagnostics"):
        adapter.refresh_dependency_diagnostics()
        return
    apply_standalone_dependency_diagnostics(editor)


def apply_standalone_dependency_diagnostics(editor: CodeEditorWidget) -> None:
    """Apply direct ``local:`` dependency rows without an LSP adapter."""
    from services.scripting.local_dependency_diagnostics import (
        RequireAnchorDiagnostic,
        collect_direct_local_dependency_diagnostics,
    )
    from services.scripting.runtime_settings import RuntimeSettings
    from ui.widgets.code_editor.gutter import SyntaxError_, normalize_validation_severity

    if not RuntimeSettings.lsp_enabled():
        return
    bundle = collect_direct_local_dependency_diagnostics(
        editor.toPlainText(),
        editor.language,
    )
    problems = [*bundle.dependency_rows, *bundle.resolution_rows]
    mapped: list[SyntaxError_] = []
    for anchor in bundle.require_anchors:
        if not isinstance(anchor, RequireAnchorDiagnostic):
            continue
        mapped.append(
            SyntaxError_(
                line=anchor.line,
                column=anchor.column,
                message=anchor.message,
                severity=normalize_validation_severity(anchor.severity),
            )
        )
    editor.apply_validation_errors(mapped)
    editor.notify_lsp_diagnostics(problems)


def notify_lsp_diagnostics(editor: CodeEditorWidget, diags: list[Any]) -> None:
    """Emit :attr:`lsp_diagnostics_changed` for UI surfaces (e.g. Problems tab)."""
    editor.lsp_diagnostics_changed.emit(list(diags))


def refresh_dependency_diagnostics_for_script(script_id: int) -> None:
    """Re-scan host script editors after a local script is saved."""
    _ = script_id
    for editor in list(_HOST_SCRIPT_EDITORS):
        if Shiboken.isValid(editor):
            refresh_dependency_diagnostics(editor)


def sync_script_lsp_attachment_for_host(host: Any) -> None:
    """Refresh LSP attachment for every script editor owned by *host*."""
    for editor in _iter_host_script_editors(host):
        sync_script_lsp_attachment(editor)


def _iter_host_script_editors(host: Any) -> list[CodeEditorWidget]:
    editors: list[CodeEditorWidget] = []
    for attr in ("_pre_request_edit", "_test_script_edit"):
        ed = getattr(host, attr, None)
        if ed is not None:
            editors.append(ed)
    pane = getattr(host, "_pane", None)
    if pane is not None:
        ed = getattr(pane, "editor", None)
        if ed is not None:
            editors.append(ed)
    return editors


def on_lsp_signature_response(editor: CodeEditorWidget, future: Any) -> None:
    """Render LSP signature help or fall back to schema-driven hint."""
    info: Any = None
    try:
        info = future.result(timeout_s=0.0)
    except Exception:
        info = None
    if info is None or not getattr(info, "label", ""):
        editor._try_show_parameter_hint()
        return
    from ui.styling.theme import COLOR_ACCENT

    params = list(getattr(info, "parameters", []) or [])
    active = int(getattr(info, "active_parameter", 0) or 0)
    label = str(info.label)
    rendered: str
    if 0 <= active < len(params) and params[active] and params[active] in label:
        target = params[active]
        idx = label.find(target)
        rendered = (
            _html.escape(label[:idx])
            + f"<span style='color:{COLOR_ACCENT};font-weight:600;'>"
            + _html.escape(target)
            + "</span>"
            + _html.escape(label[idx + len(target) :])
        )
    else:
        rendered = _html.escape(label)
    doc = getattr(info, "documentation", None)
    if doc:
        rendered += f"<br><span style='font-size:11px;opacity:0.8;'>{_html.escape(str(doc))}</span>"
    cr = editor.cursorRect()
    gp = editor.mapToGlobal(cr.topLeft())
    editor._parameter_hint_popup.show_hint(gp, rendered, cr.height())


def on_lsp_hover_response(editor: CodeEditorWidget, future: Any, path: str) -> None:
    """Render LSP hover text or fall back to schema lookup."""
    from ui.widgets.code_editor.completion.symbol_doc_popup import SymbolDoc

    text: str | None = None
    try:
        text = future.result(timeout_s=0.0)
    except Exception:
        text = None
    if not text:
        sym = editor._completion_engine.resolve_symbol(path, editor.toPlainText())
        if sym is None:
            return
        cr = editor.cursorRect()
        gp = editor.mapToGlobal(cr.bottomLeft())
        editor._symbol_hover_global_pos = gp
        editor._symbol_doc_popup.show_for(gp, sym)
        return
    sym = SymbolDoc(
        label=path,
        kind="lsp",
        type_str="",
        doc=text.strip(),
        signature="",
        origin="LSP",
    )
    cr = editor.cursorRect()
    gp = editor.mapToGlobal(cr.bottomLeft())
    editor._symbol_hover_global_pos = gp
    editor._symbol_doc_popup.show_for(gp, sym)


def request_merged_completions(
    editor: CodeEditorWidget,
    schema_items: list[Any],
    *,
    on_ready: Any,
) -> bool:
    """Request LSP completions and invoke *on_ready* with merged engine items.

    Returns ``True`` when an async LSP request was started.
    """
    from ui.widgets.code_editor.lsp_integration import EditorLspAdapter, merge_completion_items

    if getattr(editor, "_debug_session_active", False):
        return False
    adapter = getattr(editor, "_lsp_adapter", None)
    if not isinstance(adapter, EditorLspAdapter) or not adapter.is_ready:
        return False
    future = adapter.request_completion()
    if future is None:
        return False

    def _done(f: Any) -> None:
        try:
            lsp_items = f.result() or []
        except Exception:
            lsp_items = []
        merged = merge_completion_items(schema_items, lsp_items)
        if lsp_items or schema_items:
            on_ready(merged)
        else:
            on_ready([])

    future.add_done_callback(_done)
    return True


def trigger_parameter_hint(editor: CodeEditorWidget) -> None:
    """Show parameter-info for the call surrounding the cursor (used by Ctrl+P shortcuts)."""
    adapter = getattr(editor, "_lsp_adapter", None)
    if adapter is not None:
        future = adapter.request_signature()
        if future is not None:
            future.add_done_callback(lambda f: on_lsp_signature_response(editor, f))
            return
    editor._try_show_parameter_hint()
