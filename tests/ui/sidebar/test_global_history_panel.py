"""Tests for workspace-wide (left-rail) send history panel."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from services.request_history_service import RequestHistoryService
from ui.sidebar.history.helpers import find_history_tree_item
from ui.sidebar.history.panel import HistoryPanel


class TestGlobalHistoryPanel:
    """HistoryPanel in global (left-rail) mode."""

    def test_set_global_mode_object_name_and_empty(self, qapp: QApplication, qtbot) -> None:
        """Global mode uses globalHistoryPanel and workspace empty copy."""
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.set_global_mode()
        assert panel.objectName() == "globalHistoryPanel"
        assert "No send history yet" in panel._state_label.text()
        assert panel._replay_btn.isHidden()
        assert panel._open_btn.isHidden()

    def test_global_mode_hides_detail_pane(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Left-rail global history is list-only; no Body/Headers preview stack."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from ui.styling.history_settings_manager import HistorySettingsManager

        settings = HistorySettingsManager()
        entry_id = RequestHistoryService.record_send(
            identity={
                "request_id": None,
                "request_name": "",
                "method": "GET",
                "url": "http://list-only.example",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "body": "preview-me"},
            original_request={"method": "GET", "url": "http://list-only.example"},
            settings=settings,
        )
        assert entry_id is not None
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.set_global_mode()
        panel.refresh()
        assert not panel._detail_host.isVisible()
        assert panel._body_edit.toPlainText() == ""

    def test_refresh_lists_all_sends(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Global refresh uses list_for_sidebar."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from ui.styling.history_settings_manager import HistorySettingsManager

        settings = HistorySettingsManager()
        entry_id = RequestHistoryService.record_send(
            identity={
                "request_id": None,
                "request_name": "",
                "method": "GET",
                "url": "http://draft.example",
            },
            response={"status_code": 204, "elapsed_ms": 1.0, "body": "ok"},
            original_request={"method": "GET", "url": "http://draft.example"},
            settings=settings,
        )
        assert entry_id is not None
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.set_global_mode()
        panel.refresh()
        assert panel._current_entry_id == entry_id
        assert panel._items_by_id[entry_id]["source_label"] == "(draft)"

    def test_context_menu_open_only(self, qapp: QApplication, qtbot) -> None:
        """Global mode context menu offers Open, not replay/delete."""
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.set_global_mode()
        with qtbot.waitSignal(panel.entry_open_requested, timeout=1000) as blocker:
            panel._emit_entry_open(42)
        assert blocker.args == [42]

    def test_enter_emits_open(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Enter on a focused send row emits entry_open_requested."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from ui.styling.history_settings_manager import HistorySettingsManager

        settings = HistorySettingsManager()
        entry_id = RequestHistoryService.record_send(
            identity={
                "request_id": None,
                "request_name": "",
                "method": "POST",
                "url": "http://enter.example",
            },
            response={"status_code": 201, "elapsed_ms": 2.0, "body": "x"},
            original_request={"method": "POST", "url": "http://enter.example"},
            settings=settings,
        )
        assert entry_id is not None
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.set_global_mode()
        panel.refresh()
        panel._tree_widget.setFocus()
        with qtbot.waitSignal(panel.entry_open_requested, timeout=1000) as blocker:
            QTest.keyClick(panel._tree_widget, Qt.Key.Key_Return)
        assert blocker.args == [entry_id]

    def test_search_filters_by_url(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Global search filters the tree by URL substring."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from ui.styling.history_settings_manager import HistorySettingsManager

        settings = HistorySettingsManager()
        RequestHistoryService.record_send(
            identity={
                "request_id": None,
                "request_name": "",
                "method": "GET",
                "url": "http://alpha.example",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "body": "a"},
            original_request=None,
            settings=settings,
        )
        beta_id = RequestHistoryService.record_send(
            identity={
                "request_id": None,
                "request_name": "",
                "method": "GET",
                "url": "http://beta.example",
            },
            response={"status_code": 201, "elapsed_ms": 1.0, "body": "b"},
            original_request=None,
            settings=settings,
        )
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.set_global_mode()
        panel.refresh()
        panel._history_search_input.setText("beta")
        qtbot.wait(50)
        assert panel._current_entry_id == beta_id

    def test_single_click_emits_open(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Single-click on a send row emits entry_open_requested."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from ui.styling.history_settings_manager import HistorySettingsManager

        settings = HistorySettingsManager()
        entry_id = RequestHistoryService.record_send(
            identity={
                "request_id": None,
                "request_name": "",
                "method": "GET",
                "url": "http://click.example",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "body": "x"},
            original_request=None,
            settings=settings,
        )
        assert entry_id is not None
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.set_global_mode()
        panel.refresh()
        item = find_history_tree_item(panel._tree_widget, entry_id)
        assert item is not None
        with qtbot.waitSignal(panel.entry_open_requested, timeout=1000) as blocker:
            panel._on_tree_item_clicked(item, 0)
        assert blocker.args == [entry_id]

    def test_global_context_menu_actions_open_only(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Global context menu builder exposes Open only (no replay/delete)."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from ui.styling.history_settings_manager import HistorySettingsManager

        settings = HistorySettingsManager()
        entry_id = RequestHistoryService.record_send(
            identity={
                "request_id": None,
                "request_name": "",
                "method": "GET",
                "url": "http://menu.example",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "body": "x"},
            original_request=None,
            settings=settings,
        )
        assert entry_id is not None
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.set_global_mode()
        actions = panel._global_context_menu_actions(entry_id)
        assert len(actions) == 1
        assert actions[0].text() == "Open"
        with qtbot.waitSignal(panel.entry_open_requested, timeout=1000) as blocker:
            actions[0].trigger()
        assert blocker.args == [entry_id]

    def test_date_filter_popup_applies_range(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Header filter button opens popup; Apply restricts the global list."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from datetime import UTC, datetime, timedelta

        from database.database import get_session
        from database.models.request_history.model.request_history_entry_model import (
            RequestHistoryEntryModel,
        )
        from ui.styling.history_settings_manager import HistorySettingsManager

        settings = HistorySettingsManager()
        old_id = RequestHistoryService.record_send(
            identity={
                "request_id": None,
                "request_name": "",
                "method": "GET",
                "url": "http://old-filter.example",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "body": "x"},
            original_request=None,
            settings=settings,
        )
        new_id = RequestHistoryService.record_send(
            identity={
                "request_id": None,
                "request_name": "",
                "method": "GET",
                "url": "http://new-filter.example",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "body": "x"},
            original_request=None,
            settings=settings,
        )
        assert old_id is not None and new_id is not None
        today = datetime.now(tz=UTC).date()
        with get_session() as session:
            old_row = session.get(RequestHistoryEntryModel, old_id)
            assert old_row is not None
            old_row.executed_at = datetime.combine(
                today - timedelta(days=14),
                datetime.min.time(),
                tzinfo=UTC,
            )
            session.commit()

        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.show()
        panel.set_global_mode()
        panel.refresh()
        assert panel._tree_widget.topLevelItemCount() >= 2

        panel._toggle_date_range_filter(panel._date_filter_btn)
        qtbot.waitUntil(
            lambda: panel._date_filter_popup is not None and panel._date_filter_popup.isVisible(),
            timeout=3000,
        )
        popup = panel._date_filter_popup
        assert popup is not None
        from PySide6.QtCore import QDate

        popup._from_edit.setDate(QDate.currentDate().addDays(-1))
        popup._to_edit.setDate(QDate.currentDate())
        QTest.mouseClick(popup._apply_btn, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: panel._date_filter_btn.isChecked())

        item = find_history_tree_item(panel._tree_widget, new_id)
        assert item is not None
        assert find_history_tree_item(panel._tree_widget, old_id) is None
