"""UI tests for breakpoint/watch persistence."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from services.scripting.debug import DebugProtocol, DebugState
from ui.widgets.code_editor import CodeEditorWidget


def test_replace_breakpoints_no_emit_by_default(qapp: QApplication) -> None:
    """Load-path restore must not emit ``breakpoints_changed`` by default."""
    editor = CodeEditorWidget()
    emitted: list[object] = []
    editor.breakpoints_changed.connect(lambda: emitted.append(True))
    editor.replace_breakpoints({4: None, 9: "x > 1"})
    assert editor.breakpoints == {4: None, 9: "x > 1"}
    assert emitted == []
    editor.replace_breakpoints({1: None}, emit=True)
    assert len(emitted) == 1


def test_scopes_set_watch_expressions(
    qapp: QApplication,
    qtbot,
) -> None:
    """``set_watch_expressions`` replaces the watch list."""
    from ui.sidebar.debug_scopes_panel import DebugScopesPanel

    panel = DebugScopesPanel()
    qtbot.addWidget(panel)
    panel.set_watch_expressions(["pm.a", "pm.b"])
    assert panel.watch_state.expressions == ["pm.a", "pm.b"]
    panel.set_watch_expressions([])
    assert panel.watch_state.expressions == []


def test_scopes_is_paused(qapp: QApplication, qtbot) -> None:
    """``is_paused`` reflects protocol state."""
    from ui.sidebar.debug_scopes_panel import DebugScopesPanel

    panel = DebugScopesPanel()
    qtbot.addWidget(panel)
    assert not panel.is_paused()
    proto = DebugProtocol()
    with proto._lock:
        proto._state = DebugState.PAUSED
    panel.set_protocol(proto)
    assert panel.is_paused()
