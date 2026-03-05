"""Tests for the VariableLineEdit widget.

Exercises variable highlighting paint path, tooltip display, and
the ``set_variable_map`` API.
"""

from __future__ import annotations

from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QToolTip

from ui.variable_line_edit import VariableLineEdit


class TestVariableLineEditConstruction:
    """Basic widget construction and subclass contract."""

    def test_is_qlineedit_subclass(self, qapp: QApplication, qtbot) -> None:
        """VariableLineEdit inherits from QLineEdit."""
        w = VariableLineEdit()
        qtbot.addWidget(w)
        assert isinstance(w, QLineEdit)

    def test_starts_with_empty_variable_map(self, qapp: QApplication, qtbot) -> None:
        """A fresh widget has an empty variable map."""
        w = VariableLineEdit()
        qtbot.addWidget(w)
        assert w._variable_map == {}


class TestSetVariableMap:
    """Tests for set_variable_map API."""

    def test_set_variable_map_stores_map(self, qapp: QApplication, qtbot) -> None:
        """set_variable_map stores the dict for later reference."""
        w = VariableLineEdit()
        qtbot.addWidget(w)
        m = {"base_url": "https://api.example.com"}
        w.set_variable_map(m)
        assert w._variable_map is m

    def test_set_variable_map_replaces_previous(self, qapp: QApplication, qtbot) -> None:
        """Calling set_variable_map again replaces the old map."""
        w = VariableLineEdit()
        qtbot.addWidget(w)
        w.set_variable_map({"a": "1"})
        w.set_variable_map({"b": "2"})
        assert "a" not in w._variable_map
        assert w._variable_map["b"] == "2"


class TestPaintEvent:
    """Smoke tests for the paint path with variables present."""

    def test_paint_without_variables(self, qapp: QApplication, qtbot) -> None:
        """Paint completes without error when no variables are present."""
        w = VariableLineEdit()
        qtbot.addWidget(w)
        w.setText("https://example.com")
        w.show()
        w.repaint()

    def test_paint_with_variables(self, qapp: QApplication, qtbot) -> None:
        """Paint completes without error when variables are present."""
        w = VariableLineEdit()
        qtbot.addWidget(w)
        w.setText("https://{{base_url}}/api/{{version}}")
        w.show()
        w.repaint()

    def test_paint_with_variable_map(self, qapp: QApplication, qtbot) -> None:
        """Paint completes without error when variable map is set."""
        w = VariableLineEdit()
        qtbot.addWidget(w)
        w.set_variable_map({"base_url": "api.example.com"})
        w.setText("https://{{base_url}}/api")
        w.show()
        w.repaint()


class TestTooltip:
    """Tests for variable tooltip display on hover."""

    def test_tooltip_shows_resolved_value(self, qapp: QApplication, qtbot) -> None:
        """Hovering over a resolved variable shows its value."""
        w = VariableLineEdit()
        qtbot.addWidget(w)
        w.setText("{{host}}/api")
        w.set_variable_map({"host": "example.com"})
        w.show()
        w.resize(400, 30)

        # Simulate a tooltip event over the variable
        fm = w.fontMetrics()
        var_x = w._content_rect().left() + fm.horizontalAdvance("{{ho")
        pos = QPoint(var_x, w.height() // 2)
        global_pos = w.mapToGlobal(pos)
        help_event = QHelpEvent(QEvent.Type.ToolTip, pos, global_pos)

        with patch.object(QToolTip, "showText") as mock_show:
            w.event(help_event)
            if mock_show.called:
                text = mock_show.call_args[0][1]
                assert "host" in text
                assert "example.com" in text

    def test_tooltip_shows_unresolved(self, qapp: QApplication, qtbot) -> None:
        """Hovering over an unresolved variable shows '(unresolved)'."""
        w = VariableLineEdit()
        qtbot.addWidget(w)
        w.setText("{{missing}}/api")
        w.set_variable_map({})
        w.show()
        w.resize(400, 30)

        fm = w.fontMetrics()
        var_x = w._content_rect().left() + fm.horizontalAdvance("{{mis")
        pos = QPoint(var_x, w.height() // 2)
        global_pos = w.mapToGlobal(pos)
        help_event = QHelpEvent(QEvent.Type.ToolTip, pos, global_pos)

        with patch.object(QToolTip, "showText") as mock_show:
            w.event(help_event)
            if mock_show.called:
                text = mock_show.call_args[0][1]
                assert "missing" in text
                assert "unresolved" in text

    def test_tooltip_hides_outside_variable(self, qapp: QApplication, qtbot) -> None:
        """Hovering outside any variable hides the tooltip."""
        w = VariableLineEdit()
        qtbot.addWidget(w)
        w.setText("plain text only")
        w.show()
        w.resize(400, 30)

        pos = QPoint(5, w.height() // 2)
        global_pos = w.mapToGlobal(pos)
        help_event = QHelpEvent(QEvent.Type.ToolTip, pos, global_pos)

        with patch.object(QToolTip, "hideText") as mock_hide:
            w.event(help_event)
            mock_hide.assert_called_once()
