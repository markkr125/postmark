"""Tests for FolderEditorWidget script features — history, status bar, search."""

from __future__ import annotations

from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QPushButton

from ui.request.folder_editor import FolderEditorWidget


class TestFolderEditorScriptHistory:
    """Tests for the script version history button and version capture."""

    def test_history_button_exists(self, qapp: QApplication, qtbot) -> None:
        """Each script tab has a History button."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        assert editor._pre_history_btn is not None
        assert editor._pre_history_btn.text() == "History"
        assert editor._test_history_btn is not None
        assert editor._test_history_btn.text() == "History"

    def test_version_capture_timer_created(self, qapp: QApplication, qtbot) -> None:
        """A version capture timer is created during init."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        assert editor._version_capture_timer.isSingleShot()

    @patch("ui.request.request_editor.scripts.scripts_mixin.ScriptVersionService.capture")
    def test_version_capture_fires_on_edit(self, mock_capture, qapp: QApplication, qtbot) -> None:
        """Editing a script captures a version after the debounce."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        editor.load_collection({"name": "Coll"}, collection_id=7)

        editor._pre_request_edit.setPlainText("console.log('hi');")
        # Fire the timer immediately
        editor._version_capture_timer.stop()
        editor._capture_script_versions()

        mock_capture.assert_called()
        call_kwargs = mock_capture.call_args
        assert call_kwargs[1]["collection_id"] == 7
        assert call_kwargs[1]["request_id"] is None
        assert call_kwargs[1]["script_type"] == "pre_request"

    @patch("ui.request.request_editor.scripts.scripts_mixin.ScriptVersionService.capture")
    def test_no_capture_without_collection(self, mock_capture, qapp: QApplication, qtbot) -> None:
        """Version capture does nothing without a loaded collection."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor._pre_request_edit.setPlainText("x")
        editor._capture_script_versions()

        mock_capture.assert_not_called()

    @patch("ui.request.request_editor.scripts.scripts_mixin.ScriptVersionService.capture")
    def test_no_capture_during_load(self, mock_capture, qapp: QApplication, qtbot) -> None:
        """Loading data does not trigger version capture."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(
            {"name": "Coll", "events": {"pre_request": "x"}},
            collection_id=5,
        )
        # Timer should NOT have started during load
        assert not editor._version_capture_timer.isActive()


class TestFolderEditorStatusBar:
    """Tests for the script editor status bar."""

    def test_status_bar_exists(self, qapp: QApplication, qtbot) -> None:
        """Both script editors have a status label."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        assert hasattr(editor, "_pre_status_label")
        assert hasattr(editor, "_test_status_label")

    def test_status_bar_initial_text(self, qapp: QApplication, qtbot) -> None:
        """Status bar shows initial cursor position."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        text = editor._pre_status_label.text()
        assert "Ln 1" in text
        assert "Col 1" in text
        assert "JavaScript" in text

    def test_status_bar_updates_on_text(self, qapp: QApplication, qtbot) -> None:
        """Typing text updates the character count."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        editor._pre_request_edit.setPlainText("hello")
        text = editor._pre_status_label.text()
        assert "5 chars" in text


class TestFolderEditorSearchBar:
    """Tests for the search bars on folder editor script tabs."""

    def test_search_bars_exist(self, qapp: QApplication, qtbot) -> None:
        """Both script tabs have a search bar attached."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        assert hasattr(editor, "_pre_search_bar")
        assert hasattr(editor, "_test_search_bar")

    def test_search_bars_start_hidden(self, qapp: QApplication, qtbot) -> None:
        """Search bars are hidden by default."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        assert editor._pre_search_bar.isHidden()
        assert editor._test_search_bar.isHidden()

    def test_search_bar_toggle(self, qapp: QApplication, qtbot) -> None:
        """Toggling the search bar shows it."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        editor._pre_search_bar.toggle_search()
        assert not editor._pre_search_bar.isHidden()

    def test_editor_minimum_height(self, qapp: QApplication, qtbot) -> None:
        """Script editors have a non-zero minimum height."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        assert editor._pre_request_edit.minimumHeight() >= 80
        assert editor._test_script_edit.minimumHeight() >= 80


