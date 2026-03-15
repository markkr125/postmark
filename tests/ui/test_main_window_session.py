"""Tests for tab session persistence (save on close, restore on launch)."""

from __future__ import annotations

import json

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from services.collection_service import CollectionService
from ui.main_window import MainWindow
from ui.styling.tab_settings_manager import TabSettingsManager


# ------------------------------------------------------------------
# TabSettingsManager — unit tests for save/load/clear
# ------------------------------------------------------------------
class TestTabSettingsManagerSession:
    """Unit tests for the session persistence helpers on TabSettingsManager."""

    def test_save_and_load_round_trip(self, qapp: QApplication) -> None:
        """Saved session data survives a load round-trip."""
        mgr = TabSettingsManager(qapp)
        payload = {
            "tabs": [{"type": "request", "id": 1}],
            "active": 0,
        }
        mgr.save_open_tabs(payload)
        loaded = mgr.load_open_tabs()
        assert loaded == payload

    def test_load_returns_none_when_empty(self, qapp: QApplication) -> None:
        """load_open_tabs returns None when nothing has been saved."""
        mgr = TabSettingsManager(qapp)
        assert mgr.load_open_tabs() is None

    def test_load_returns_none_for_corrupt_json(self, qapp: QApplication) -> None:
        """Corrupt JSON in QSettings yields None instead of raising."""
        settings = QSettings("Postmark", "Postmark")
        settings.setValue("tabs/session", "NOT VALID JSON {{{")
        settings.sync()

        mgr = TabSettingsManager(qapp)
        assert mgr.load_open_tabs() is None

    def test_load_returns_none_for_non_dict_json(self, qapp: QApplication) -> None:
        """Valid JSON that is not a dict yields None."""
        settings = QSettings("Postmark", "Postmark")
        settings.setValue("tabs/session", json.dumps([1, 2, 3]))
        settings.sync()

        mgr = TabSettingsManager(qapp)
        assert mgr.load_open_tabs() is None

    def test_clear_removes_saved_session(self, qapp: QApplication) -> None:
        """clear_open_tabs removes the persisted session."""
        mgr = TabSettingsManager(qapp)
        mgr.save_open_tabs({"tabs": [], "active": 0})
        mgr.clear_open_tabs()
        assert mgr.load_open_tabs() is None


