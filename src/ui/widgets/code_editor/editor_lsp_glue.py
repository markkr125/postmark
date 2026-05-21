"""Language-server attachment and response helpers for :class:`~editor_widget.CodeEditorWidget`."""

from __future__ import annotations

import html as _html
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ui.widgets.code_editor.editor_widget import CodeEditorWidget


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


def attach_lsp(editor: CodeEditorWidget, language: str) -> None:
    """Attach to the shared language server for *language* (script modes only).

    Reuses the existing adapter when the new language maps to the
    same LSP client family (JS ↔ TS share the Deno server). Avoids
    the detach + signal-reconnect round-trip that previously caused
    a noticeable lag and dropped diagnostics on language toggle.
    """
    from services.scripting.runtime_settings import RuntimeSettings
    from ui.widgets.code_editor.lsp_integration import EditorLspAdapter

    prev = getattr(editor, "_lsp_adapter", None)
    if prev is not None and prev.can_swap_to(language) and prev.swap_language(language):
        return
    if prev is not None:
        prev.detach()
    editor._lsp_adapter = None
    if not RuntimeSettings.lsp_enabled():
        editor._validate_timer.start()
        return
    # Pre-spawn both shared LSP clients so the next language switch
    # finds them already initialised (no subprocess + handshake lag).
    from services.lsp.server_registry import LspRegistry as _Reg

    _Reg.instance().warm()
    adapter = EditorLspAdapter(editor, parent=editor)
    if adapter.attach(language):
        editor._lsp_adapter = adapter
    else:
        adapter.detach()
        editor._validate_timer.start()


def detach_lsp(editor: CodeEditorWidget) -> None:
    """Disconnect from the language server and restore legacy validation."""
    prev = getattr(editor, "_lsp_adapter", None)
    if prev is not None:
        prev.detach()
    editor._lsp_adapter = None


def notify_lsp_diagnostics(editor: CodeEditorWidget, diags: list[Any]) -> None:
    """Emit :attr:`lsp_diagnostics_changed` for UI surfaces (e.g. Problems tab).

    *diags* is a list of :class:`services.lsp.client.Diagnostic` instances.
    """
    editor.lsp_diagnostics_changed.emit(list(diags))


def sync_script_lsp_attachment(editor: CodeEditorWidget) -> None:
    """Start or stop LSP based on language mode and read-only state."""
    if editor._read_only or editor.isReadOnly():
        detach_lsp(editor)
        return
    lang = editor._language
    if lang in ("javascript", "typescript", "python"):
        attach_lsp(editor, lang)
    else:
        detach_lsp(editor)
        editor._validate_timer.start()


def trigger_parameter_hint(editor: CodeEditorWidget) -> None:
    """Show parameter-info for the call surrounding the cursor (used by Ctrl+P shortcuts)."""
    adapter = getattr(editor, "_lsp_adapter", None)
    if adapter is not None:
        future = adapter.request_signature()
        if future is not None:
            future.add_done_callback(lambda f: on_lsp_signature_response(editor, f))
            return
    editor._try_show_parameter_hint()


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
