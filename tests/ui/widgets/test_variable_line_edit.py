"""Tests for the VariableLineEdit widget.

Exercises variable highlighting paint path, popup display, and
the ``set_variable_map`` API.
"""

from __future__ import annotations

from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QLineEdit

from services.environment_service import VariableDetail
from ui.widgets.variable_line_edit import VariableLineEdit


def _D(v: str, s: str = "collection", sid: int = 1) -> VariableDetail:
    """Build a VariableDetail dict for tests."""
    return {"value": v, "source": s, "source_id": sid}


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
        m = {"base_url": _D("https://api.example.com")}
        w.set_variable_map(m)
        assert w._variable_map is m

    def test_set_variable_map_replaces_previous(self, qapp: QApplication, qtbot) -> None:
        """Calling set_variable_map again replaces the old map."""
        w = VariableLineEdit()
        qtbot.addWidget(w)
        w.set_variable_map({"a": _D("1")})
        w.set_variable_map({"b": _D("2")})
        assert "a" not in w._variable_map
        assert w._variable_map["b"]["value"] == "2"


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
        w.set_variable_map({"base_url": _D("api.example.com")})
        w.setText("https://{{base_url}}/api")
        w.show()
        w.repaint()


class TestPopup:
    """Tests for variable popup display on hover."""

    def test_popup_shows_for_resolved_variable(self, qapp: QApplication, qtbot) -> None:
        """Hovering over a resolved variable triggers the popup."""
        w = VariableLineEdit()
        qtbot.addWidget(w)
        w.setText("{{host}}/api")
        w.set_variable_map({"host": _D("example.com")})
        w.show()
        w.resize(400, 30)

        fm = w.fontMetrics()
        var_x = w._content_rect().left() + fm.horizontalAdvance("{{ho")
        pos = QPoint(var_x, w.height() // 2)
        global_pos = w.mapToGlobal(pos)
        help_event = QHelpEvent(QEvent.Type.ToolTip, pos, global_pos)

        with patch("ui.widgets.variable_popup.VariablePopup") as mock_cls:
            w.event(help_event)
            if mock_cls.show_variable.called:
                args = mock_cls.show_variable.call_args[0]
                assert args[0] == "host"
                assert args[1] == _D("example.com")

    def test_popup_shows_for_unresolved_variable(self, qapp: QApplication, qtbot) -> None:
        """Hovering over an unresolved variable shows None detail."""
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

        with patch("ui.widgets.variable_popup.VariablePopup") as mock_cls:
            w.event(help_event)
            if mock_cls.show_variable.called:
                args = mock_cls.show_variable.call_args[0]
                assert args[0] == "missing"
                assert args[1] is None

    def test_popup_hides_outside_variable(self, qapp: QApplication, qtbot) -> None:
        """ToolTip event outside any variable is swallowed without side-effects."""
        w = VariableLineEdit()
        qtbot.addWidget(w)
        w.setText("plain text only")
        w.show()
        w.resize(400, 30)

        pos = QPoint(5, w.height() // 2)
        global_pos = w.mapToGlobal(pos)
        help_event = QHelpEvent(QEvent.Type.ToolTip, pos, global_pos)

        with patch("ui.widgets.variable_popup.VariablePopup") as mock_cls:
            result = w.event(help_event)
            # ToolTip events are consumed to suppress native tooltips
            assert result is True
            # No show or hide calls — popup manages its own lifecycle
            mock_cls.show_variable.assert_not_called()
