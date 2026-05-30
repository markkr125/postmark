"""Post-response handlers — called by :class:`_SendPipelineMixin`.

``window`` is the MainWindow instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ui.request.request_editor import RequestEditorWidget
    from ui.request.request_editor.scripts.output_panel import ScriptOutputPanel


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
    editor = ctx.require_editor() if ctx is not None else window.request_widget
    window._history_panel.add_entry(
        editor._method_combo.currentText(),
        editor._url_input.text(),
        data.get("status_code"),
        data.get("elapsed_ms", 0),
    )
    window._refresh_sidebar()

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
