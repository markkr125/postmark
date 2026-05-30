"""Debug inspector UI for :class:`ScriptOutputPanel` (variables and call stack)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from services.scripting.debug import DebugPauseInfo, DebugProtocol
from ui.sidebar.debug_inspector_split import DebugInspectorSplit
from ui.sidebar.debug_panel import DebugControls, _qt_valid
from ui.request.request_editor.scripts.breakpoints_dialog import BreakpointsDialog

if TYPE_CHECKING:
    pass


def build_debug_controls(panel: Any, parent_layout: QVBoxLayout) -> None:
    """Build step toolbar (placement handled by :class:`DebugInspectorSplit`)."""
    # Parent to the output panel immediately so it can never flash as a
    # transient top-level window during startup.
    panel._debug_controls = DebugControls(panel, keep_visible_when_idle=True)
    panel._debug_controls.setObjectName("scriptOutputDebugControls")
    panel._debug_controls.step_requested.connect(panel.debug_step_requested.emit)
    panel._debug_controls.start_debug_requested.connect(lambda: _on_start_debug(panel))
    panel._debug_controls.view_breakpoints_requested.connect(lambda: _on_view_breakpoints(panel))
    panel._debug_controls.breakpoints_enabled_toggled.connect(
        lambda enabled: _on_breakpoints_enabled_toggled(panel, enabled)
    )
    panel._debug_controls.pause_on_exceptions_toggled.connect(
        lambda enabled: _on_pause_on_exceptions_toggled(panel, enabled)
    )


def _host_editor(panel: Any) -> Any | None:
    host = getattr(panel, "_host_pane", None)
    if host is None or not _qt_valid(host):
        return None
    editor = getattr(host, "editor", None)
    if editor is None or not _qt_valid(editor):
        return None
    return editor


def _on_start_debug(panel: Any) -> None:
    """Start inline debug for the script pane bound to this output panel."""
    host = getattr(panel, "_host_pane", None)
    if host is None or not _qt_valid(host):
        return
    start = getattr(host, "debug", None)
    if callable(start):
        start()


def _on_view_breakpoints(panel: Any) -> None:
    """Show the breakpoint list and ensure the gutter is visible."""
    editor = _host_editor(panel)
    if editor is None:
        return
    editor.set_breakpoint_gutter_visible(True)
    protocol = getattr(panel, "_debug_protocol", None)
    host = getattr(panel, "_host_pane", None)
    dlg = BreakpointsDialog(
        editor,
        protocol=protocol,
        host_pane=host if _qt_valid(host) else None,
        parent=panel,
    )
    dlg.exec()


def _on_breakpoints_enabled_toggled(panel: Any, enabled: bool) -> None:
    protocol = getattr(panel, "_debug_protocol", None)
    if protocol is not None:
        protocol.set_breakpoints_enabled(enabled)


def _on_pause_on_exceptions_toggled(panel: Any, enabled: bool) -> None:
    protocol = getattr(panel, "_debug_protocol", None)
    if protocol is not None:
        protocol.set_pause_on_exceptions(enabled)


def build_debug_variables(panel: Any, parent_layout: QVBoxLayout) -> None:
    """Call stack + watches inspector with controls above Watches."""
    build_debug_controls(panel, parent_layout)
    parent_layout.setSpacing(8)

    panel._debug_inspector = DebugInspectorSplit(panel)
    panel._debug_inspector.set_controls_widget(panel._debug_controls)
    panel._debug_inspector.setSizePolicy(
        QSizePolicy.Policy.Preferred,
        QSizePolicy.Policy.Expanding,
    )
    parent_layout.addWidget(panel._debug_inspector, 1)

    # Back-compat aliases for tests and older code paths.
    panel._debug_call_stack = panel._debug_inspector.call_stack
    panel._debug_variables = panel._debug_inspector.scopes

    panel._debug_protocol = None


def on_debug_frame_selected(panel: Any, index: int) -> None:
    """Refresh variables and watch values for the selected stack frame."""
    protocol = panel._debug_protocol
    if protocol is None:
        return
    info = protocol.select_frame(index)
    if info is not None:
        panel._debug_inspector.update_pause(info)


def set_debug_protocol(panel: Any, protocol: DebugProtocol | None) -> None:
    """Attach the active :class:`DebugProtocol` for watch / frame selection."""
    panel._debug_protocol = protocol
    panel._debug_inspector.set_protocol(protocol)
    controls = getattr(panel, "_debug_controls", None)
    if controls is not None and _qt_valid(controls):
        if protocol is not None:
            protocol.set_breakpoints_enabled(not controls._disable_bp_btn.isChecked())
            protocol.set_pause_on_exceptions(controls._exception_bp_btn.isChecked())
        else:
            controls.reset_breakpoint_toolbar()


def _sync_host_debug_status(panel: Any, info: DebugPauseInfo | None) -> None:
    """Mirror pause status on the script editor status bar when bound to a pane."""
    host = getattr(panel, "_host_pane", None)
    if host is None or not _qt_valid(host):
        return
    if info is None:
        clear = getattr(host, "clear_debug_status_text", None)
        if callable(clear):
            clear()
        return
    show = getattr(host, "set_debug_pause_status", None)
    if callable(show):
        show(info)


def show_debug_controls(panel: Any, info: dict[str, Any]) -> None:
    """Show the debug variable list for the current pause payload."""
    panel._clear_result_rows()
    panel._elapsed_label.setText("")
    panel._timing_row.hide()
    pause: DebugPauseInfo = cast(DebugPauseInfo, info)
    controls = getattr(panel, "_debug_controls", None)
    if controls is not None and _qt_valid(controls):
        controls.update_pause(pause)
    _sync_host_debug_status(panel, pause)
    panel._debug_inspector.update_pause(pause)
    focus = getattr(panel, "focus_debugger_tab", None)
    if callable(focus):
        focus()
    schedule_script_split_line_refresh_on_host(panel)


def _idle_and_hide(widget: QWidget | None, idle_method: str) -> None:
    """Run *idle_method* on *widget* and hide it when the Qt object is still alive."""
    if widget is None or not _qt_valid(widget):
        return
    getattr(widget, idle_method)()
    widget.hide()


def hide_debug_controls(panel: Any) -> None:
    """Reset the debugger tab UI without changing the active output-strip tab."""
    _sync_host_debug_status(panel, None)
    controls = getattr(panel, "_debug_controls", None)
    if controls is not None and _qt_valid(controls):
        controls.set_idle()
        controls.reset_breakpoint_toolbar()
    inspector = getattr(panel, "_debug_inspector", None)
    if inspector is not None and _qt_valid(inspector):
        inspector.set_idle()
    if _qt_valid(panel):
        set_debug_protocol(panel, None)
        schedule_script_split_line_refresh_on_host(panel)


def schedule_script_split_line_refresh_on_host(panel: Any) -> None:
    """Reposition the scripts full-width split line after output-pane layout changes."""
    w: QWidget | None = panel
    while w is not None:
        sched = getattr(w, "_schedule_refresh_script_split_full_width_line", None)
        if callable(sched):
            sched()
            return
        w = w.parentWidget()
