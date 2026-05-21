"""Debug inspector UI for :class:`ScriptOutputPanel` (variables, watch, call stack)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from services.scripting.debug import DebugPauseInfo, DebugProtocol
from ui.sidebar.debug_call_stack_panel import CallStackPanel
from ui.sidebar.debug_panel import DebugVariablesPanel, _qt_valid
from ui.sidebar.debug_watch_panel import WatchPanel

if TYPE_CHECKING:
    pass


def build_debug_variables(panel: Any, parent_layout: QVBoxLayout) -> None:
    """Debug inspector sections (hidden until a debug session pauses)."""
    panel._debug_call_stack = CallStackPanel(panel)
    panel._debug_call_stack.hide()
    panel._debug_call_stack.frame_selected.connect(
        lambda index: on_debug_frame_selected(panel, index)
    )
    parent_layout.addWidget(panel._debug_call_stack)

    panel._debug_variables = DebugVariablesPanel(panel)
    panel._debug_variables.setSizePolicy(
        QSizePolicy.Policy.Preferred,
        QSizePolicy.Policy.Expanding,
    )
    panel._debug_variables.hide()
    parent_layout.addWidget(panel._debug_variables, 100)

    panel._debug_watch = WatchPanel(panel)
    panel._debug_watch.hide()
    parent_layout.addWidget(panel._debug_watch)

    panel._debug_protocol = None


def on_debug_frame_selected(panel: Any, index: int) -> None:
    """Refresh variables and watch values for the selected stack frame."""
    protocol = panel._debug_protocol
    if protocol is None:
        return
    info = protocol.select_frame(index)
    if info is not None:
        panel._debug_variables.update_pause(info)
        panel._debug_watch.refresh()


def set_debug_protocol(panel: Any, protocol: DebugProtocol | None) -> None:
    """Attach the active :class:`DebugProtocol` for watch / frame selection."""
    panel._debug_protocol = protocol
    panel._debug_watch.set_protocol(protocol)


def show_debug_controls(panel: Any, info: dict[str, Any]) -> None:
    """Show the debug variable list for the current pause payload."""
    panel._clear_result_rows()
    panel._elapsed_label.setText("")
    panel._timing_row.hide()
    pause: DebugPauseInfo = cast(DebugPauseInfo, info)
    panel._debug_call_stack.update_pause(pause)
    panel._debug_call_stack.setVisible(True)
    panel._debug_variables.update_pause(pause)
    panel._debug_variables.setVisible(True)
    panel._debug_watch.update_pause()
    panel._debug_watch.setVisible(True)
    schedule_script_split_line_refresh_on_host(panel)


def _idle_and_hide(widget: QWidget | None, idle_method: str) -> None:
    """Run *idle_method* on *widget* and hide it when the Qt object is still alive."""
    if not _qt_valid(widget):
        return
    getattr(widget, idle_method)()
    widget.hide()


def hide_debug_controls(panel: Any) -> None:
    """Hide the debug inspector sections."""
    _idle_and_hide(getattr(panel, "_debug_call_stack", None), "set_idle")
    _idle_and_hide(getattr(panel, "_debug_variables", None), "set_idle")
    _idle_and_hide(getattr(panel, "_debug_watch", None), "set_idle")
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