# ------------------------------------------------------------------
# MainWindow — _persist_open_tabs
# ------------------------------------------------------------------
class TestPersistOpenTabs:
    """Tests for the _persist_open_tabs helper on MainWindow."""

    def test_persist_records_open_request_tabs(self, qapp: QApplication, qtbot) -> None:
        """_persist_open_tabs saves request tab IDs and active index."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req2 = svc.create_request(coll.id, "POST", "http://b.com", "B")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req1.id, push_history=False)
        window._open_request(req2.id, push_history=False)
        window._tab_bar.setCurrentIndex(1)

        saved = window._tab_settings_manager.load_open_tabs()
        assert saved is not None
        assert saved["active"] == 1
        assert len(saved["tabs"]) == 2
        assert saved["tabs"][0] == {"type": "request", "id": req1.id, "method": "GET", "name": "A"}
        assert saved["tabs"][1] == {"type": "request", "id": req2.id, "method": "POST", "name": "B"}

    def test_persist_records_folder_tabs(self, qapp: QApplication, qtbot) -> None:
        """_persist_open_tabs saves folder tab collection IDs."""
        svc = CollectionService()
        coll = svc.create_collection("FolderColl")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_folder(coll.id)

        saved = window._tab_settings_manager.load_open_tabs()
        assert saved is not None
        assert len(saved["tabs"]) == 1
        assert saved["tabs"][0] == {"type": "folder", "id": coll.id}

    def test_persist_records_mixed_tabs(self, qapp: QApplication, qtbot) -> None:
        """_persist_open_tabs handles a mix of request and folder tabs."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://x.com", "X")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req.id, push_history=False)
        window._open_folder(coll.id)

        saved = window._tab_settings_manager.load_open_tabs()
        assert saved is not None
        assert len(saved["tabs"]) == 2
        types = [t["type"] for t in saved["tabs"]]
        assert "request" in types
        assert "folder" in types

    def test_persist_on_close_event(self, qapp: QApplication, qtbot) -> None:
        """CloseEvent persists tabs before the window is destroyed."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://x.com", "X")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req.id, push_history=False)

        # Clear any previously persisted data to verify closeEvent writes it
        window._tab_settings_manager.clear_open_tabs()
        assert window._tab_settings_manager.load_open_tabs() is None

        window.close()

        saved = window._tab_settings_manager.load_open_tabs()
        assert saved is not None
        assert len(saved["tabs"]) == 1


# ------------------------------------------------------------------
# MainWindow — _restore_tabs
# ------------------------------------------------------------------
class TestRestoreTabs:
    """Tests for the _restore_tabs helper on MainWindow."""

    def test_restore_opens_saved_request_tabs(self, qapp: QApplication, qtbot) -> None:
        """_restore_tabs reopens request tabs from the persisted session."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req2 = svc.create_request(coll.id, "POST", "http://b.com", "B")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {"type": "request", "id": req1.id, "method": "GET", "name": "A"},
                    {"type": "request", "id": req2.id, "method": "POST", "name": "B"},
                ],
                "active": 1,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        # Simulate load_finished which triggers _restore_tabs
        window.collection_widget.load_finished.emit()

        assert window._tab_bar.count() == 2
        assert window._tab_bar.currentIndex() == 1
        # Active tab is materialised on activation
        assert window.request_widget._url_input.text() == "http://b.com"

    def test_restore_opens_folder_tabs(self, qapp: QApplication, qtbot) -> None:
        """_restore_tabs reopens folder tabs from the persisted session."""
        svc = CollectionService()
        coll = svc.create_collection("FolderColl")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [{"type": "folder", "id": coll.id}],
                "active": 0,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window.collection_widget.load_finished.emit()

        assert window._tab_bar.count() == 1
        ctx = window._tabs[0]
        assert ctx.tab_type == "folder"
        assert ctx.collection_id == coll.id

    def test_restore_skips_deleted_request(self, qapp: QApplication, qtbot) -> None:
        """Deleted requests are silently skipped during restore."""
        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [{"type": "request", "id": 999999}],
                "active": 0,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window.collection_widget.load_finished.emit()

        assert window._tab_bar.count() == 0

    def test_restore_skips_deleted_collection(self, qapp: QApplication, qtbot) -> None:
        """Deleted collections are silently skipped during restore."""
        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [{"type": "folder", "id": 999999}],
                "active": 0,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window.collection_widget.load_finished.emit()

        assert window._tab_bar.count() == 0

    def test_restore_does_nothing_when_no_session(self, qapp: QApplication, qtbot) -> None:
        """No session data means no tabs are restored."""
        window = MainWindow()
        qtbot.addWidget(window)

        window.collection_widget.load_finished.emit()

        assert window._tab_bar.count() == 0

    def test_restore_handles_mixed_valid_and_deleted(self, qapp: QApplication, qtbot) -> None:
        """Valid tabs are restored while deleted ones are skipped."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://alive.com", "Alive")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {"type": "request", "id": 999999},
                    {"type": "request", "id": req.id},
                ],
                "active": 0,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window.collection_widget.load_finished.emit()

        assert window._tab_bar.count() == 1
        assert window.request_widget._url_input.text() == "http://alive.com"

    def test_restore_clamps_active_index(self, qapp: QApplication, qtbot) -> None:
        """Active index beyond restored count is clamped gracefully."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://x.com", "X")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [{"type": "request", "id": req.id}],
                "active": 99,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window.collection_widget.load_finished.emit()

        # Should not crash; tab 0 is the only option
        assert window._tab_bar.count() == 1

    def test_restore_ignores_unknown_tab_type(self, qapp: QApplication, qtbot) -> None:
        """Unknown tab types in session data are silently skipped."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://x.com", "X")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {"type": "alien", "id": 1},
                    {"type": "request", "id": req.id},
                ],
                "active": 0,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window.collection_widget.load_finished.emit()

        assert window._tab_bar.count() == 1


# ------------------------------------------------------------------
# Draft tab session persistence
# ------------------------------------------------------------------
class TestDraftSessionPersistence:
    """Tests for persisting and restoring unsaved draft tabs."""

    def test_persist_records_draft_tabs(self, qapp: QApplication, qtbot) -> None:
        """Draft tabs are serialized with editor state snapshot."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        window.request_widget._url_input.setText("http://draft.example.com")
        window.request_widget._method_combo.setCurrentText("POST")

        # Force a fresh persist after edits
        window._persist_open_tabs()

        saved = window._tab_settings_manager.load_open_tabs()
        assert saved is not None
        assert len(saved["tabs"]) == 1
        draft_entry = saved["tabs"][0]
        assert draft_entry["type"] == "draft"
        assert draft_entry["data"]["url"] == "http://draft.example.com"
        assert draft_entry["data"]["method"] == "POST"

    def test_persist_includes_draft_name(self, qapp: QApplication, qtbot) -> None:
        """Draft tabs include the user-set draft_name in session data."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        idx = window._tab_bar.currentIndex()
        window._tabs[idx].draft_name = "My Custom Draft"

        window._persist_open_tabs()
        saved = window._tab_settings_manager.load_open_tabs()
        assert saved is not None
        assert saved["tabs"][0]["draft_name"] == "My Custom Draft"

    def test_restore_reopens_draft_tab(self, qapp: QApplication, qtbot) -> None:
        """Draft tabs are restored with their editor state."""
        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {
                        "type": "draft",
                        "data": {"method": "PUT", "url": "http://draft.test"},
                    }
                ],
                "active": 0,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window.collection_widget.load_finished.emit()

        assert window._tab_bar.count() == 1
        assert window.request_widget._url_input.text() == "http://draft.test"
        assert window.request_widget._method_combo.currentText() == "PUT"
        ctx = window._tabs[0]
        assert ctx.request_id is None

    def test_restore_draft_with_custom_name(self, qapp: QApplication, qtbot) -> None:
        """Restored draft tab uses the persisted draft_name."""
        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {
                        "type": "draft",
                        "data": {"method": "GET", "url": ""},
                        "draft_name": "Renamed Draft",
                    }
                ],
                "active": 0,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window.collection_widget.load_finished.emit()

        assert window._tab_bar.count() == 1
        ctx = window._tabs[0]
        assert ctx.draft_name == "Renamed Draft"

    def test_restore_draft_skips_missing_data(self, qapp: QApplication, qtbot) -> None:
        """Draft entry without a 'data' dict is silently skipped."""
        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [{"type": "draft"}],
                "active": 0,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window.collection_widget.load_finished.emit()

        assert window._tab_bar.count() == 0

    def test_persist_mixed_request_and_draft(self, qapp: QApplication, qtbot) -> None:
        """Session with both persisted requests and drafts round-trips."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://saved.com", "Saved")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {"type": "request", "id": req.id},
                    {
                        "type": "draft",
                        "data": {"method": "DELETE", "url": "http://unsaved.com"},
                    },
                ],
                "active": 1,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window.collection_widget.load_finished.emit()

        assert window._tab_bar.count() == 2
        # Tab 0: persisted request
        assert window._tabs[0].request_id == req.id
        # Tab 1: draft
        assert window._tabs[1].request_id is None
        assert window._tab_bar.currentIndex() == 1


