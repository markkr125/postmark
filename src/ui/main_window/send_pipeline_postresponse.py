"""Post-response handlers — called by :class:`_SendPipelineMixin`.

``window`` is the MainWindow instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from ui.request.request_editor import RequestEditorWidget
    from ui.request.request_editor.scripts.output_panel import ScriptOutputPanel


def _apply_replay_indicator(window: Any, ctx: Any, viewer: Any) -> None:
    """Show or clear the response viewer replay banner from tab context."""
    replay_id = getattr(ctx, "replay_source_entry_id", None) if ctx is not None else None
    if replay_id is None:
        viewer.clear_replay_history_source()
        return
    from services.request_history_service import RequestHistoryService

    entry = RequestHistoryService.get_entry(int(replay_id))
    if entry is not None:
        viewer.set_replay_history_source(
            int(replay_id),
            RequestHistoryService.replay_source_link_text(entry),
        )
    else:
        viewer.clear_replay_history_source()
    if ctx is not None:
        ctx.replay_source_entry_id = None


def _record_request_history(
    window: Any,
    ctx: Any,
    data: dict,
) -> None:
    """Persist this send to request history when guards pass."""
    cap = getattr(window, "_pending_history_context", None)
    tab_type = cap.get("tab_type") if isinstance(cap, dict) else None
    if tab_type is None and ctx is not None:
        tab_type = getattr(ctx, "tab_type", None)
    if tab_type != "request":
        if hasattr(window, "_clear_pending_history_capture"):
            window._clear_pending_history_capture()
        else:
            window._pending_request_snapshot = None
            window._pending_history_context = None
        return
    if getattr(window, "_suppress_history_record", False):
        if hasattr(window, "_clear_pending_history_capture"):
            window._clear_pending_history_capture()
        return
    settings = getattr(window, "_history_settings", None)
    if settings is None:
        if hasattr(window, "_clear_pending_history_capture"):
            window._clear_pending_history_capture()
        return
    from services.request_history_service import (
        PendingHistoryContextDict,
        RequestHistoryService,
        SendIdentityDict,
    )

    identity: SendIdentityDict
    if isinstance(cap, dict):
        cap_dict = cast(PendingHistoryContextDict, cap)
        identity = SendIdentityDict(
            request_id=cap_dict.get("request_id"),
            request_name=str(cap_dict.get("request_name", "")),
            method=str(data.get("request_method") or cap_dict.get("method", "GET")),
            url=str(data.get("request_url") or cap_dict.get("url", "")).strip(),
        )
    elif ctx is not None:
        editor = ctx.require_editor()
        identity = RequestHistoryService.gather_send_identity(ctx, editor, data)
    else:
        if hasattr(window, "_clear_pending_history_capture"):
            window._clear_pending_history_capture()
        return

    snapshot = getattr(window, "_pending_request_snapshot", None)
    try:
        entry_id = RequestHistoryService.record_send(
            identity=identity,
            response=data,
            original_request=snapshot if isinstance(snapshot, dict) else None,
            settings=settings,
        )
        if entry_id is not None:
            panel = getattr(window, "_request_history_panel", None)
            recorded_id = identity.get("request_id")
            active_id = cap.get("request_id") if isinstance(cap, dict) else None
            if active_id is None and ctx is not None:
                active_id = ctx.request_id
            if panel is not None and recorded_id is not None and active_id == recorded_id:
                panel.refresh()
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Failed to record request history")
        status = window.statusBar() if hasattr(window, "statusBar") else None
        if status is not None:
            status.showMessage("History was not saved (see application log)", 8000)
    finally:
        if hasattr(window, "_clear_pending_history_capture"):
            window._clear_pending_history_capture()
        else:
            window._pending_request_snapshot = None
            window._pending_history_context = None


def run_post_response_script_with_live_response(
    window: Any,
    *,
    editor: RequestEditorWidget,
    panel: ScriptOutputPanel,
    script: str,
    language: str,
    run_btn: Any,
    debug_btn: Any,
) -> None:
    """Send the active request first, then run one post-response script inline."""
    for btn in (run_btn, debug_btn):
        if btn is not None:
            btn.setEnabled(False)
    window._inline_test_run = {
        "editor": editor,
        "panel": panel,
        "script": script,
        "language": language,
        "run_btn": run_btn,
        "debug_btn": debug_btn,
    }
    panel.show_error("Sending request to fetch live response…")
    window._on_send_request()


def on_send_finished(window: Any, data: dict) -> None:
    """Handle a successful HTTP response from the worker thread."""
    inline_test = getattr(window, "_inline_test_run", None)
    ctx = window._current_tab_context()
    viewer = ctx.require_response_viewer() if ctx is not None else window.response_widget

    was_on_pre_request = (
        hasattr(viewer, "_pre_tab_index")
        and viewer._tabs.currentIndex() == viewer._pre_tab_index
        and viewer._tabs.isTabVisible(viewer._pre_tab_index)
    )

    viewer.load_response(data)
    _apply_replay_indicator(window, ctx, viewer)

    test_results = data.get("test_results", [])
    console_logs = data.get("console_logs", [])
    if test_results:
        viewer.load_test_results(test_results)

    if data.get("has_pre_request_scripts"):
        viewer.load_pre_request_data(
            console_logs=data.get("pre_request_console_logs", []),
            variable_changes=data.get("pre_request_variable_changes", {}),
            errors=data.get("pre_request_errors", []),
        )
        if was_on_pre_request:
            viewer._tabs.setCurrentIndex(viewer._pre_tab_index)

    if console_logs:
        from ui.panels.console_panel import ConsolePanel

        console_panel: ConsolePanel | None = getattr(window, "_console_panel", None)
        if console_panel is not None:
            for log_entry in console_logs:
                message = log_entry.get("message", "")
                level = log_entry.get("level", "log")
                if level == "error":
                    console_panel.append_error(f"[Script] {message}")
                else:
                    console_panel.append_message(f"[Script] {message}")

    var_changes = data.get("variable_changes", {})
    if ctx and ctx.tab_type not in ("folder", "environments", "local_script") and var_changes:
        _ = ctx.require_editor()
        for key, value in var_changes.items():
            ctx.local_overrides[key] = {
                "value": str(value),
                "original_source": "script",
                "original_source_id": 0,
            }

    window._set_send_button_cancel(False)
    if ctx is not None:
        idx = window._tab_bar.currentIndex()
        window._tab_bar.update_tab(idx, is_sending=False)
        ctx.cleanup_thread()
    else:
        window._cleanup_send_thread()
    window._refresh_sidebar()
    _record_request_history(window, ctx, data)

    if inline_test is not None:
        from ui.request.request_editor.scripts.script_run_worker import build_inline_context

        panel = inline_test.get("panel")
        script = str(inline_test.get("script", ""))
        language = str(inline_test.get("language", "javascript"))
        run_btn = inline_test.get("run_btn")
        debug_btn = inline_test.get("debug_btn")
        window._inline_test_run = None
        if script and panel is not None and hasattr(panel, "run_script"):
            response_payload = {
                "code": int(data.get("status_code", 0) or 0),
                "status": f"{data.get('status_code', '')} {data.get('status_text', '')}".strip(),
                "headers": data.get("headers", []),
                "body": str(data.get("body", "")),
                "responseTime": float(data.get("elapsed_ms", 0.0) or 0.0),
                "responseSize": int(data.get("size_bytes", 0) or 0),
            }
            context = build_inline_context(script_type="test", response_data=response_payload)
            panel.run_script(
                script=script,
                language=language,
                context=context,
                run_btn=run_btn,
                debug_btn=debug_btn,
            )
        else:
            for btn in (run_btn, debug_btn):
                if btn is not None:
                    btn.setEnabled(True)
