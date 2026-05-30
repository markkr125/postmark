"""Tests for watch expressions in :class:`DebugWatchesPane`."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from services.scripting.debug import CallFrame, DebugPauseInfo
from services.scripting.debug.protocol import (
    WATCH_EVAL_ERROR_PREFIX,
    DebugProtocol,
    DebugState,
)
from ui.sidebar.debug_panel import DebugVariablesPanel
from ui.sidebar.debug_watch_in_tree import WATCH_VALUE_PLACEHOLDER
from ui.widgets.debug_value_tree import debug_tree_cell_text


def _pause_info(
    *,
    local_vars: dict | None = None,
    stack: list[CallFrame] | None = None,
    selected: int = 0,
) -> DebugPauseInfo:
    return {
        "line": 0,
        "source_name": "inline",
        "local_vars": local_vars or {},
        "script_type": "pre_request",
        "env_changes": {},
        "global_changes": {},
        "call_stack": stack or [],
        "selected_frame_index": selected,
    }


class TestDebugVariablesWatches:
    """Watch rows live under a Watches section in the variables tree."""

    def test_add_watch_shows_tree_row(self, qapp: QApplication, qtbot) -> None:
        panel = DebugVariablesPanel()
        qtbot.addWidget(panel)
        proto = DebugProtocol()
        proto.set_evaluate_callback(lambda expr, _frame: f"val({expr})")
        with proto._lock:
            proto._state = DebugState.PAUSED
        panel.set_protocol(proto)
        panel._watch_add_edit.setText("pm.response.code")
        with qtbot.waitSignal(proto.evaluated, timeout=3000):
            panel._add_watch_expression()
        assert panel._tree.topLevelItemCount() == 1
        root = panel._tree.topLevelItem(0)
        assert root is not None
        assert root.text(0) == "Watches"
        assert root.childCount() == 1
        child = root.child(0)
        assert child is not None
        assert debug_tree_cell_text(child, 0) == "pm.response.code"
        assert "val(pm.response.code)" in debug_tree_cell_text(child, 1)

    def test_remove_watch_by_index_not_expression(self, qapp: QApplication, qtbot) -> None:
        panel = DebugVariablesPanel()
        qtbot.addWidget(panel)
        panel._watch_add_edit.setText("pm.a")
        panel._add_watch_expression()
        panel._watch_add_edit.setText("pm.a")
        panel._add_watch_expression()
        root = panel._watches_root
        assert root is not None
        second = root.child(1)
        assert second is not None
        panel._tree.setCurrentItem(second)
        panel._remove_selected_watch()
        assert panel.watch_state.expressions == ["pm.a"]
        assert root.childCount() == 1
        first = root.child(0)
        assert first is not None
        assert debug_tree_cell_text(first, 0) == "pm.a"

    def test_frame_change_re_evaluates(self, qapp: QApplication, qtbot) -> None:
        panel = DebugVariablesPanel()
        qtbot.addWidget(panel)
        frames: list[int] = []

        def evaluate(expr: str, frame: int) -> str:
            frames.append(frame)
            return f"f{frame}:{expr}"

        proto = DebugProtocol()
        proto.set_evaluate_callback(evaluate)
        proto.set_frame_locals_callback(lambda idx: {"x": idx})
        with proto._lock:
            proto._state = DebugState.PAUSED
        panel.set_protocol(proto)
        panel._watch_add_edit.setText("x")
        with qtbot.waitSignal(proto.evaluated, timeout=3000):
            panel._add_watch_expression()
        stack: list[CallFrame] = [
            CallFrame(id="a", name="top", line=0, column=0),
            CallFrame(id="b", name="helper", line=4, column=0),
        ]
        pause0 = _pause_info(stack=stack, selected=0)
        with proto._lock:
            proto._pause_info = pause0
        with qtbot.waitSignal(proto.evaluated, timeout=3000):
            panel.update_pause(pause0)
        child = panel._watches_root
        assert child is not None
        row = child.child(0)
        assert row is not None
        assert "f0:x" in debug_tree_cell_text(row, 1)
        info = proto.select_frame(1)
        assert info is not None
        with qtbot.waitSignal(proto.evaluated, timeout=3000):
            panel.update_pause(info)
        root2 = panel._watches_root
        assert root2 is not None
        row2 = root2.child(0)
        assert row2 is not None
        assert "f1:x" in debug_tree_cell_text(row2, 1)

    def test_clear_session_keeps_expressions_tree_page(self, qapp: QApplication, qtbot) -> None:
        panel = DebugVariablesPanel()
        qtbot.addWidget(panel)
        panel._watch_add_edit.setText("pm.y")
        panel._add_watch_expression()
        panel._watch_add_edit.setText("kept-draft")
        proto = DebugProtocol()
        proto.set_evaluate_callback(lambda expr, _frame: "42")
        with proto._lock:
            proto._state = DebugState.PAUSED
        panel.set_protocol(proto)
        with qtbot.waitSignal(proto.evaluated, timeout=3000):
            panel.update_pause(_pause_info(local_vars={"a": 1}))
        panel.clear_session()
        assert len(panel.watch_state.expressions) == 1
        root = panel._tree.topLevelItem(0)
        assert root is not None
        assert root.text(0) == "Watches"
        child = root.child(0)
        assert child is not None
        assert debug_tree_cell_text(child, 1) == WATCH_VALUE_PLACEHOLDER
        assert panel._watch_add_edit.text() == "kept-draft"

    def test_set_idle_shows_watches_dash(self, qapp: QApplication, qtbot) -> None:
        panel = DebugVariablesPanel()
        qtbot.addWidget(panel)
        panel._watch_add_edit.setText("pm.x")
        panel._add_watch_expression()
        proto = DebugProtocol()
        with proto._lock:
            proto._state = DebugState.PAUSED
        panel.set_protocol(proto)
        panel.update_pause(_pause_info())
        panel.set_idle()
        assert len(panel.watch_state.expressions) == 1
        assert panel._protocol is None
        root = panel._tree.topLevelItem(0)
        assert root is not None
        assert root.text(0) == "Watches"
        assert root.childCount() == 1
        child = root.child(0)
        assert child is not None
        assert debug_tree_cell_text(child, 1) == WATCH_VALUE_PLACEHOLDER

    def test_empty_pause_zero_watches_can_add_first(self, qapp: QApplication, qtbot) -> None:
        """Paused with no locals and no watches still shows the add strip on the tree page."""
        panel = DebugVariablesPanel()
        qtbot.addWidget(panel)
        proto = DebugProtocol()
        with proto._lock:
            proto._state = DebugState.PAUSED
        panel.set_protocol(proto)
        panel.update_pause(_pause_info(local_vars={}))
        assert panel._tree.topLevelItemCount() == 0
        panel._watch_add_edit.setText("1+1")
        panel._add_watch_expression()
        assert panel._tree.topLevelItemCount() == 1
        root = panel._tree.topLevelItem(0)
        assert root is not None
        assert root.text(0) == "Watches"

    def test_remove_last_watch_drops_section_header(self, qapp: QApplication, qtbot) -> None:
        """Removing the last watch removes the Watches top-level section."""
        panel = DebugVariablesPanel()
        qtbot.addWidget(panel)
        panel._watch_add_edit.setText("only")
        panel._add_watch_expression()
        assert panel._tree.topLevelItemCount() == 1
        root = panel._watches_root
        assert root is not None
        row = root.child(0)
        assert row is not None
        panel._tree.setCurrentItem(row)
        panel._remove_selected_watch()
        assert panel._tree.topLevelItemCount() == 0
        assert panel._watches_root is None

    def test_watch_eval_error_shows_question_mark(self, qapp: QApplication, qtbot) -> None:
        """Runtime evaluate errors display as ``?`` in the value column."""
        panel = DebugVariablesPanel()
        qtbot.addWidget(panel)
        proto = DebugProtocol()
        proto.set_evaluate_callback(lambda _expr, _frame: f"{WATCH_EVAL_ERROR_PREFIX}syntax")
        with proto._lock:
            proto._state = DebugState.PAUSED
        panel.set_protocol(proto)
        panel._watch_add_edit.setText("bad")
        with qtbot.waitSignal(proto.evaluated, timeout=3000):
            panel._add_watch_expression()
        with qtbot.waitSignal(proto.evaluated, timeout=3000):
            panel.refresh_watches()
        root = panel._watches_root
        assert root is not None
        row = root.child(0)
        assert row is not None
        assert debug_tree_cell_text(row, 1) == "?"

    def test_watch_cdp_multiline_error_not_scrambled(self, qapp: QApplication, qtbot) -> None:
        """CDP-style multi-line ReferenceError text shows ``?``, not a stack in the tree."""
        panel = DebugVariablesPanel()
        qtbot.addWidget(panel)
        proto = DebugProtocol()
        proto.set_evaluate_callback(
            lambda _expr, _frame: (
                "ReferenceError: randomId is not defined\n"
                "    at eval (eval at _pm_debugUserScript (file:///tmp/x:1:1))"
            )
        )
        with proto._lock:
            proto._state = DebugState.PAUSED
        panel.set_protocol(proto)
        panel._watch_add_edit.setText("randomId")
        with qtbot.waitSignal(proto.evaluated, timeout=3000):
            panel._add_watch_expression()
        with qtbot.waitSignal(proto.evaluated, timeout=3000):
            panel.refresh_watches()
        root = panel._watches_root
        assert root is not None
        row = root.child(0)
        assert row is not None
        assert debug_tree_cell_text(row, 1) == "?"
        assert "\n" not in debug_tree_cell_text(row, 1)
        tip = row.toolTip(1)
        assert "randomId is not defined" in tip

    def test_remove_watch_via_row_trash_button(self, qapp: QApplication, qtbot) -> None:
        """Each watch row exposes a trash control on the right."""
        panel = DebugVariablesPanel()
        qtbot.addWidget(panel)
        panel._watch_add_edit.setText("pm.a")
        panel._add_watch_expression()
        panel._watch_add_edit.setText("pm.b")
        panel._add_watch_expression()
        root = panel._watches_root
        assert root is not None
        row = root.child(0)
        assert row is not None
        host = panel._tree.itemWidget(row, 1)
        assert host is not None
        btn = host.findChild(QPushButton, "debugWatchRowRemoveButton")
        assert btn is not None
        assert btn.objectName() == "debugWatchRowRemoveButton"
        qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        assert panel.watch_state.expressions == ["pm.b"]

    def test_watch_label_click_selects_row(self, qapp: QApplication, qtbot) -> None:
        """Clicking the expression label selects the watch row for toolbar removal."""
        panel = DebugVariablesPanel()
        qtbot.addWidget(panel)
        panel._watch_add_edit.setText("x")
        panel._add_watch_expression()
        root = panel._watches_root
        assert root is not None
        row = root.child(0)
        assert row is not None
        label = panel._tree.itemWidget(row, 0)
        assert isinstance(label, QLabel)
        panel._tree.clearSelection()
        qtbot.mouseClick(label, Qt.MouseButton.LeftButton)
        assert panel._tree.currentItem() is row
