"""Tests for the debug call-stack sidebar widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from services.scripting.debug import CallFrame, DebugPauseInfo
from ui.sidebar.debug_call_stack_panel import CallStackPanel


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
