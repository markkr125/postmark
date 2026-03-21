"""Tests for the SettingsDialog."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from ui.dialogs.settings_dialog import SettingsDialog
from ui.styling.tab_settings_manager import (
    ACTIVATE_MRU,
    LIMIT_CLOSE_UNUSED,
    WRAP_SINGLE_ROW,
    TabSettingsManager,
)
from ui.styling.theme_manager import (
    _APP,
    _ORG,
    SCHEME_AUTO,
    SCHEME_DARK,
    SCHEME_LIGHT,
    STYLE_FUSION,
    STYLE_NATIVE,
    ThemeManager,
)


@pytest.fixture(autouse=True)
def _clear_theme_settings() -> None:
    """Clear persisted theme QSettings before each test."""
    settings = QSettings(_ORG, _APP)
    settings.remove("theme")
    settings.remove("tabs")
    settings.sync()


class TestSettingsDialogConstruction:
    """Tests for SettingsDialog initialisation."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """SettingsDialog can be instantiated without errors."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "Settings"

    def test_has_category_list(self, qapp: QApplication, qtbot) -> None:
        """SettingsDialog has a category list with at least one entry."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog._cat_list.count() >= 1

    def test_appearance_category_exists(self, qapp: QApplication, qtbot) -> None:
        """The first category is 'Appearance'."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog._cat_list.item(0).text() == "Appearance"

    def test_tabs_category_exists(self, qapp: QApplication, qtbot) -> None:
        """The second category is 'Tabs'."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog._cat_list.item(1).text() == "Tabs"


class TestSettingsDialogCombos:
    """Tests for the combo box contents and defaults."""

    def test_style_combo_has_entries(self, qapp: QApplication, qtbot) -> None:
        """Style combo box has at least two entries (Fusion, Native)."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog._style_combo.count() >= 2

    def test_style_combo_data_values(self, qapp: QApplication, qtbot) -> None:
        """Style combo items carry correct userData."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        data = [dialog._style_combo.itemData(i) for i in range(dialog._style_combo.count())]
        assert STYLE_FUSION in data
        assert STYLE_NATIVE in data

    def test_scheme_combo_has_entries(self, qapp: QApplication, qtbot) -> None:
        """Scheme combo box has three entries (Auto, Light, Dark)."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog._scheme_combo.count() == 3

    def test_scheme_combo_data_values(self, qapp: QApplication, qtbot) -> None:
        """Scheme combo items carry correct userData."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        data = [dialog._scheme_combo.itemData(i) for i in range(dialog._scheme_combo.count())]
        assert SCHEME_AUTO in data
        assert SCHEME_LIGHT in data
        assert SCHEME_DARK in data

    def test_default_style_selected(self, qapp: QApplication, qtbot) -> None:
        """Default style combo selection matches the ThemeManager default."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog._style_combo.currentData() == STYLE_FUSION

    def test_default_scheme_selected(self, qapp: QApplication, qtbot) -> None:
        """Default scheme combo selection matches the ThemeManager default."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog._scheme_combo.currentData() == SCHEME_AUTO


class TestSettingsDialogApply:
    """Tests for pressing the Apply button."""

    def test_apply_updates_style(self, qapp: QApplication, qtbot) -> None:
        """Selecting Native and applying changes the ThemeManager style."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)

        # Select Native style
        for i in range(dialog._style_combo.count()):
            if dialog._style_combo.itemData(i) == STYLE_NATIVE:
                dialog._style_combo.setCurrentIndex(i)
                break

        dialog._on_apply()
        assert tm.style == STYLE_NATIVE

    def test_apply_updates_scheme(self, qapp: QApplication, qtbot) -> None:
        """Selecting Dark and applying changes the ThemeManager scheme."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)

        # Select Dark scheme
        for i in range(dialog._scheme_combo.count()):
            if dialog._scheme_combo.itemData(i) == SCHEME_DARK:
                dialog._scheme_combo.setCurrentIndex(i)
                break

        dialog._on_apply()
        assert tm.scheme == SCHEME_DARK

    def test_apply_emits_theme_changed(self, qapp: QApplication, qtbot) -> None:
        """Applying settings emits theme_changed on the ThemeManager."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)

        with qtbot.waitSignal(tm.theme_changed, timeout=1000):
            dialog._on_apply()

    def test_combo_reflects_theme_manager_state(self, qapp: QApplication, qtbot) -> None:
        """Opening dialog with non-default state shows correct selections."""
        tm = ThemeManager(qapp)
        tm.style = STYLE_NATIVE
        tm.scheme = SCHEME_DARK

        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)

        assert dialog._style_combo.currentData() == STYLE_NATIVE
        assert dialog._scheme_combo.currentData() == SCHEME_DARK

    def test_apply_updates_tab_settings(self, qapp: QApplication, qtbot) -> None:
        """Applying the Tabs page persists the tab preferences."""
        tm = ThemeManager(qapp)
        tab_settings = TabSettingsManager(qapp)
        dialog = SettingsDialog(tm, tab_settings)
        qtbot.addWidget(dialog)

        dialog._small_labels_check.setChecked(False)
        dialog._preview_tab_check.setChecked(False)
        dialog._wrap_mode_combo.setCurrentIndex(1)
        dialog._tab_limit_spin.setValue(42)
        dialog._tab_limit_policy_combo.setCurrentIndex(1)
        dialog._activate_on_close_combo.setCurrentIndex(2)

        dialog._on_apply()

        assert not tab_settings.small_labels
        assert not tab_settings.enable_preview_tab
        assert tab_settings.wrap_mode == WRAP_SINGLE_ROW
        assert tab_settings.tab_limit == 42
        assert tab_settings.tab_limit_policy == LIMIT_CLOSE_UNUSED
        assert tab_settings.activate_on_close == ACTIVATE_MRU

    def test_tabs_page_reflects_existing_settings(self, qapp: QApplication, qtbot) -> None:
        """Opening the dialog reflects persisted tab settings."""
        tm = ThemeManager(qapp)
        tab_settings = TabSettingsManager(qapp)
        tab_settings.small_labels = False
        tab_settings.show_path_for_duplicates = False
        tab_settings.enable_preview_tab = False
        tab_settings.wrap_mode = WRAP_SINGLE_ROW
        tab_settings.tab_limit = 55

        dialog = SettingsDialog(tm, tab_settings)
        qtbot.addWidget(dialog)

        assert not dialog._small_labels_check.isChecked()
        assert not dialog._show_path_duplicates_check.isChecked()
        assert not dialog._preview_tab_check.isChecked()
        assert dialog._wrap_mode_combo.currentData() == WRAP_SINGLE_ROW
        assert dialog._tab_limit_spin.value() == 55
