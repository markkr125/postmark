"""Tests for the VariablePopup hover widget."""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QWidget

from services.environment_service import VariableDetail
from ui.widgets.variable_popup import VariablePopup


class TestVariablePopupLocalOverride:
    """Tests for per-request local override behaviour on close."""

    def test_close_with_changed_value_emits_local_override(self, qapp: QApplication, qtbot) -> None:
        """Closing popup with edited value calls the local override callback."""
        callback = MagicMock()
        VariablePopup.set_local_override_callback(lambda *a: callback(*a))
        try:
            parent = QWidget()
            qtbot.addWidget(parent)
            parent.show()

            detail: VariableDetail = {
                "value": "original",
                "source": "collection",
                "source_id": 1,
            }
            VariablePopup.show_variable("my_var", detail, QPoint(100, 100), parent)
            popup = VariablePopup._instance
            assert popup is not None

            popup._value_input.setText("modified")
            popup.close()

            callback.assert_called_once_with("my_var", "modified", "collection", 1)
        finally:
            VariablePopup.set_local_override_callback(None)

    def test_close_without_change_does_not_emit(self, qapp: QApplication, qtbot) -> None:
        """Closing popup without editing does not call local override callback."""
        callback = MagicMock()
        VariablePopup.set_local_override_callback(lambda *a: callback(*a))
        try:
            parent = QWidget()
            qtbot.addWidget(parent)
            parent.show()

            detail: VariableDetail = {
                "value": "original",
                "source": "collection",
                "source_id": 1,
            }
            VariablePopup.show_variable("my_var", detail, QPoint(100, 100), parent)
            popup = VariablePopup._instance
            assert popup is not None
            popup.close()

            callback.assert_not_called()
        finally:
            VariablePopup.set_local_override_callback(None)

    def test_update_click_does_not_emit_local_override(self, qapp: QApplication, qtbot) -> None:
        """Clicking Update persists globally and does not emit local override."""
        local_cb = MagicMock()
        save_cb = MagicMock()
        VariablePopup.set_local_override_callback(lambda *a: local_cb(*a))
        VariablePopup.set_save_callback(lambda *a: save_cb(*a))
        try:
            parent = QWidget()
            qtbot.addWidget(parent)
            parent.show()

            detail: VariableDetail = {
                "value": "original",
                "source": "collection",
                "source_id": 42,
            }
            VariablePopup.show_variable("my_var", detail, QPoint(100, 100), parent)
            popup = VariablePopup._instance
            assert popup is not None

            popup._value_input.setText("new-value")
            popup._on_update_clicked()

            # Save callback was invoked (global persist)
            save_cb.assert_called_once_with("my_var", "new-value", "collection", 42)
            # Local override callback should NOT have been called
            local_cb.assert_not_called()
        finally:
            VariablePopup.set_local_override_callback(None)
            VariablePopup.set_save_callback(None)

    def test_close_unresolved_variable_does_not_emit(self, qapp: QApplication, qtbot) -> None:
        """Closing popup for unresolved variable does not emit local override."""
        callback = MagicMock()
        VariablePopup.set_local_override_callback(lambda *a: callback(*a))
        try:
            parent = QWidget()
            qtbot.addWidget(parent)
            parent.show()

            VariablePopup.show_variable("missing", None, QPoint(100, 100), parent)
            popup = VariablePopup._instance
            assert popup is not None
            popup.close()

            callback.assert_not_called()
        finally:
            VariablePopup.set_local_override_callback(None)


