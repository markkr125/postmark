"""Tests for the SettingsDialog."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from ui.dialogs.settings_dialog import SettingsDialog
from ui.theme_manager import (
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
