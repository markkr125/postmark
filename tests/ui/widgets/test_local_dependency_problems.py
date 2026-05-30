"""UI tests for local dependency rows in the Problems tab."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from services.lsp.client import Diagnostic
from ui.request.request_editor.scripts.lsp_problems_tab import (
    ScriptLspProblemsTab,
    format_problem_line,
)
from ui.widgets.code_editor.editor_widget import CodeEditorWidget


def test_format_problem_line_includes_local_path() -> None:
    """Dependency diagnostics show the virtual path prefix."""
    row = Diagnostic(
        line=6,
        column=0,
        end_line=6,
        end_column=1,
        severity="error",
        message="CommonJS module.exports is not supported.",
        source="postmark",
        related_local_path="home/tests/testjs.js",
        related_local_script_id=42,
        related_line=6,
        related_column=0,
    )
    text = format_problem_line(row)
    assert "[local:home/tests/testjs.js]" in text
    assert "Ln 7" in text


def test_problems_click_invokes_open_local_script_handler(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clicking a dependency row opens the local script via the registered handler."""
    opened: list[int] = []

    def _handler(script_id: int) -> None:
        opened.append(script_id)

    CodeEditorWidget.set_open_local_script_handler(_handler)

    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    panel = ScriptLspProblemsTab()
    qtbot.addWidget(panel)
    panel.set_editor(editor)

    row = Diagnostic(
        line=0,
        column=0,
        end_line=0,
        end_column=1,
        severity="error",
        message="CommonJS module.exports is not supported.",
        source="postmark",
        related_local_path="home/tests/testjs.js",
        related_local_script_id=99,
        related_line=6,
        related_column=0,
    )
    panel._apply_diagnostics([row])
    assert panel.diagnostic_count() == 1
    item = panel._list.item(0)
    assert item is not None
    panel._navigate_to_item(item)
    assert opened == [99]

    CodeEditorWidget.set_open_local_script_handler(None)
