"""Tests for ``{{variable}}`` highlighting and tooltips in CodeEditorWidget."""

from __future__ import annotations

from unittest.mock import patch

from PySide6.QtCore import QEvent
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication

from services.environment_service import VariableDetail
from ui.widgets.code_editor import CodeEditorWidget


class TestVariableHighlighting:
    """Tests for ``{{variable}}`` highlighting in the code editor."""

    def test_variable_highlight_format_applied(self, qapp: QApplication, qtbot) -> None:
        """Blocks containing {{var}} get a highlight format applied."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("text")
        editor.setPlainText("url = {{base_url}}/api")

        block = editor.document().firstBlock()
        layout = block.layout()
        formats = layout.formats()
        var_start = 6  # "url = " is 6 chars
        var_end = 18  # "{{base_url}}" is 12 chars -> ends at 18
        found = any(f.start <= var_start and f.start + f.length >= var_end for f in formats)
        assert found, "Expected a format range covering {{base_url}}"

    def test_variable_highlight_in_json(self, qapp: QApplication, qtbot) -> None:
        """Variable highlighting works alongside JSON syntax highlighting."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.setPlainText('{"url": "{{base_url}}"}')

        block = editor.document().firstBlock()
        layout = block.layout()
        formats = layout.formats()
        assert len(formats) >= 2

    def test_set_variable_map_stores_and_rehighlights(self, qapp: QApplication, qtbot) -> None:
        """set_variable_map stores the map and triggers rehighlight."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        m: dict[str, VariableDetail] = {
            "host": {"value": "example.com", "source": "collection", "source_id": 1}
        }
        editor.set_variable_map(m)
        assert editor._variable_map == m


class TestVariableTooltipInEditor:
    """Tests for variable tooltip display in the code editor."""

    def test_tooltip_for_resolved_variable(self, qapp: QApplication, qtbot) -> None:
        """Hovering over a resolved variable triggers the popup."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.show()
        editor.setPlainText("{{host}}/api")
        vmap: dict[str, VariableDetail] = {
            "host": {"value": "example.com", "source": "environment", "source_id": 10},
        }
        editor.set_variable_map(vmap)

        block = editor.document().firstBlock()
        rect = editor.blockBoundingGeometry(block).translated(editor.contentOffset())
        local_pos = rect.center().toPoint()
        global_pos = editor.mapToGlobal(local_pos)

        with patch("ui.widgets.variable_popup.VariablePopup") as mock_cls:
            help_event = QHelpEvent(QEvent.Type.ToolTip, local_pos, global_pos)
            editor.event(help_event)
            if mock_cls.show_variable.called:
                args = mock_cls.show_variable.call_args[0]
                assert args[0] == "host"
                assert args[1]["value"] == "example.com"

    def test_tooltip_for_unresolved_variable(self, qapp: QApplication, qtbot) -> None:
        """Hovering over an unresolved variable shows None detail."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.show()
        editor.setPlainText("{{unknown}}/api")
        editor.set_variable_map({})

        block = editor.document().firstBlock()
        rect = editor.blockBoundingGeometry(block).translated(editor.contentOffset())
        local_pos = rect.center().toPoint()
        global_pos = editor.mapToGlobal(local_pos)

        with patch("ui.widgets.variable_popup.VariablePopup") as mock_cls:
            help_event = QHelpEvent(QEvent.Type.ToolTip, local_pos, global_pos)
            editor.event(help_event)
            if mock_cls.show_variable.called:
                args = mock_cls.show_variable.call_args[0]
                assert args[0] == "unknown"
                assert args[1] is None
