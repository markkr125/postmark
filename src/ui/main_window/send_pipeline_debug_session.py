"""Debug session handlers — called by :class:`_SendPipelineMixin`.

``window`` is the MainWindow instance.
"""

from __future__ import annotations

from typing import Any

from shiboken6 import Shiboken

from ui.main_window.send_pipeline_debug import (
    _debug_hover_root_objects,
    _merge_debug_hover_values,
)


def _script_editors_for_host(host: Any) -> tuple[Any | None, Any | None]:
    """Return ``(pre_request_editor, test_editor)`` for a script host widget."""
    from ui.main_window.send_pipeline_debug import _ensure_script_host_materialized

    _ensure_script_host_materialized(host)
    pre = getattr(host, "_pre_request_edit", None)
    test = getattr(host, "_test_script_edit", None)
    return pre, test


def _clear_script_debug_highlights(host: Any) -> None:
    """Clear debug line and hover locals on all editors for *host*."""
    seen: set[int] = set()
    for editor in _script_editors_for_host(host):
        if editor is None:
            continue
        key = id(editor)
        if key in seen:
            continue
        seen.add(key)
        editor.set_debug_line(None)
        editor.set_debug_locals({})


def on_debug_paused(window: Any, info: dict) -> None:
    """Handle a debug pause event from the worker thread."""
    from services.scripting.debug import DebugPauseInfo

    editor: Any = window._resolve_debug_script_host()
    pause_info: DebugPauseInfo = info  # type: ignore[assignment]

    script_type = pause_info.get("script_type", "pre_request")
    line = pause_info.get("line", 0)

    pre_ed, test_ed = _script_editors_for_host(editor)
    target = pre_ed if script_type == "pre_request" else test_ed
    other = test_ed if script_type == "pre_request" else pre_ed
    if target is not None:
        target.set_debug_line(line)
        merged = _merge_debug_hover_values(dict(pause_info))
        roots = _debug_hover_root_objects(dict(pause_info))
        target.set_debug_locals(merged, root_values=roots)
    if other is not None and other is not target:
        other.set_debug_locals({})

    tabs = getattr(editor, "_tabs", None)
    scripts_tab = getattr(editor, "_scripts_tab", None)
    scripts_sub_tabs = getattr(editor, "_scripts_sub_tabs", None)
    if tabs is not None and scripts_tab is not None and scripts_sub_tabs is not None:
        scripts_idx = tabs.indexOf(scripts_tab)
        if scripts_idx >= 0:
            tabs.setCurrentIndex(scripts_idx)
        scripts_sub_tabs.setCurrentIndex(0 if script_type == "pre_request" else 1)

    pre = getattr(editor, "_pre_output_panel", None)
    testp = getattr(editor, "_test_output_panel", None)
    if script_type == "pre_request":
        if pre is not None:
            pre.show_debug_controls(pause_info)
        if testp is not None:
            testp.hide_debug_controls()
    else:
        if testp is not None:
            testp.show_debug_controls(pause_info)
        if pre is not None:
            pre.hide_debug_controls()

    controls_map = getattr(editor, "_debug_controls", None)
    if isinstance(controls_map, dict):
        active_key = "pre_request" if script_type == "pre_request" else "test"
        for key, ctrl in controls_map.items():
            pbar = ctrl.parentWidget()
            if key == active_key:
                ctrl.update_pause(pause_info)
                ctrl.show()
                if pbar is not None:
                    pbar.show()
            else:
                ctrl.clear_session()
                ctrl.hide()
                if pbar is not None:
                    pbar.hide()

    sched = getattr(editor, "_schedule_refresh_script_split_full_width_line", None)
    if callable(sched):
        sched()


def on_debug_step(window: Any, mode_name: str) -> None:
    """Handle a step request from the debug panel."""
    if window._debug_protocol is None:
        return
    from services.scripting.debug import StepMode

    mode_map = {
        "continue": StepMode.CONTINUE,
        "step_over": StepMode.STEP_OVER,
        "step_into": StepMode.STEP_INTO,
        "step_out": StepMode.STEP_OUT,
        "stop": StepMode.STOP,
    }
    mode = mode_map.get(mode_name, StepMode.CONTINUE)

    host: Any = window._resolve_debug_script_host()
    _clear_script_debug_highlights(host)

    if mode == StepMode.STOP:
        window._debug_protocol.stop()
    else:
        window._debug_protocol.resume(mode)


def on_debug_finished(window: Any, data: dict) -> None:
    """Handle completion of a debug send."""
    window._debug_protocol = None
    window._on_send_finished(data)
    end_debug_ui(window)


def on_debug_error(window: Any, message: str) -> None:
    """Handle an error during a debug send."""
    window._debug_protocol = None
    window._on_send_error(message)
    end_debug_ui(window)


def end_debug_ui(window: Any) -> None:
    """Clean up debug UI state after a session ends."""
    window._clear_debug_breakpoint_listeners()
    host: Any = window._resolve_debug_script_host()
    if host is None or not Shiboken.isValid(host):
        window._clear_debug_script_host_pin()
        return
    _clear_script_debug_highlights(host)
    for name in ("_pre_output_panel", "_test_output_panel"):
        p = getattr(host, name, None)
        if p is not None and hasattr(p, "hide_debug_controls"):
            p.hide_debug_controls()
    controls_map = getattr(host, "_debug_controls", None)
    if isinstance(controls_map, dict):
        for ctrl in controls_map.values():
            ctrl.clear_session()
            ctrl.hide()
            pbar = ctrl.parentWidget()
            if pbar is not None:
                pbar.hide()
    pane = getattr(host, "_pane", None)
    if pane is not None and hasattr(pane, "hide_debug_toolbar"):
        pane.hide_debug_toolbar()
    sched = getattr(host, "_schedule_refresh_script_split_full_width_line", None)
    if callable(sched):
        sched()
    window._clear_debug_script_host_pin()


def end_inline_script_debug(window: Any) -> None:
    """Clear inline script debug state when :class:`ScriptDebugWorker` ends."""
    window._debug_protocol = None
    end_debug_ui(window)