# ------------------------------------------------------------------
# Deferred tab materialisation
# ------------------------------------------------------------------
class TestDeferredTabRestore:
    """Tests for deferred (lazy) tab restoration using the new session format."""

    def test_deferred_tabs_create_chips_without_editor(self, qapp: QApplication, qtbot) -> None:
        """New-format session entries create tab chips without materialising editors."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req2 = svc.create_request(coll.id, "PUT", "http://b.com", "B")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {"type": "request", "id": req1.id, "method": "GET", "name": "A"},
                    {"type": "request", "id": req2.id, "method": "PUT", "name": "B"},
                ],
                "active": 0,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)
        window.collection_widget.load_finished.emit()

        assert window._tab_bar.count() == 2
        # Active tab (0) is materialised
        assert 0 in window._tabs
        assert window._tabs[0].request_id == req1.id
        # Inactive tab (1) is deferred
        assert 1 not in window._tabs
        assert 1 in window._deferred_tabs
        assert window._deferred_tabs[1]["request_id"] == req2.id

    def test_selecting_deferred_tab_materialises_it(self, qapp: QApplication, qtbot) -> None:
        """Clicking a deferred tab creates its editor and viewer."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req2 = svc.create_request(coll.id, "POST", "http://b.com", "B")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {"type": "request", "id": req1.id, "method": "GET", "name": "A"},
                    {"type": "request", "id": req2.id, "method": "POST", "name": "B"},
                ],
                "active": 0,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)
        window.collection_widget.load_finished.emit()

        # Switch to the deferred tab
        window._tab_bar.setCurrentIndex(1)

        # Now it is materialised
        assert 1 in window._tabs
        assert 1 not in window._deferred_tabs
        assert window._tabs[1].request_id == req2.id
        assert window.request_widget._url_input.text() == "http://b.com"

    def test_deferred_deleted_request_removed_on_materialise(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Deferred tab for a deleted request silently disappears on selection."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://a.com", "A")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {"type": "request", "id": req.id, "method": "GET", "name": "A"},
                    {"type": "request", "id": 999999, "method": "DELETE", "name": "Gone"},
                ],
                "active": 0,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)
        window.collection_widget.load_finished.emit()

        assert window._tab_bar.count() == 2
        # Select the deferred tab pointing to a deleted request
        window._tab_bar.setCurrentIndex(1)

        # The deleted tab should be removed
        assert window._tab_bar.count() == 1

    def test_old_format_falls_back_to_eager(self, qapp: QApplication, qtbot) -> None:
        """Session entries without method/name use eager loading (backward compat)."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://old.com", "Old")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [{"type": "request", "id": req.id}],
                "active": 0,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)
        window.collection_widget.load_finished.emit()

        # Eagerly materialised — no deferred entry
        assert 0 in window._tabs
        assert 0 not in window._deferred_tabs
        assert window._tabs[0].request_id == req.id

    def test_close_deferred_tab(self, qapp: QApplication, qtbot) -> None:
        """Closing a deferred tab removes it without errors."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req2 = svc.create_request(coll.id, "POST", "http://b.com", "B")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {"type": "request", "id": req1.id, "method": "GET", "name": "A"},
                    {"type": "request", "id": req2.id, "method": "POST", "name": "B"},
                ],
                "active": 0,
            }
        )

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)
        window.collection_widget.load_finished.emit()

        # Close the deferred tab (index 1)
        window._on_tab_close(1)

        assert window._tab_bar.count() == 1
        assert 1 not in window._deferred_tabs
