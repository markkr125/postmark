"""Accept ESM import path completions in the code editor."""

from __future__ import annotations

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from ui.widgets.code_editor.editor_widget import CodeEditorWidget


def test_accept_esm_import_completion_preserves_closing_quote(
    qapp: QApplication,
    qtbot,
) -> None:
    """Accepting a sibling path replaces the typed prefix and keeps the quote."""
    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    editor.set_language("javascript")
    editor._completion_engine._local_script_id = 1
    editor.setPlainText("import { x } from './ma")
    cur = editor.textCursor()
    cur.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cur)
    editor._accept_completion("./mapper.js", "module")
    assert editor.toPlainText() == "import { x } from './mapper.js"