class TestVariablePopupLocalDisplay:
    """Tests for locally-overridden variable display."""

    def test_local_badge_shown_for_local_override(self, qapp: QApplication, qtbot) -> None:
        """A variable with is_local=True shows a 'Local' badge."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        detail: VariableDetail = {
            "value": "overridden",
            "source": "collection",
            "source_id": 1,
            "is_local": True,
        }
        popup._populate("var", detail)
        assert popup._source_badge.text() == "Local"
        assert popup._source_badge.property("varSource") == "local"

    def test_local_override_buttons_visible_immediately(self, qapp: QApplication, qtbot) -> None:
        """Update and Reset buttons are visible right away for local overrides."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        detail: VariableDetail = {
            "value": "overridden",
            "source": "collection",
            "source_id": 1,
            "is_local": True,
        }
        popup._populate("var", detail)
        assert not popup._update_btn.isHidden()
        assert not popup._reset_btn.isHidden()

    def test_local_override_buttons_stay_on_edit(self, qapp: QApplication, qtbot) -> None:
        """Editing the text does not hide buttons for a local override."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        detail: VariableDetail = {
            "value": "overridden",
            "source": "collection",
            "source_id": 1,
            "is_local": True,
        }
        popup._populate("var", detail)
        popup._value_input.setText("changed-again")
        assert not popup._update_btn.isHidden()
        assert not popup._reset_btn.isHidden()

    def test_local_update_uses_original_source(self, qapp: QApplication, qtbot) -> None:
        """Clicking Update on a local override persists to the original source."""
        callback = MagicMock()
        VariablePopup.set_save_callback(lambda *a: callback(*a))
        try:
            popup = VariablePopup()
            qtbot.addWidget(popup)
            detail: VariableDetail = {
                "value": "overridden",
                "source": "collection",
                "source_id": 42,
                "is_local": True,
            }
            popup._populate("my_var", detail)
            popup._on_update_clicked()
            callback.assert_called_once_with("my_var", "overridden", "collection", 42)
        finally:
            VariablePopup.set_save_callback(None)


class TestVariablePopupResetLocal:
    """Tests for reset behaviour on locally-overridden variables."""

    def test_reset_local_calls_callback(self, qapp: QApplication, qtbot) -> None:
        """Clicking Reset on a local override invokes the reset callback."""
        callback = MagicMock()
        VariablePopup.set_reset_local_override_callback(lambda *a: callback(*a))
        try:
            popup = VariablePopup()
            qtbot.addWidget(popup)
            detail: VariableDetail = {
                "value": "overridden",
                "source": "collection",
                "source_id": 1,
                "is_local": True,
            }
            popup._populate("my_var", detail)
            popup._on_reset_clicked()
            callback.assert_called_once_with("my_var")
        finally:
            VariablePopup.set_reset_local_override_callback(None)

    def test_reset_non_local_reverts_text(self, qapp: QApplication, qtbot) -> None:
        """Clicking Reset on a normal variable reverts the text value."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        detail: VariableDetail = {"value": "original", "source": "collection", "source_id": 1}
        popup._populate("var", detail)
        popup._value_input.setText("modified")
        popup._on_reset_clicked()
        assert popup._value_input.text() == "original"

    def test_reset_local_does_not_emit_local_override(self, qapp: QApplication, qtbot) -> None:
        """After reset on local, closing does not fire the local override callback."""
        local_cb = MagicMock()
        reset_cb = MagicMock()
        VariablePopup.set_local_override_callback(lambda *a: local_cb(*a))
        VariablePopup.set_reset_local_override_callback(lambda *a: reset_cb(*a))
        try:
            parent = QWidget()
            qtbot.addWidget(parent)
            parent.show()
            detail: VariableDetail = {
                "value": "overridden",
                "source": "collection",
                "source_id": 1,
                "is_local": True,
            }
            VariablePopup.show_variable("var", detail, QPoint(100, 100), parent)
            popup = VariablePopup._instance
            assert popup is not None
            popup._on_reset_clicked()
            # Reset callback was invoked; local override callback was not
            reset_cb.assert_called_once_with("var")
            local_cb.assert_not_called()
        finally:
            VariablePopup.set_local_override_callback(None)
            VariablePopup.set_reset_local_override_callback(None)

    def test_set_reset_callback_stores_and_clears(self, qapp: QApplication, qtbot) -> None:
        """set_reset_local_override_callback stores and clears the callable."""

        def _cb(_a: str) -> None:
            pass

        try:
            VariablePopup.set_reset_local_override_callback(_cb)
            assert VariablePopup._reset_local_override_callback is _cb
        finally:
            VariablePopup.set_reset_local_override_callback(None)
        assert VariablePopup._reset_local_override_callback is None


