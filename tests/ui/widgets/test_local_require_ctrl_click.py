"""Tests for Ctrl+click navigation on ``pm.require('local:…')`` paths."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from database.models.local_scripts.local_script_repository import create_folder, create_script
from services.local_script_service import LocalScriptService
from ui.widgets.code_editor import CodeEditorWidget


def test_local_require_path_range_at_pos_inside_string(qapp: QApplication, qtbot) -> None:
    """Ctrl+hover uses the path span inside the quoted ``local:…`` string."""
    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    source = "const local = pm.require('local:home/tests/testJs.js');\n"
    editor.setPlainText(source)
    path_start = source.index("home/tests")
    path_end = source.index("testJs.js") + len("testJs.js")
    cur = editor.textCursor()
    cur.setPosition(path_start)
    editor.setTextCursor(cur)
    click_pos = editor.cursorRect(cur).center()
    path_range = editor._local_require_path_range_at_pos(click_pos)
    assert path_range == (path_start, path_end)


def test_try_open_local_require_at_offset_inside_string(qapp: QApplication, qtbot) -> None:
    """Offsets inside the quoted ``local:…`` path resolve and open the script tab."""
    home = create_folder("home")
    tests = create_folder("tests", parent_id=home.id)
    script = create_script(tests.id, "testJs.js", language="javascript", content="// dep\n")
    LocalScriptService.invalidate_path_index_cache()

    opened: list[int] = []

    def _handler(script_id: int) -> None:
        opened.append(script_id)

    CodeEditorWidget.set_open_local_script_handler(_handler)
    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    source = "const local = pm.require('local:home/tests/testJs.js');\n"
    editor.setPlainText(source)
    offset = source.index("testJs")
    assert editor._try_open_local_require_at_offset(offset) is True
    assert opened == [script.id]
    CodeEditorWidget.set_open_local_script_handler(None)


def test_ctrl_click_inside_local_path_string_opens_script(qapp: QApplication, qtbot) -> None:
    """Ctrl+click on the path inside quotes opens the script (not blocked by string-literal ident rule)."""
    home = create_folder("home")
    tests = create_folder("tests", parent_id=home.id)
    script = create_script(tests.id, "testJs.js", language="javascript", content="// dep\n")
    LocalScriptService.invalidate_path_index_cache()

    opened: list[int] = []

    def _handler(script_id: int) -> None:
        opened.append(script_id)

    CodeEditorWidget.set_open_local_script_handler(_handler)
    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    source = "const local = pm.require('local:home/tests/testJs.js');\n"
    editor.setPlainText(source)
    editor.set_language("javascript")

    path_offset = source.index("testJs")
    cur = editor.textCursor()
    cur.setPosition(path_offset)
    editor.setTextCursor(cur)
    click_pos = editor.cursorRect(cur).center()

    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(click_pos),
        editor.mapToGlobal(click_pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier,
    )
    editor.mousePressEvent(event)

    assert opened == [script.id]
    CodeEditorWidget.set_open_local_script_handler(None)
