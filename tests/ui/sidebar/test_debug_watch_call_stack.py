"""Tests for watch-expression and call-stack debug sidebar widgets."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from services.scripting.debug import CallFrame, DebugPauseInfo
from services.scripting.debug.protocol import DebugProtocol, DebugState
from ui.sidebar.debug_call_stack_panel import CallStackPanel
from ui.sidebar.debug_watch_panel import WatchPanel


def _pause_info(
    *,
    stack: list[CallFrame] | None = None,
    selected: int = 0,
) -> DebugPauseInfo:
    return {
        "line": 0,
        "source_name": "inline",
        "local_vars": {},
        "script_type": "pre_request",
        "env_changes": {},
        "global_changes": {},
        "call_stack": stack or [],
        "selected_frame_index": selected,
    }


class TestWatchPanel:
    """Watch expressions call :meth:`DebugProtocol.evaluate` on refresh."""

    def test_refresh_shows_evaluated_value(self, qapp: QApplication, qtbot) -> None:
        panel = WatchPanel()
        qtbot.addWidget(panel)
        proto = DebugProtocol()
        proto.set_evaluate_callback(lambda expr, _frame: f"val({expr})")
        with proto._lock:
            proto._state = DebugState.PAUSED
        panel.set_protocol(proto)
        panel._input.setText("pm.response.code")
        panel._add_expression()
        panel.refresh()
        row = panel._list.item(0)
        assert row is not None
        assert "val(pm.response.code)" in row.text()

    def test_add_expression_via_return(self, qapp: QApplication, qtbot) -> None:
        panel = WatchPanel()
        qtbot.addWidget(panel)
        panel._input.setText("globals.foo")
        panel._add_expression()
        assert panel.expressions() == ["globals.foo"]
        assert panel._list.count() == 1


class TestCallStackPanel:
    """Call stack emits frame index when the user selects a row."""

    def test_update_pause_lists_frames(self, qapp: QApplication, qtbot) -> None:
        panel = CallStackPanel()
        qtbot.addWidget(panel)
        stack: list[CallFrame] = [
            CallFrame(id="a", name="top", line=0, column=0),
            CallFrame(id="b", name="helper", line=4, column=0),
        ]
        panel.update_pause(_pause_info(stack=stack, selected=1))
        assert panel._list.count() == 2
        assert "helper" in panel._list.item(1).text()

    def test_frame_selected_signal(self, qapp: QApplication, qtbot) -> None:
        panel = CallStackPanel()
        qtbot.addWidget(panel)
        stack: list[CallFrame] = [
            CallFrame(id="a", name="top", line=0, column=0),
            CallFrame(id="b", name="helper", line=4, column=0),
        ]
        panel.update_pause(_pause_info(stack=stack))
        seen: list[int] = []
        panel.frame_selected.connect(seen.append)
        panel._list.setCurrentRow(1)
        assert seen == [1]
