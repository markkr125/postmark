"""Tests for the VariablePopup hover widget."""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QWidget

from services.environment_service import VariableDetail
from ui.widgets.variable_popup import VariablePopup


class TestVariablePopupConstruction:
    """Basic popup construction and layout."""

    def test_creates_without_error(self, qapp: QApplication, qtbot) -> None:
        """VariablePopup can be constructed."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        assert popup.objectName() == "variablePopup"

    def test_has_name_label(self, qapp: QApplication, qtbot) -> None:
        """Popup contains a variable name label."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        assert popup._name_label is not None

    def test_has_value_input(self, qapp: QApplication, qtbot) -> None:
        """Popup contains an editable value input."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        assert popup._value_input is not None

    def test_has_source_badge(self, qapp: QApplication, qtbot) -> None:
        """Popup contains a source badge label."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        assert popup._source_badge is not None


class TestVariablePopupPopulate:
    """Tests for popup content population."""

    def test_populate_resolved_variable(self, qapp: QApplication, qtbot) -> None:
        """Resolved variable shows name, value and source."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        detail: VariableDetail = {
            "value": "https://api.example.com",
            "source": "collection",
            "source_id": 1,
        }
        popup._populate("base_url", detail)
        assert popup._name_label.text() == "base_url"
        assert popup._value_input.text() == "https://api.example.com"
        assert popup._source_badge.text() == "Collection"

    def test_populate_environment_source(self, qapp: QApplication, qtbot) -> None:
        """Environment source shows capitalised badge text."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        detail: VariableDetail = {"value": "secret123", "source": "environment", "source_id": 10}
        popup._populate("api_key", detail)
        assert popup._source_badge.text() == "Environment"

    def test_populate_unresolved_variable(self, qapp: QApplication, qtbot) -> None:
        """Unresolved variable shows name and 'Unresolved' badge."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        popup._populate("missing_var", None)
        assert popup._name_label.text() == "missing_var"
        assert popup._value_input.text() == ""
        assert popup._source_badge.text() == "Unresolved"


class TestVariablePopupShowHide:
    """Tests for popup show/hide behaviour."""

    def test_show_variable_creates_and_shows(self, qapp: QApplication, qtbot) -> None:
        """show_variable displays the popup at the given position."""
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()

        detail: VariableDetail = {"value": "val", "source": "collection", "source_id": 1}
        VariablePopup.show_variable("var", detail, QPoint(100, 100), parent)
        assert VariablePopup._instance is not None
        assert VariablePopup._instance.isVisible()
        VariablePopup._instance.close()

    def test_hide_popup_closes_instance(self, qapp: QApplication, qtbot) -> None:
        """hide_popup closes the singleton instance."""
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()

        detail: VariableDetail = {"value": "val", "source": "collection", "source_id": 1}
        VariablePopup.show_variable("var", detail, QPoint(100, 100), parent)
        assert VariablePopup._instance is not None
        VariablePopup.hide_popup()
        assert VariablePopup._instance is None

    def test_show_variable_replaces_previous(self, qapp: QApplication, qtbot) -> None:
        """Calling show_variable again replaces the previous popup."""
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()

        VariablePopup.show_variable(
            "a", {"value": "1", "source": "collection", "source_id": 1}, QPoint(100, 100), parent
        )
        first = VariablePopup._instance
        VariablePopup.show_variable(
            "b", {"value": "2", "source": "environment", "source_id": 10}, QPoint(200, 200), parent
        )
        assert VariablePopup._instance is not first
        assert VariablePopup._instance is not None
        assert VariablePopup._instance._name_label.text() == "b"
        VariablePopup._instance.close()

    def test_hide_popup_noop_when_none(self, qapp: QApplication, qtbot) -> None:
        """hide_popup does not raise when no popup is active."""
        VariablePopup._instance = None
        VariablePopup.hide_popup()  # Should not raise


class TestVariablePopupEditing:
    """Tests for editable value input and action buttons."""

    def test_resolved_variable_is_editable(self, qapp: QApplication, qtbot) -> None:
        """Resolved variable value input is not read-only."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        detail: VariableDetail = {"value": "val", "source": "collection", "source_id": 1}
        popup._populate("var", detail)
        assert not popup._value_input.isReadOnly()

    def test_unresolved_variable_is_editable(self, qapp: QApplication, qtbot) -> None:
        """Unresolved variable value input is editable for adding."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        popup._populate("missing", None)
        assert not popup._value_input.isReadOnly()

    def test_buttons_hidden_initially(self, qapp: QApplication, qtbot) -> None:
        """Update and Reset buttons are hidden after populate."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        detail: VariableDetail = {"value": "val", "source": "collection", "source_id": 1}
        popup._populate("var", detail)
        assert popup._update_btn.isHidden()
        assert popup._reset_btn.isHidden()

    def test_buttons_appear_on_value_change(self, qapp: QApplication, qtbot) -> None:
        """Update and Reset buttons appear when the value diverges."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        detail: VariableDetail = {"value": "original", "source": "collection", "source_id": 1}
        popup._populate("var", detail)
        popup._value_input.setText("modified")
        assert not popup._update_btn.isHidden()
        assert not popup._reset_btn.isHidden()

    def test_buttons_hidden_when_value_restored(self, qapp: QApplication, qtbot) -> None:
        """Buttons disappear when the value is restored to original."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        detail: VariableDetail = {"value": "original", "source": "collection", "source_id": 1}
        popup._populate("var", detail)
        popup._value_input.setText("modified")
        assert not popup._update_btn.isHidden()
        popup._value_input.setText("original")
        assert popup._update_btn.isHidden()
        assert popup._reset_btn.isHidden()

    def test_reset_restores_original_value(self, qapp: QApplication, qtbot) -> None:
        """Clicking Reset reverts the value input to the original."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        detail: VariableDetail = {"value": "original", "source": "collection", "source_id": 1}
        popup._populate("var", detail)
        popup._value_input.setText("modified")
        popup._on_reset_clicked()
        assert popup._value_input.text() == "original"

    def test_update_calls_save_callback(self, qapp: QApplication, qtbot) -> None:
        """Clicking Update invokes the save callback with correct args."""
        callback = MagicMock()
        popup = VariablePopup()
        qtbot.addWidget(popup)
        # Set callback AFTER construction to avoid PySide6/shiboken
        # segfault when a MagicMock is stored as a QWidget class attr.
        VariablePopup.set_save_callback(lambda *a: callback(*a))
        try:
            detail: VariableDetail = {
                "value": "original",
                "source": "collection",
                "source_id": 42,
            }
            popup._populate("my_var", detail)
            popup._value_input.setText("new-value")
            popup._on_update_clicked()
            callback.assert_called_once_with("my_var", "new-value", "collection", 42)
        finally:
            VariablePopup.set_save_callback(None)

    def test_update_without_callback_does_not_raise(self, qapp: QApplication, qtbot) -> None:
        """Clicking Update with no callback set does not raise."""
        VariablePopup.set_save_callback(None)
        popup = VariablePopup()
        qtbot.addWidget(popup)
        detail: VariableDetail = {"value": "val", "source": "collection", "source_id": 1}
        popup._populate("var", detail)
        popup._value_input.setText("changed")
        popup._on_update_clicked()  # Should not raise


class TestVariablePopupClassMethods:
    """Tests for class-level configuration helpers."""

    def test_hover_delay_ms_positive(self, qapp: QApplication, qtbot) -> None:
        """hover_delay_ms returns a positive integer."""
        assert VariablePopup.hover_delay_ms() > 0

    def test_set_save_callback_stores_callable(self, qapp: QApplication, qtbot) -> None:
        """set_save_callback stores the provided callable on the class."""

        def _cb(_a: str, _b: str, _c: str, _d: int) -> None:
            pass

        try:
            VariablePopup.set_save_callback(_cb)
            assert VariablePopup._save_callback is _cb
        finally:
            VariablePopup.set_save_callback(None)

    def test_set_save_callback_none_clears(self, qapp: QApplication, qtbot) -> None:
        """Passing None clears the callback."""
        VariablePopup.set_save_callback(lambda *a: None)
        VariablePopup.set_save_callback(None)
        assert VariablePopup._save_callback is None

    def test_set_local_override_callback_stores_callable(self, qapp: QApplication, qtbot) -> None:
        """set_local_override_callback stores the provided callable."""

        def _cb(_a: str, _b: str, _c: str, _d: int) -> None:
            pass

        try:
            VariablePopup.set_local_override_callback(_cb)
            assert VariablePopup._local_override_callback is _cb
        finally:
            VariablePopup.set_local_override_callback(None)

    def test_set_local_override_callback_none_clears(self, qapp: QApplication, qtbot) -> None:
        """Passing None clears the local override callback."""
        VariablePopup.set_local_override_callback(lambda *a: None)
        VariablePopup.set_local_override_callback(None)
        assert VariablePopup._local_override_callback is None
