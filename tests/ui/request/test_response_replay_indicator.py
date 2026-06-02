"""Tests for the response viewer replayed-send indicator."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.request.response_viewer import ResponseViewerWidget


class TestResponseReplayIndicator:
    """Replay banner visibility and link signal."""

    def test_set_and_clear_replay_source(self, qapp: QApplication, qtbot) -> None:
        """Banner shows when a replay source is set and hides when cleared."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        assert viewer._replay_indicator.isHidden()

        viewer.set_replay_history_source(42, "View GET 400 (2024-06-01)")
        assert not viewer._replay_indicator.isHidden()
        assert viewer._replay_indicator._link.text() == "View GET 400 (2024-06-01)"

        viewer.clear_replay_history_source()
        assert viewer._replay_indicator.isHidden()

    def test_link_emits_entry_id(self, qapp: QApplication, qtbot) -> None:
        """Clicking the link emits replay_history_link_clicked with the entry id."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        viewer.set_replay_history_source(7, "View send")

        with qtbot.waitSignal(viewer.replay_history_link_clicked, timeout=2000) as blocker:
            qtbot.mouseClick(viewer._replay_indicator._link, Qt.MouseButton.LeftButton)

        assert blocker.args == [7]


class TestHistoryPanelFocusEntry:
    """History panel focus_entry selects a row."""

    def test_focus_entry_selects_tree_row(
        self, qapp: QApplication, qtbot, tmp_path, monkeypatch
    ) -> None:
        """focus_entry expands the date group and selects the target row."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from services.collection_service import CollectionService
        from services.request_history_service import RequestHistoryService
        from ui.sidebar.history.panel import HistoryPanel
        from ui.styling.history_settings_manager import HistorySettingsManager

        svc = CollectionService()
        coll = svc.create_collection("C")
        req = svc.create_request(coll.id, "GET", "http://example.com", "R")
        settings = HistorySettingsManager()
        entry_id = RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": "R",
                "method": "GET",
                "url": "http://example.com",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "headers": [], "body": "ok"},
            original_request={"method": "GET"},
            settings=settings,
        )
        assert entry_id is not None

        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(req.id, "R", is_persisted_request=True)
        panel.refresh()

        assert panel.focus_entry(entry_id)
        assert panel._current_entry_id == entry_id