class TestFolderEditorToolbar:
    """Tests for the script toolbar buttons (Find, Replace, GoToLine)."""

    def test_toolbar_buttons_exist(self, qapp: QApplication, qtbot) -> None:
        """Each script tab has Find, Replace, and GoToLine toolbar buttons."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        all_btns = editor.findChildren(QPushButton, "iconButton")
        tips = [b.toolTip() for b in all_btns]
        assert sum(t.startswith("Find (") for t in tips) >= 2
        assert sum("Find & Replace" in t for t in tips) >= 2
        assert sum("Go to Line" in t for t in tips) >= 2

    def test_toolbar_find_opens_search(self, qapp: QApplication, qtbot) -> None:
        """Clicking the Find toolbar button opens a search bar."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        btn = next(
            b
            for b in editor.findChildren(QPushButton, "iconButton")
            if b.toolTip().startswith("Find (")
        )
        btn.click()
        opened = not editor._pre_search_bar.isHidden() or not editor._test_search_bar.isHidden()
        assert opened

    def test_toolbar_replace_opens_replace(self, qapp: QApplication, qtbot) -> None:
        """Clicking the Replace toolbar button opens the replace bar."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        btn = next(
            b
            for b in editor.findChildren(QPushButton, "iconButton")
            if "Find & Replace" in b.toolTip()
        )
        btn.click()
        opened = not editor._pre_search_bar.isHidden() or not editor._test_search_bar.isHidden()
        assert opened


class TestFolderEditorAutoSave:
    """Tests for the auto-save toggle on script tabs."""

    def test_auto_save_checkboxes_exist(self, qapp: QApplication, qtbot) -> None:
        """Both script tabs have auto-save checkboxes."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        assert hasattr(editor, "_auto_save_checkboxes")
        assert len(editor._auto_save_checkboxes) == 2

    def test_auto_save_starts_checked(self, qapp: QApplication, qtbot) -> None:
        """Auto-save checkboxes start checked by default."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        for cb in editor._auto_save_checkboxes:
            assert cb.isChecked()

    def test_auto_save_syncs_checkboxes(self, qapp: QApplication, qtbot) -> None:
        """Toggling one auto-save checkbox syncs the other."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        editor._auto_save_checkboxes[0].setChecked(False)
        assert not editor._auto_save_checkboxes[1].isChecked()

    def test_auto_save_changes_interval(self, qapp: QApplication, qtbot) -> None:
        """Disabling auto-save increases the version capture interval."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        fast_interval = editor._version_capture_timer.interval()
        editor._auto_save_checkboxes[0].setChecked(False)
        assert editor._version_capture_timer.interval() > fast_interval

    def test_auto_save_persists_per_collection(self, qapp: QApplication, qtbot) -> None:
        """Disabling auto-save is remembered for a specific collection."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        editor.load_collection({"name": "Coll"}, collection_id=99)
        editor._auto_save_checkboxes[0].setChecked(False)

        # Reload same collection — auto-save should still be off
        editor.load_collection({"name": "Coll"}, collection_id=99)
        assert not editor._auto_save_checkboxes[0].isChecked()

        # Load a different collection — auto-save should be on (default)
        editor.load_collection({"name": "Other"}, collection_id=100)
        assert editor._auto_save_checkboxes[0].isChecked()

    def test_auto_save_follows_global_default(self, qapp: QApplication, qtbot) -> None:
        """When global default is OFF, new entities start with auto-save off."""
        from PySide6.QtCore import QSettings

        from ui.styling.theme_manager import _APP, _ORG

        settings = QSettings(_ORG, _APP)
        settings.setValue("scripting/auto_save_default", False)

        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        editor.load_collection({"name": "Coll"}, collection_id=200)
        assert not editor._auto_save_checkboxes[0].isChecked()

    def test_per_entity_overrides_global_default(self, qapp: QApplication, qtbot) -> None:
        """Per-entity override takes precedence over global default."""
        from PySide6.QtCore import QSettings

        from ui.styling.theme_manager import _APP, _ORG

        settings = QSettings(_ORG, _APP)
        settings.setValue("scripting/auto_save_default", False)

        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        editor.load_collection({"name": "Coll"}, collection_id=201)
        # Enable auto-save (overriding global OFF)
        editor._auto_save_checkboxes[0].setChecked(True)

        # Reload — override should persist
        editor.load_collection({"name": "Coll"}, collection_id=201)
        assert editor._auto_save_checkboxes[0].isChecked()

        # Different collection — should follow global default (OFF)
        editor.load_collection({"name": "Other"}, collection_id=202)
        assert not editor._auto_save_checkboxes[0].isChecked()
