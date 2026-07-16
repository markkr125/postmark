"""Apply drained execute bridge events to centre-pane UI."""

from __future__ import annotations

from typing import Any, Literal

from services.ai.chat.mutation.bridge import MutationBridgeEvent


def apply_executed_event(host: Any, event: MutationBridgeEvent) -> None:
    """Open tabs / script output for one ``executed`` bridge event."""
    action = str(event.get("action") or "")
    ids = event.get("ids") or {}
    payload = event.get("payload") or {}
    if not isinstance(ids, dict):
        ids = {}
    if not isinstance(payload, dict):
        payload = {}

    if action in {"send_request", "send_draft", "replay_history"}:
        hist = ids.get("history_entry_id")
        if isinstance(hist, int) and hist > 0:
            open_hist = getattr(host, "_open_from_global_history", None)
            if callable(open_hist):
                open_hist(hist, load_centre_response=True)
        return

    if action == "run_scripts":
        request_id = ids.get("request_id")
        if not isinstance(request_id, int) or request_id <= 0:
            return
        open_request = getattr(host, "_open_request", None)
        if not callable(open_request):
            return
        phase = str(payload.get("script_phase") or "both")
        scripts_kind = _scripts_focus_kind(phase)
        if not open_request(request_id, push_history=True, is_preview=False):
            return
        current_ctx = getattr(host, "_current_tab_context", None)
        ctx = current_ctx() if callable(current_ctx) else None
        if ctx is not None and ctx.editor is not None and ctx.request_id == request_id:
            focus = getattr(ctx.editor, "focus_section", None)
            if callable(focus):
                focus("scripts", scripts_kind=scripts_kind)
            _show_request_script_output(ctx, payload, scripts_kind)
        return

    if action == "run_local_script":
        script_id = ids.get("local_script_id")
        if not isinstance(script_id, int) or script_id <= 0:
            return
        open_script = getattr(host, "_open_local_script", None)
        if not callable(open_script):
            return
        if not open_script(script_id):
            return
        current_ctx = getattr(host, "_current_tab_context", None)
        ctx = current_ctx() if callable(current_ctx) else None
        if (
            ctx is not None
            and getattr(ctx, "tab_type", None) == "local_script"
            and getattr(ctx, "local_script_id", None) == script_id
            and getattr(ctx, "local_script_editor", None) is not None
        ):
            _show_local_script_output(ctx.local_script_editor, payload)
        return

    if action == "run_collection":
        collection_id = ids.get("collection_id")
        if not isinstance(collection_id, int) or collection_id <= 0:
            return
        open_folder = getattr(host, "_open_folder", None)
        if callable(open_folder):
            open_folder(collection_id, focus_runner_panel=True)
        _reload_folder_runs(host, collection_id)
        return

    if action == "run_iterations":
        request_id = ids.get("request_id")
        if not isinstance(request_id, int) or request_id <= 0:
            return
        open_request = getattr(host, "_open_request", None)
        if not callable(open_request):
            return
        if not open_request(request_id, push_history=True, is_preview=False):
            return
        current_ctx = getattr(host, "_current_tab_context", None)
        ctx = current_ctx() if callable(current_ctx) else None
        if ctx is not None and ctx.editor is not None and ctx.request_id == request_id:
            focus = getattr(ctx.editor, "focus_section", None)
            if callable(focus):
                focus("scripts", scripts_kind="test")
            _show_request_script_output(ctx, payload, "test")
            _show_iterations_matrix(ctx, payload)
        return


def _reload_folder_runs(host: Any, collection_id: int) -> None:
    """Refresh the open folder editor's Runs history table from the DB."""
    from services.run_history_service import RunHistoryService

    tabs = getattr(host, "_tabs", None)
    if not isinstance(tabs, dict):
        return
    runs = RunHistoryService.get_runs(collection_id)
    for ctx in tabs.values():
        if getattr(ctx, "tab_type", None) != "folder":
            continue
        if getattr(ctx, "collection_id", None) != collection_id:
            continue
        editor = getattr(ctx, "folder_editor", None)
        if editor is None:
            continue
        load_runs = getattr(editor, "load_runs", None)
        if callable(load_runs):
            load_runs(runs)
        return


def _show_iterations_matrix(ctx: Any, payload: dict[str, object]) -> None:
    """Best-effort update of the Scripts iterations matrix tab."""
    editor = getattr(ctx, "editor", None)
    if editor is None:
        return
    panel = getattr(editor, "_test_output_panel", None)
    if panel is None:
        return
    iterations = payload.get("iterations")
    if not isinstance(iterations, list):
        return
    show_matrix = getattr(panel, "show_iteration_results", None)
    if callable(show_matrix):
        show_matrix(iterations)
        return
    # Fallback: aggregate already applied via show_results in _show_request_script_output.


def _scripts_focus_kind(phase: str) -> Literal["pre_request", "test"]:
    """Map run_scripts phase to the Scripts sub-tab."""
    if phase == "pre":
        return "pre_request"
    return "test"


def _show_request_script_output(ctx: Any, payload: dict[str, object], scripts_kind: str) -> None:
    """Push agent script output into the request Scripts output panel."""
    editor = getattr(ctx, "editor", None)
    if editor is None:
        return
    ensure = getattr(editor, "_ensure_scripts_editors", None)
    if callable(ensure):
        ensure()
    panel = (
        getattr(editor, "_pre_output_panel", None)
        if scripts_kind == "pre_request"
        else getattr(editor, "_test_output_panel", None)
    )
    if panel is None:
        return
    output = _output_from_payload(payload)
    show = getattr(panel, "show_results", None)
    if callable(show):
        show(output, _elapsed_ms(payload), focus_output=True)


def _show_local_script_output(editor: Any, payload: dict[str, object]) -> None:
    """Push agent local-script output into the tab output panel."""
    pane = getattr(editor, "_pane", None)
    if pane is None:
        return
    panel = getattr(pane, "output_panel", None)
    if panel is None:
        return
    output = _output_from_payload(payload)
    show = getattr(panel, "show_results", None)
    if callable(show):
        show(output, _elapsed_ms(payload), focus_output=True)


def _elapsed_ms(payload: dict[str, object]) -> float:
    """Coerce bridge payload elapsed_ms to float."""
    raw = payload.get("elapsed_ms")
    if isinstance(raw, int | float):
        return float(raw)
    return 0.0


def _output_from_payload(payload: dict[str, object]) -> dict[str, object]:
    """Build a ScriptOutput-shaped dict from a bridge execute payload."""
    test_results = payload.get("test_results")
    console_logs = payload.get("console_logs")
    return {
        "test_results": list(test_results) if isinstance(test_results, list) else [],
        "console_logs": list(console_logs) if isinstance(console_logs, list) else [],
        "variable_changes": {},
        "global_variable_changes": {},
        "error": None,
    }
