"""Tests for the per-request send-history sidebar panel."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTreeWidget

from services.request_history_service import RequestHistoryService
from ui.sidebar.history.delegate import ROLE_HISTORY_IS_DATE_GROUP
from ui.sidebar.history.helpers import (
    build_history_row_meta,
    first_history_entry_id,
    group_entries_by_local_date,
    populate_history_tree_widget,
)
from ui.sidebar.history.panel import HistoryPanel


def _entry_count(tree: QTreeWidget) -> int:
    """Count send rows (exclude date group parents)."""
    total = 0
    for index in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(index)
        if group is not None:
            total += group.childCount()
    return total


class TestRequestHistoryPanel:
    """Tests for HistoryPanel in request-scoped mode."""

    def test_construction_starts_without_request(self, qapp: QApplication, qtbot) -> None:
        """Panel starts in a request-required empty state."""
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        assert panel.objectName() == "requestHistoryPanel"
        assert panel._tree_widget.objectName() == "requestHistoryTree"
        assert "Open a saved request" in panel._state_label.text()

    def test_draft_shows_save_first_message(self, qapp: QApplication, qtbot) -> None:
        """Unsaved request tabs show the save-first empty state."""
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Draft", is_persisted_request=False)
        panel.show_request_required_state(
            "Save the request first to browse history for this request."
        )
        assert "Save the request first" in panel._state_label.text()
        assert panel._content_splitter.isHidden()

    def test_refresh_populates_tree_and_detail(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Persisted request refresh loads tree rows and detail body text."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from database.models.collections.collection_repository import (
            create_new_collection,
            create_new_request,
        )
        from ui.styling.history_settings_manager import HistorySettingsManager

        coll = create_new_collection("C")
        req = create_new_request(coll.id, "GET", "http://example.com", "Example")
        settings = HistorySettingsManager()
        RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": "Example",
                "method": "GET",
                "url": "http://example.com",
            },
            response={
                "status_code": 200,
                "elapsed_ms": 5.0,
                "headers": [{"key": "Content-Type", "value": "text/plain"}],
                "body": "hello",
            },
            original_request={"method": "GET", "url": "http://example.com", "body": "x"},
            settings=settings,
        )

        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(req.id, "Example", is_persisted_request=True)
        panel.refresh()

        assert panel._history_search_input.objectName() == "requestHistorySearch"
        assert panel._tree_widget.topLevelItemCount() == 1
        group = panel._tree_widget.topLevelItem(0)
        assert group is not None
        assert group.data(0, ROLE_HISTORY_IS_DATE_GROUP)
        assert group.text(0) == "Today"
        assert group.childCount() == 1
        assert _entry_count(panel._tree_widget) == 1
        assert first_history_entry_id(panel._tree_widget) is not None
        assert "Example" in panel._detail_name.text()
        assert "hello" in panel._body_edit.toPlainText()

    def test_search_filters_by_status(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Search box filters rows by HTTP status code."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from database.models.collections.collection_repository import (
            create_new_collection,
            create_new_request,
        )
        from ui.styling.history_settings_manager import HistorySettingsManager

        coll = create_new_collection("C")
        req = create_new_request(coll.id, "GET", "http://example.com", "Example")
        settings = HistorySettingsManager()
        RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": "Ok",
                "method": "GET",
                "url": "http://example.com/ok",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "headers": [], "body": "a"},
            original_request={"method": "GET"},
            settings=settings,
        )
        RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": "Bad",
                "method": "GET",
                "url": "http://example.com/bad",
            },
            response={"status_code": 400, "elapsed_ms": 1.0, "headers": [], "body": "b"},
            original_request={"method": "GET"},
            settings=settings,
        )

        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(req.id, "Example", is_persisted_request=True)
        panel.refresh()
        assert _entry_count(panel._tree_widget) == 2

        panel._history_search_input.setText("400")
        qtbot.wait(50)
        assert panel._tree_widget.topLevelItemCount() == 1
        assert _entry_count(panel._tree_widget) == 1
        assert "Bad" in panel._detail_name.text()

    def test_search_no_match_keeps_search_visible(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Empty search results keep the search field and browse layout visible."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from database.models.collections.collection_repository import (
            create_new_collection,
            create_new_request,
        )
        from ui.styling.history_settings_manager import HistorySettingsManager

        coll = create_new_collection("C")
        req = create_new_request(coll.id, "GET", "http://example.com", "Example")
        settings = HistorySettingsManager()
        RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": "Example",
                "method": "GET",
                "url": "http://example.com",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "headers": [], "body": "ok"},
            original_request={"method": "GET"},
            settings=settings,
        )

        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.show()
        qtbot.waitExposed(panel)
        panel.set_request_context(req.id, "Example", is_persisted_request=True)
        panel.refresh()

        panel._history_search_input.setText("999")
        qtbot.wait(50)

        assert not panel._history_search_input.isHidden()
        assert not panel._content_splitter.isHidden()
        assert panel._state_label.isHidden()
        assert panel._list_stack.currentIndex() == 0
        assert 'No history matches "999"' in panel._list_empty_label.text()

    def test_collapse_date_group_keeps_replay_enabled(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Collapsing a date group must not clear the active send or disable replay."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from database.models.collections.collection_repository import (
            create_new_collection,
            create_new_request,
        )
        from ui.styling.history_settings_manager import HistorySettingsManager

        coll = create_new_collection("C")
        req = create_new_request(coll.id, "GET", "http://example.com", "Example")
        settings = HistorySettingsManager()
        RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": "Example",
                "method": "GET",
                "url": "http://example.com",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "headers": [], "body": "ok"},
            original_request={"method": "GET", "url": "http://example.com"},
            settings=settings,
        )

        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.show()
        qtbot.waitExposed(panel)
        panel.set_request_context(req.id, "Example", is_persisted_request=True)
        panel.refresh()

        entry_id = first_history_entry_id(panel._tree_widget)
        assert entry_id is not None
        assert panel._replay_btn.isEnabled()

        group = panel._tree_widget.topLevelItem(0)
        assert group is not None
        panel._tree_widget.setCurrentItem(group)

        assert panel._current_entry_id == entry_id
        assert panel._replay_btn.isEnabled()

    def test_group_entries_by_local_date(self) -> None:
        """Rows group under Today when executed_at is now."""
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        groups = group_entries_by_local_date(
            [
                {"id": 1, "executed_at": now},
                {"id": 2, "executed_at": now},
            ]
        )
        assert len(groups) == 1
        assert groups[0][0] == "Today"
        assert len(groups[0][1]) == 2

    def test_populate_history_tree_widget_builds_date_groups(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Tree population creates expandable date parents with child sends."""
        from datetime import UTC, datetime

        tree = QTreeWidget()
        qtbot.addWidget(tree)
        now = datetime.now(UTC).isoformat()
        populate_history_tree_widget(
            tree,
            [
                {"id": 10, "executed_at": now, "request_name": "A", "method": "GET"},
                {"id": 11, "executed_at": now, "request_name": "B", "method": "POST"},
            ],
        )
        assert tree.topLevelItemCount() == 1
        group = tree.topLevelItem(0)
        assert group is not None
        assert group.data(0, ROLE_HISTORY_IS_DATE_GROUP)
        assert group.isExpanded()
        assert group.childCount() == 2

    def test_deleted_label_in_row_meta(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Orphaned rows expose (deleted) via source_label in list metadata."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from database.models.collections.collection_repository import (
            create_new_collection,
            create_new_request,
            delete_request,
        )
        from ui.styling.history_settings_manager import HistorySettingsManager

        coll = create_new_collection("C")
        req = create_new_request(coll.id, "GET", "http://x", "Gone")
        settings = HistorySettingsManager()
        RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": "Gone",
                "method": "GET",
                "url": "http://x",
            },
            response={"status_code": 204, "elapsed_ms": 1.0, "headers": [], "body": ""},
            original_request={"method": "GET"},
            settings=settings,
        )
        delete_request(req.id)

        items = RequestHistoryService.list_for_request(99999)
        assert items == []

        rows = RequestHistoryService.list_for_sidebar()
        assert any(r.get("request_id") is None for r in rows)
        orphaned = [r for r in rows if r.get("source_label") == "(deleted)"]
        assert orphaned
        assert "(deleted)" in build_history_row_meta(orphaned[0])

    def test_replay_button_emits_signal(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Replay button emits replay_requested with the selected entry id."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from database.models.collections.collection_repository import (
            create_new_collection,
            create_new_request,
        )
        from ui.styling.history_settings_manager import HistorySettingsManager

        coll = create_new_collection("C")
        req = create_new_request(coll.id, "GET", "http://example.com", "Example")
        settings = HistorySettingsManager()
        entry_id = RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": "Example",
                "method": "GET",
                "url": "http://example.com",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "headers": [], "body": "ok"},
            original_request={"method": "GET", "url": "http://example.com"},
            settings=settings,
        )
        assert entry_id is not None

        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(req.id, "Example", is_persisted_request=True)
        panel.refresh()

        with qtbot.waitSignal(panel.replay_requested, timeout=2000) as blocker:
            qtbot.mouseClick(panel._replay_btn, Qt.MouseButton.LeftButton)
        assert blocker.args == [entry_id]
