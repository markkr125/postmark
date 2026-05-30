"""Regression: script editor keystrokes must not invoke debug watch evaluation."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QApplication

from services.scripting.debug.protocol import DebugProtocol
from ui.widgets.code_editor import CodeEditorWidget


def test_typing_does_not_call_debug_evaluate(
    qapp: QApplication,
    qtbot,
    monkeypatch,
) -> None:
    """Typing in the script editor must not invoke DebugProtocol.evaluate or submit_evaluate."""
    evaluate_calls = 0
    submit_calls = 0

    original_evaluate = DebugProtocol.evaluate

    def counting_evaluate(self: DebugProtocol, *args: Any, **kwargs: Any) -> str:
        nonlocal evaluate_calls
        evaluate_calls += 1
        return original_evaluate(self, *args, **kwargs)

    monkeypatch.setattr(DebugProtocol, "evaluate", counting_evaluate)

    if hasattr(DebugProtocol, "submit_evaluate"):
        original_submit = DebugProtocol.submit_evaluate

        def counting_submit(self: DebugProtocol, *args: Any, **kwargs: Any) -> None:
            nonlocal submit_calls
            submit_calls += 1
            return original_submit(self, *args, **kwargs)

        monkeypatch.setattr(DebugProtocol, "submit_evaluate", counting_submit)

    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    editor.set_language("javascript")
    editor.setPlainText("// paused script\n")
    editor.set_debug_locals(
        {"x": 1},
        root_values={"pm": {"variables": {}}},
    )
    editor.setFocus()
    qtbot.waitExposed(editor)

    qtbot.keyClicks(editor, "console.log('hi');")

    assert evaluate_calls == 0
    assert submit_calls == 0
