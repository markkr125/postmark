"""Tests for the SettingsDialog."""

from __future__ import annotations

import sys
from collections.abc import Generator

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from ui.dialogs.settings_dialog import SettingsDialog
from ui.styling.history_settings_manager import HistorySettingsManager
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
def _clear_theme_settings() -> Generator[None, None, None]:
    """Clear persisted QSettings so tests do not leak to other test modules.

    A Scripting test may persist a fake ``scripting/deno_path``; the last test
    in this file has no *following* per-test pre-hook, so we also clear on
    teardown. Otherwise the next file sees an invalid custom path and script
    runtimes (e.g. Deno debug) can misbehave in the same session.
    """
    settings = QSettings(_ORG, _APP)
    settings.remove("theme")
    settings.remove("tabs")
    settings.remove("scripting")
    settings.remove("history")
    settings.sync()
    yield
    settings = QSettings(_ORG, _APP)
    settings.remove("theme")
    settings.remove("tabs")
    settings.remove("scripting")
    settings.remove("history")
    settings.sync()


class TestSettingsDialogConstruction:
    """Tests for SettingsDialog initialisation."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """SettingsDialog can be instantiated without errors."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "Settings"

    def test_has_category_tree(self, qapp: QApplication, qtbot) -> None:
        """SettingsDialog has a category tree with at least one top-level node."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog._cat_tree.topLevelItemCount() >= 1

    def test_initial_category_scripting(self, qapp: QApplication, qtbot) -> None:
        """``initial_category=Scripting`` selects the Scripting node + its stack page."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm, initial_category="Scripting")
        qtbot.addWidget(dialog)
        current = dialog._cat_tree.currentItem()
        assert current is not None and current.text(0) == "Scripting"
        assert dialog._stack.currentIndex() == dialog._page_indices["scripting"]

    def test_initial_category_pypi_selects_under_private_packages(
        self, qapp: QApplication, qtbot
    ) -> None:
        """``initial_category=PyPI`` drills into the Private packages branch."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm, initial_category="PyPI")
        qtbot.addWidget(dialog)
        current = dialog._cat_tree.currentItem()
        assert current is not None and current.text(0) == "PyPI"
        assert dialog._stack.currentIndex() == dialog._page_indices["private_pypi"]

    def test_top_level_categories_present(self, qapp: QApplication, qtbot) -> None:
        """Tree has Appearance / Tabs / Scripting / Private packages at top level."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        labels = [
            dialog._cat_tree.topLevelItem(i).text(0)
            for i in range(dialog._cat_tree.topLevelItemCount())
        ]
        assert labels == ["Appearance", "Tabs", "Scripting", "History", "Private packages"]

    def test_private_packages_has_provider_children(self, qapp: QApplication, qtbot) -> None:
        """Private packages has npm / JSR / PyPI children."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        private_parent = None
        for i in range(dialog._cat_tree.topLevelItemCount()):
            top = dialog._cat_tree.topLevelItem(i)
            if top.text(0) == "Private packages":
                private_parent = top
                break
        assert private_parent is not None
        children = [private_parent.child(i).text(0) for i in range(private_parent.childCount())]
        assert children == ["npm", "JSR", "PyPI"]


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

    def test_apply_emits_theme_changed_when_style_changes(self, qapp: QApplication, qtbot) -> None:
        """Applying settings emits theme_changed when the style actually changes.

        Apply is a no-op for the theme when nothing changed (otherwise
        ``ThemeManager.apply()`` re-applies the global QSS and clobbers
        per-widget overrides — e.g. the tab bar's ``small_labels`` font).
        """
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)

        # Flip the style combo so apply actually has work to do.
        target_idx = 0 if dialog._style_combo.currentIndex() != 0 else 1
        dialog._style_combo.setCurrentIndex(target_idx)

        with qtbot.waitSignal(tm.theme_changed, timeout=1000):
            dialog._on_apply()

    def test_apply_is_noop_when_nothing_changed(self, qapp: QApplication, qtbot) -> None:
        """No theme reflow when neither style nor scheme actually changed."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)

        fired = [False]

        def _on_changed() -> None:
            fired[0] = True

        tm.theme_changed.connect(_on_changed)
        dialog._on_apply()
        assert not fired[0], "theme_changed should not fire when nothing changed"

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


class TestSettingsDialogScripting:
    """Tests for the Scripting settings page."""

    def test_auto_save_default_checkbox_exists(self, qapp: QApplication, qtbot) -> None:
        """Scripting page has an auto-save default checkbox."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert hasattr(dialog, "_auto_save_default_check")
        assert dialog._auto_save_default_check.isChecked()

    def test_auto_save_default_persists(self, qapp: QApplication, qtbot) -> None:
        """Applying with auto-save unchecked persists the setting."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)

        dialog._auto_save_default_check.setChecked(False)
        dialog._on_apply()

        settings = QSettings(_ORG, _APP)
        raw = settings.value("scripting/auto_save_default")
        assert not raw

    def test_auto_save_default_reflects_existing(self, qapp: QApplication, qtbot) -> None:
        """Opening the dialog reflects a previously persisted auto-save default."""
        settings = QSettings(_ORG, _APP)
        settings.setValue("scripting/auto_save_default", False)

        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert not dialog._auto_save_default_check.isChecked()

    def test_runtime_path_widgets_exist(self, qapp: QApplication, qtbot) -> None:
        """Scripting page has Deno and Python path line edits and actions."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert hasattr(dialog, "_deno_path_edit")
        assert hasattr(dialog, "_python_path_edit")
        assert hasattr(dialog, "_deno_autodetect_btn")
        assert hasattr(dialog, "_deno_download_btn")
        assert hasattr(dialog, "_python_reset_btn")

    def test_deno_autodetect_clears_path(self, qapp: QApplication, qtbot) -> None:
        """Auto-detect clears the custom Deno line edit (Apply persists the clear)."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        dialog._deno_path_edit.setText("/opt/deno")
        dialog._on_deno_autodetect()
        assert not dialog._deno_path_edit.text().strip()

    def test_apply_persists_custom_runtime_paths(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Apply stores scripting/deno_path and scripting/python_path."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)

        d_path = f"{sys.prefix}/fake-deno"
        py_path = f"{sys.prefix}/fake-python"
        dialog._deno_path_edit.setText(d_path)
        dialog._python_path_edit.setText(py_path)
        dialog._on_apply()
        s = QSettings(_ORG, _APP)
        assert s.value("scripting/deno_path", "") in (d_path, str(d_path))
        assert s.value("scripting/python_path", "") in (py_path, str(py_path))

    def test_apply_persists_lsp_enabled(self, qapp: QApplication, qtbot) -> None:
        """Apply persists scripting/lsp_enabled via RuntimeSettings."""
        from services.scripting.runtime_settings import RuntimeSettings

        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        dialog._lsp_enabled_check.setChecked(False)
        dialog._on_apply()
        assert RuntimeSettings.lsp_enabled() is False
        dialog._lsp_enabled_check.setChecked(True)
        dialog._on_apply()
        assert RuntimeSettings.lsp_enabled() is True


class TestSettingsDialogHistory:
    """Request history retention settings."""

    def test_history_page_widgets_exist(self, qapp: QApplication, qtbot) -> None:
        """History page exposes retention controls."""
        tm = ThemeManager(qapp)
        hm = HistorySettingsManager()
        dialog = SettingsDialog(tm, history_settings_manager=hm)
        qtbot.addWidget(dialog)
        w = dialog._history_widgets
        assert w is not None
        assert w.retention_days_spin is not None
        assert w.unlimited_check is not None
        assert w.max_mib_spin is not None

    def test_apply_persists_history_settings(self, qapp: QApplication, qtbot) -> None:
        """Apply writes history/* QSettings keys."""
        tm = ThemeManager(qapp)
        hm = HistorySettingsManager()
        dialog = SettingsDialog(tm, history_settings_manager=hm)
        qtbot.addWidget(dialog)
        w = dialog._history_widgets
        assert w is not None
        w.retention_days_spin.setValue(14)
        w.unlimited_check.setChecked(True)
        w.max_mib_spin.setValue(2)
        dialog._on_apply()
        assert hm.retention_days == 14
        assert hm.unlimited_per_day is True
        assert hm.max_response_bytes == 2 * 1024 * 1024

    def test_unlimited_toggle_disables_max_items_spin(self, qapp: QApplication, qtbot) -> None:
        """Unlimited per day disables the per-day cap spin."""
        tm = ThemeManager(qapp)
        hm = HistorySettingsManager()
        dialog = SettingsDialog(tm, history_settings_manager=hm)
        qtbot.addWidget(dialog)
        w = dialog._history_widgets
        assert w is not None
        w.unlimited_check.setChecked(True)
        w.unlimited_check.toggled.emit(True)
        assert w.max_items_spin.isEnabled() is False

    def test_max_mib_minimum_on_apply(self, qapp: QApplication, qtbot) -> None:
        """Apply stores at least 1 MiB for max response body size."""
        tm = ThemeManager(qapp)
        hm = HistorySettingsManager()
        dialog = SettingsDialog(tm, history_settings_manager=hm)
        qtbot.addWidget(dialog)
        w = dialog._history_widgets
        assert w is not None
        w.max_mib_spin.setValue(1)
        dialog._on_apply()
        assert hm.max_response_bytes >= 1024 * 1024


class TestSettingsDialogPrivatePackages:
    """Private package registries: table, default-npm, PyPI."""

    def test_section_widgets_exist(self, qapp: QApplication, qtbot) -> None:
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog._npm_table is not None
        assert dialog._jsr_table is not None
        assert dialog._default_npm_edit is not None
        assert dialog._pypi_table is not None
        assert dialog._secret_backend_label is not None

    def test_npm_table_reflects_existing_entries(self, qapp: QApplication, qtbot) -> None:
        """An ``npm`` entry shows up on the npm page, not the JSR page."""
        from services.scripting.runtime_settings import RuntimeSettings

        RuntimeSettings.set_registries(
            [
                {
                    "id": "row-existing",
                    "scope": "@mycompany",
                    "url": "https://npm.mycorp.io/",
                    "kind": "npm",
                    "auth_kind": "token",
                    "auth_ref": "registry:row-existing",
                }
            ]
        )
        try:
            tm = ThemeManager(qapp)
            dialog = SettingsDialog(tm)
            qtbot.addWidget(dialog)
            assert dialog._npm_table.rowCount() == 1
            assert dialog._jsr_table.rowCount() == 0
            assert dialog._npm_table.item(0, 0).text() == "@mycompany"
            assert dialog._npm_table.item(0, 1).text() == "https://npm.mycorp.io/"
        finally:
            RuntimeSettings.set_registries([])

    def test_jsr_table_reflects_existing_entries(self, qapp: QApplication, qtbot) -> None:
        """A ``jsr`` entry shows up on the JSR page, not the npm page."""
        from services.scripting.runtime_settings import RuntimeSettings

        RuntimeSettings.set_registries(
            [
                {
                    "id": "row-jsr",
                    "scope": "@std",
                    "url": "https://jsr.mycorp.io/",
                    "kind": "jsr",
                    "auth_kind": "none",
                    "auth_ref": "",
                }
            ]
        )
        try:
            tm = ThemeManager(qapp)
            dialog = SettingsDialog(tm)
            qtbot.addWidget(dialog)
            assert dialog._jsr_table.rowCount() == 1
            assert dialog._npm_table.rowCount() == 0
            assert dialog._jsr_table.item(0, 0).text() == "@std"
        finally:
            RuntimeSettings.set_registries([])

    def test_add_npm_row_appends_to_npm_table(self, qapp: QApplication, qtbot) -> None:
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        before_npm = dialog._npm_table.rowCount()
        before_jsr = dialog._jsr_table.rowCount()
        dialog._on_add_registry_row("npm")
        assert dialog._npm_table.rowCount() == before_npm + 1
        assert dialog._jsr_table.rowCount() == before_jsr
        last = dialog._npm_table.rowCount() - 1
        assert dialog._npm_table.item(last, 0).text() == "@new"

    def test_add_jsr_row_appends_to_jsr_table(self, qapp: QApplication, qtbot) -> None:
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        before_npm = dialog._npm_table.rowCount()
        before_jsr = dialog._jsr_table.rowCount()
        dialog._on_add_registry_row("jsr")
        assert dialog._jsr_table.rowCount() == before_jsr + 1
        assert dialog._npm_table.rowCount() == before_npm

    def test_remove_selected_row_drops_entry(self, qapp: QApplication, qtbot) -> None:
        from services.scripting.runtime_settings import RuntimeSettings

        RuntimeSettings.set_registries(
            [
                {
                    "id": "row-a",
                    "scope": "@a",
                    "url": "https://a/",
                    "kind": "npm",
                    "auth_kind": "none",
                    "auth_ref": "",
                },
                {
                    "id": "row-b",
                    "scope": "@b",
                    "url": "https://b/",
                    "kind": "npm",
                    "auth_kind": "none",
                    "auth_ref": "",
                },
            ]
        )
        try:
            tm = ThemeManager(qapp)
            dialog = SettingsDialog(tm)
            qtbot.addWidget(dialog)
            dialog._npm_table.selectRow(0)
            dialog._on_remove_registry_row("npm")
            assert dialog._npm_table.rowCount() == 1
            assert dialog._npm_table.item(0, 0).text() == "@b"
        finally:
            RuntimeSettings.set_registries([])

    def test_invalid_scope_is_flagged_red(self, qapp: QApplication, qtbot) -> None:
        """Scope without ``@`` prefix should colour the cell red + tooltip."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        dialog._on_add_registry_row("npm")
        row = dialog._npm_table.rowCount() - 1
        scope_item = dialog._npm_table.item(row, 0)
        scope_item.setText("bad-no-at-prefix")
        dialog._refresh_registry_row_validation()
        scope_item = dialog._npm_table.item(row, 0)
        assert "must start with '@'" in scope_item.toolTip()

    def test_invalid_url_is_flagged_red(self, qapp: QApplication, qtbot) -> None:
        """URL without ``https://`` should colour the cell red + tooltip."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        dialog._on_add_registry_row("npm")
        row = dialog._npm_table.rowCount() - 1
        url_item = dialog._npm_table.item(row, 1)
        url_item.setText("http://insecure.example/")
        dialog._refresh_registry_row_validation()
        url_item = dialog._npm_table.item(row, 1)
        assert "https://" in url_item.toolTip()

    def test_row_remove_deletes_stored_secret(self, qapp: QApplication, qtbot) -> None:
        """B3: removing a row also wipes its secret from the keychain."""
        from services.scripting.runtime_settings import RuntimeSettings

        deleted: list[str] = []

        class _SpyStore:
            backend_id = "spy"

            def put(self, r: str, s: str) -> None:
                pass

            def get(self, r: str) -> str | None:
                return None

            def delete(self, r: str) -> None:
                deleted.append(r)

        spy = _SpyStore()
        import services.scripting.secret_store as _ss

        original = _ss.get_default_store
        _ss.get_default_store = lambda: spy  # type: ignore[assignment]
        try:
            RuntimeSettings.set_registries(
                [
                    {
                        "id": "row-1",
                        "scope": "@deleteme",
                        "url": "https://npm.example/",
                        "kind": "npm",
                        "auth_kind": "token",
                        "auth_ref": "registry:row-1",
                    }
                ]
            )
            tm = ThemeManager(qapp)
            dialog = SettingsDialog(tm)
            qtbot.addWidget(dialog)
            dialog._npm_table.selectRow(0)
            dialog._on_remove_registry_row("npm")
            assert "registry:row-1" in deleted
        finally:
            _ss.get_default_store = original
            RuntimeSettings.set_registries([])

    def test_scope_rename_preserves_auth_ref(self, qapp: QApplication, qtbot) -> None:
        """B4: ``auth_ref`` is anchored to ``id``.

        Renaming scope keeps the existing keychain entry reachable.
        """
        from services.scripting.runtime_settings import RuntimeSettings

        RuntimeSettings.set_registries(
            [
                {
                    "id": "abc123",
                    "scope": "@old",
                    "url": "https://npm.example/",
                    "kind": "npm",
                    "auth_kind": "token",
                    "auth_ref": "registry:abc123",
                }
            ]
        )
        try:
            tm = ThemeManager(qapp)
            dialog = SettingsDialog(tm)
            qtbot.addWidget(dialog)
            # User renames the scope cell on the npm page.
            dialog._npm_table.item(0, 0).setText("@renamed")
            dialog._sync_table_into_registries("npm")
            entry = dialog._registries[0]
            assert entry["id"] == "abc123"
            assert entry["auth_ref"] == "registry:abc123"
            # New rows get a fresh UUID, not "abc123".
            dialog._on_add_registry_row("npm")
            new_entry = dialog._registries[-1]
            assert new_entry["id"] and new_entry["id"] != "abc123"
        finally:
            RuntimeSettings.set_registries([])

    def test_legacy_entries_without_id_get_migrated(self, qapp: QApplication, qtbot) -> None:
        """Settings persisted before ``id`` was introduced auto-receive one."""
        from services.scripting.runtime_settings import RuntimeSettings

        # Write directly with no ``id`` field to simulate a legacy blob.
        import json

        from PySide6.QtCore import QSettings

        s = QSettings("Postmark", "Postmark")
        s.setValue(
            "scripting/registries/entries",
            json.dumps(
                [
                    {
                        "scope": "@legacy",
                        "url": "https://npm.legacy/",
                        "kind": "npm",
                        "auth_kind": "none",
                        "auth_ref": "",
                    }
                ]
            ),
        )
        try:
            entries = RuntimeSettings.get_registries()
            assert len(entries) == 1
            assert entries[0]["id"]  # populated by migration
            assert entries[0]["scope"] == "@legacy"
        finally:
            RuntimeSettings.set_registries([])

    def test_apply_drops_invalid_rows_with_warning(self, qapp: QApplication, qtbot) -> None:
        """B6: invalid rows are stripped on Apply with a transient warning.

        They are not silently lost at read time.
        """
        from services.scripting.runtime_settings import RuntimeSettings

        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        # One valid + one invalid row, both on the npm page.
        dialog._on_add_registry_row("npm")
        dialog._npm_table.item(0, 0).setText("@good")
        dialog._npm_table.item(0, 1).setText("https://npm.good.example/")
        dialog._on_add_registry_row("npm")
        dialog._npm_table.item(1, 0).setText("bad-no-at")
        dialog._npm_table.item(1, 1).setText("http://insecure/")
        dialog._on_apply()
        try:
            kept = RuntimeSettings.get_registries()
            assert len(kept) == 1
            assert kept[0]["scope"] == "@good"
            # Backend label was hijacked with the drop warning.
            assert "dropped" in dialog._secret_backend_label.text().lower()
        finally:
            RuntimeSettings.set_registries([])

    def test_auth_button_shows_check_when_secret_set(self, qapp: QApplication, qtbot) -> None:
        """UX polish: ``Auth ✓`` text when a token/basic ref is recorded."""
        from PySide6.QtWidgets import QPushButton

        from services.scripting.runtime_settings import RuntimeSettings

        RuntimeSettings.set_registries(
            [
                {
                    "id": "row-x",
                    "scope": "@configured",
                    "url": "https://npm.example/",
                    "kind": "npm",
                    "auth_kind": "token",
                    "auth_ref": "registry:row-x",
                }
            ]
        )
        try:
            tm = ThemeManager(qapp)
            dialog = SettingsDialog(tm)
            qtbot.addWidget(dialog)
            # Auth button is in column 2 (the Type column is gone in the
            # per-kind split — kind is implied by the page).
            btn = dialog._npm_table.cellWidget(0, 2)
            assert isinstance(btn, QPushButton)
            assert "✓" in btn.text()
            assert "configured" in btn.toolTip().lower()
        finally:
            RuntimeSettings.set_registries([])

    def test_pypi_table_starts_empty(self, qapp: QApplication, qtbot) -> None:
        """Default state: no PyPI rows (uses public PyPI)."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog._pypi_table.rowCount() == 0

    def test_add_pypi_row_appends_with_priority_badge(self, qapp: QApplication, qtbot) -> None:
        """First row labels as 'Primary'; second as 'Extra 1'."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        dialog._on_add_pypi_index_row()
        dialog._on_add_pypi_index_row()
        assert dialog._pypi_table.rowCount() == 2
        assert dialog._pypi_table.item(0, 0).text() == "Primary"
        assert dialog._pypi_table.item(1, 0).text() == "Extra 1"

    def test_pypi_row_move_down_reorders(self, qapp: QApplication, qtbot) -> None:
        """``_on_move_pypi_index_row`` swaps rows and refreshes priority badges."""
        from services.scripting.runtime_settings import RuntimeSettings

        RuntimeSettings.set_pypi_indexes(
            [
                {
                    "id": "first",
                    "url": "https://a.test/",
                    "auth_kind": "none",
                    "auth_ref": "",
                },
                {
                    "id": "second",
                    "url": "https://b.test/",
                    "auth_kind": "none",
                    "auth_ref": "",
                },
            ]
        )
        try:
            tm = ThemeManager(qapp)
            dialog = SettingsDialog(tm)
            qtbot.addWidget(dialog)
            dialog._pypi_table.selectRow(0)
            dialog._on_move_pypi_index_row(1)
            assert dialog._pypi_table.item(0, 1).text() == "https://b.test/"
            assert dialog._pypi_table.item(0, 0).text() == "Primary"
            assert dialog._pypi_table.item(1, 1).text() == "https://a.test/"
        finally:
            RuntimeSettings.set_pypi_indexes([])

    def test_pypi_row_remove_wipes_secret(self, qapp: QApplication, qtbot) -> None:
        """Removing a PyPI row deletes its keychain entry (same B3 contract as npm)."""
        from services.scripting.runtime_settings import RuntimeSettings

        deleted: list[str] = []

        class _SpyStore:
            backend_id = "spy"

            def put(self, r: str, s: str) -> None:
                pass

            def get(self, r: str) -> str | None:
                return None

            def delete(self, r: str) -> None:
                deleted.append(r)

        spy = _SpyStore()
        import services.scripting.secret_store as _ss

        original = _ss.get_default_store
        _ss.get_default_store = lambda: spy  # type: ignore[assignment]
        try:
            RuntimeSettings.set_pypi_indexes(
                [
                    {
                        "id": "drop-me",
                        "url": "https://pypi.test/",
                        "auth_kind": "token",
                        "auth_ref": "pypi:drop-me",
                    }
                ]
            )
            tm = ThemeManager(qapp)
            dialog = SettingsDialog(tm)
            qtbot.addWidget(dialog)
            dialog._pypi_table.selectRow(0)
            dialog._on_remove_pypi_index_row()
            assert "pypi:drop-me" in deleted
        finally:
            _ss.get_default_store = original
            RuntimeSettings.set_pypi_indexes([])

    def test_localhost_http_is_accepted(self, qapp: QApplication, qtbot) -> None:
        """Local dev escape hatch: ``http://localhost…`` is treated as valid."""
        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog._registry_url_is_valid("http://localhost:4873")
        assert dialog._registry_url_is_valid("http://127.0.0.1:4873/")
        assert not dialog._registry_url_is_valid("http://prod.example/")

    def test_apply_persists_registries_and_pypi(self, qapp: QApplication, qtbot) -> None:
        from services.scripting.runtime_settings import RuntimeSettings

        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        dialog._on_add_registry_row("npm")
        last = dialog._npm_table.rowCount() - 1
        dialog._npm_table.item(last, 0).setText("@mytest")
        dialog._npm_table.item(last, 1).setText("https://npm.test.invalid/")
        dialog._default_npm_edit.setText("https://npm.mirror.test/")
        # PyPI: add a row, set URL.
        dialog._on_add_pypi_index_row()
        pypi_row = dialog._pypi_table.rowCount() - 1
        dialog._pypi_table.item(pypi_row, 1).setText("https://pypi.test.invalid/simple/")
        dialog._on_apply()
        try:
            entries = RuntimeSettings.get_registries()
            assert any(
                e["scope"] == "@mytest" and e["url"] == "https://npm.test.invalid/" for e in entries
            )
            default_url, _ref, _kind = RuntimeSettings.get_default_npm_registry()
            assert default_url == "https://npm.mirror.test/"
            indexes = RuntimeSettings.get_pypi_indexes()
            assert any(e["url"] == "https://pypi.test.invalid/simple/" for e in indexes)
        finally:
            RuntimeSettings.set_registries([])
            RuntimeSettings.set_default_npm_registry("")
            RuntimeSettings.set_pypi_indexes([])
            RuntimeSettings.set_pypi_config(
                {
                    "index_url": "",
                    "extra_index_url": "",
                    "auth_ref": "",
                    "auth_kind": "none",
                }
            )