class TestVariablePopupUnresolvedAdd:
    """Tests for adding unresolved variables."""

    def test_unresolved_shows_add_select(self, qapp: QApplication, qtbot) -> None:
        """Unresolved variable shows the 'Add to' select box."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        popup._populate("missing", None)
        assert not popup._add_select.isHidden()
        assert popup._add_panel.isHidden()  # collapsed by default

    def test_select_toggles_panel(self, qapp: QApplication, qtbot) -> None:
        """Clicking the select box expands and collapses the panel."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        popup._populate("missing", None)
        assert popup._add_panel.isHidden()
        popup._toggle_add_panel()
        assert not popup._add_panel.isHidden()
        popup._toggle_add_panel()
        assert popup._add_panel.isHidden()

    def test_targets_disabled_when_empty(self, qapp: QApplication, qtbot) -> None:
        """Target buttons are disabled when value input is empty."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        popup._populate("missing", None)
        assert not popup._target_collection.isEnabled()
        assert not popup._target_environment.isEnabled()

    def test_targets_enabled_when_value_entered(self, qapp: QApplication, qtbot) -> None:
        """Target buttons become enabled when a value is entered."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        popup._populate("missing", None)
        VariablePopup._has_environment = True
        popup._value_input.setText("some-value")
        assert popup._target_collection.isEnabled()
        assert popup._target_environment.isEnabled()
        VariablePopup._has_environment = False

    def test_add_hidden_for_resolved(self, qapp: QApplication, qtbot) -> None:
        """Resolved variables do not show the add-to UI."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        detail: VariableDetail = {"value": "val", "source": "collection", "source_id": 1}
        popup._populate("var", detail)
        assert popup._add_select.isHidden()
        assert popup._add_panel.isHidden()

    def test_panel_has_collection_and_environment(self, qapp: QApplication, qtbot) -> None:
        """Expanded panel shows Collection and Environment targets."""
        popup = VariablePopup()
        qtbot.addWidget(popup)
        popup._populate("missing", None)
        popup._toggle_add_panel()  # expand
        assert popup._target_collection.text().strip().endswith("Collection")
        assert popup._target_environment.text().strip().endswith("Environment")

    def test_add_collection_calls_callback(self, qapp: QApplication, qtbot) -> None:
        """Clicking Collection target invokes the callback."""
        callback = MagicMock()
        VariablePopup.set_add_variable_callback(lambda *a: callback(*a))
        try:
            popup = VariablePopup()
            qtbot.addWidget(popup)
            popup._populate("new_var", None)
            popup._value_input.setText("my-value")
            popup._on_add_target("collection")
            callback.assert_called_once_with("new_var", "my-value", "collection")
        finally:
            VariablePopup.set_add_variable_callback(None)

    def test_add_environment_calls_callback(self, qapp: QApplication, qtbot) -> None:
        """Clicking Environment target invokes the callback."""
        callback = MagicMock()
        VariablePopup.set_add_variable_callback(lambda *a: callback(*a))
        try:
            popup = VariablePopup()
            qtbot.addWidget(popup)
            popup._populate("env_var", None)
            popup._value_input.setText("env-value")
            popup._on_add_target("environment")
            callback.assert_called_once_with("env_var", "env-value", "environment")
        finally:
            VariablePopup.set_add_variable_callback(None)

    def test_add_with_empty_value_does_nothing(self, qapp: QApplication, qtbot) -> None:
        """Clicking a target with empty value does not invoke the callback."""
        callback = MagicMock()
        VariablePopup.set_add_variable_callback(lambda *a: callback(*a))
        try:
            popup = VariablePopup()
            qtbot.addWidget(popup)
            popup._populate("missing", None)
            popup._on_add_target("collection")
            callback.assert_not_called()
        finally:
            VariablePopup.set_add_variable_callback(None)

    def test_no_env_warning_shown_when_no_environment(self, qapp: QApplication, qtbot) -> None:
        """Warning label is visible when no environment is selected."""
        VariablePopup._has_environment = False
        try:
            popup = VariablePopup()
            qtbot.addWidget(popup)
            popup._populate("missing", None)
            popup._toggle_add_panel()  # expand to see warning
            assert not popup._no_env_label.isHidden()
            assert not popup._target_environment.isEnabled()
        finally:
            VariablePopup._has_environment = False

    def test_no_env_warning_hidden_when_environment_selected(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Warning label is hidden when an environment is selected."""
        VariablePopup._has_environment = True
        try:
            popup = VariablePopup()
            qtbot.addWidget(popup)
            popup._populate("missing", None)
            popup._toggle_add_panel()  # expand
            assert popup._no_env_label.isHidden()
            # Env target still disabled until value entered
            popup._value_input.setText("val")
            assert popup._target_environment.isEnabled()
        finally:
            VariablePopup._has_environment = False

    def test_set_has_environment(self, qapp: QApplication, qtbot) -> None:
        """set_has_environment updates the class-level flag."""
        try:
            VariablePopup.set_has_environment(True)
            assert VariablePopup._has_environment is True
            VariablePopup.set_has_environment(False)
            assert VariablePopup._has_environment is False
        finally:
            VariablePopup._has_environment = False

    def test_set_add_variable_callback_stores_and_clears(self, qapp: QApplication, qtbot) -> None:
        """set_add_variable_callback stores and clears the callable."""

        def _cb(_a: str, _b: str, _c: str) -> None:
            pass

        try:
            VariablePopup.set_add_variable_callback(_cb)
            assert VariablePopup._add_variable_callback is _cb
        finally:
            VariablePopup.set_add_variable_callback(None)
        assert VariablePopup._add_variable_callback is None
