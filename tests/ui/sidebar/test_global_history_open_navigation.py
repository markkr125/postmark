"""Tests for opening workspace history entries into request tabs."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from services.request_history_service import RequestHistoryService
from ui.main_window import MainWindow


class TestGlobalHistoryOpenNavigation:
    """MainWindow navigation from global history."""

    def test_open_existing_request_focuses_tab_not_center_response(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Opening a persisted send focuses the tab and right History, not centre viewer."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from database.models.collections.collection_repository import (
            create_new_collection,
            create_new_request,
        )
        from tests.ui.conftest import finish_main_window_startup
        from ui.styling.history_settings_manager import HistorySettingsManager

        coll = create_new_collection("C")
        req = create_new_request(coll.id, "GET", "http://nav.example", "NavReq")
        settings = HistorySettingsManager()
        entry_id = RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": "NavReq",
                "method": "GET",
                "url": "http://nav.example",
            },
            response={
                "status_code": 418,
                "elapsed_ms": 3.0,
                "headers": [{"key": "X-Test", "value": "1"}],
                "body": "teapot",
            },
            original_request={
                "method": "GET",
                "url": "http://nav.example",
                "name": "NavReq",
            },
            settings=settings,
        )
        assert entry_id is not None
        window = MainWindow()
        qtbot.addWidget(window)
        finish_main_window_startup(window)
        window._run_open_from_global_history(entry_id)
        qtbot.wait(100)
        ctx = window._tab_context_for_request_id(req.id)
        assert ctx is not None
        viewer = ctx.response_viewer
        assert viewer is not None
        assert "teapot" not in viewer._body_edit.toPlainText().lower()
        assert window._right_sidebar.active_panel == "request_history"
        assert window._request_history_panel._current_entry_id == entry_id

    def test_open_deleted_request_creates_draft(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Orphaned history opens a draft tab with editor prefilled."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from database.models.collections.collection_repository import (
            create_new_collection,
            create_new_request,
            delete_request,
        )
        from tests.ui.conftest import finish_main_window_startup
        from ui.styling.history_settings_manager import HistorySettingsManager

        coll = create_new_collection("C")
        req = create_new_request(coll.id, "GET", "http://orphan.example", "Gone")
        settings = HistorySettingsManager()
        entry_id = RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": "Gone",
                "method": "GET",
                "url": "http://orphan.example",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "body": "gone"},
            original_request={
                "method": "GET",
                "url": "http://orphan.example",
                "name": "Gone",
            },
            settings=settings,
        )
        delete_request(req.id)
        window = MainWindow()
        qtbot.addWidget(window)
        finish_main_window_startup(window)
        assert entry_id is not None
        window._run_open_from_global_history(entry_id)

        def _orphan_url_ready() -> bool:
            ctx = window._current_tab_context()
            return ctx is not None and "orphan.example" in ctx.require_editor()._url_input.text()

        qtbot.waitUntil(_orphan_url_ready, timeout=5000)
        ctx = window._current_tab_context()
        assert ctx is not None
        assert ctx.request_id is None
        editor = ctx.require_editor()
        assert editor.is_dirty
        assert "orphan.example" in editor._url_input.text()
        assert not window._right_sidebar._history_btn.isEnabled()
        assert ctx.draft_name == "Gone"
        crumb = window._breadcrumb_bar.last_segment_info
        assert crumb is not None
        assert crumb.get("name") == "Gone"
        viewer = ctx.response_viewer
        assert viewer is not None
        assert not viewer.has_live_response()
        assert not viewer._save_response_btn.isEnabled()

    def test_open_deleted_request_resolves_collection_variables_in_editor(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Orphan draft tabs push collection variables into the request editor."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from database.models.collections.collection_repository import (
            create_new_collection,
            create_new_request,
            delete_request,
        )
        from services.environment_service import EnvironmentService
        from tests.ui.conftest import finish_main_window_startup
        from ui.styling.history_settings_manager import HistorySettingsManager

        coll = create_new_collection("C")
        EnvironmentService.add_variable("collection", coll.id, "hg_api_key", "from-collection")
        req = create_new_request(coll.id, "GET", "http://orphan-vars.example", "Gone")
        settings = HistorySettingsManager()
        entry_id = RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": "Gone",
                "method": "GET",
                "url": "http://orphan-vars.example",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "body": "gone"},
            original_request={
                "method": "GET",
                "url": "http://orphan-vars.example",
                "name": "Gone",
                "collection_id": coll.id,
                "auth": {
                    "type": "bearer",
                    "bearer": [{"key": "token", "value": "{{hg_api_key}}", "enabled": True}],
                },
            },
            settings=settings,
        )
        delete_request(req.id)
        window = MainWindow()
        qtbot.addWidget(window)
        finish_main_window_startup(window)
        assert entry_id is not None
        window._run_open_from_global_history(entry_id)

        def _vars_ready() -> bool:
            ctx = window._current_tab_context()
            if ctx is None or ctx.editor is None:
                return False
            var_map = ctx.editor._bearer_token_input._variable_map
            return "hg_api_key" in var_map

        qtbot.waitUntil(_vars_ready, timeout=5000)
        ctx = window._current_tab_context()
        assert ctx is not None
        assert ctx.variable_collection_id == coll.id

    def test_open_orphan_does_not_overwrite_draft_when_tab_limit_blocks(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """When draft creation fails, an existing draft tab is not overwritten."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from tests.ui.conftest import finish_main_window_startup
        from ui.styling.history_settings_manager import HistorySettingsManager

        settings = HistorySettingsManager()
        entry_id = RequestHistoryService.record_send(
            identity={
                "request_id": None,
                "request_name": "Orphan",
                "method": "GET",
                "url": "http://orphan-blocked.example",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "body": "x"},
            original_request={
                "method": "GET",
                "url": "http://orphan-blocked.example",
                "name": "Orphan",
            },
            settings=settings,
        )
        assert entry_id is not None
        window = MainWindow()
        qtbot.addWidget(window)
        finish_main_window_startup(window)
        window._open_draft_request()
        ctx = window._current_tab_context()
        assert ctx is not None
        editor = ctx.require_editor()
        editor._url_input.setText("keep-this-draft")
        monkeypatch.setattr(window, "_enforce_tab_limit_before_open", lambda: False)
        window._run_open_from_global_history(entry_id)
        qtbot.wait(50)
        assert editor._url_input.text() == "keep-this-draft"

    def test_open_existing_blocked_while_sending(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Global open does not replace response while a send is in flight."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from database.models.collections.collection_repository import (
            create_new_collection,
            create_new_request,
        )
        from tests.ui.conftest import finish_main_window_startup
        from ui.styling.history_settings_manager import HistorySettingsManager

        coll = create_new_collection("C")
        req = create_new_request(coll.id, "GET", "http://sending.example", "Send")
        settings = HistorySettingsManager()
        entry_id = RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": "Send",
                "method": "GET",
                "url": "http://sending.example",
            },
            response={"status_code": 200, "elapsed_ms": 1.0, "body": "ok"},
            original_request={"method": "GET", "url": "http://sending.example"},
            settings=settings,
        )
        assert entry_id is not None
        window = MainWindow()
        qtbot.addWidget(window)
        finish_main_window_startup(window)
        window._open_request(req.id, push_history=False)
        ctx = window._tab_context_for_request_id(req.id)
        assert ctx is not None
        ctx.is_sending = True
        window._run_open_from_global_history(entry_id)
        qtbot.wait(50)
        viewer = ctx.response_viewer
        assert viewer is not None
        assert not viewer.has_live_response()

    def test_stale_request_id_opens_draft(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """When request_id is set but get_request fails, open as draft."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from tests.ui.conftest import finish_main_window_startup
        from ui.styling.history_settings_manager import HistorySettingsManager

        settings = HistorySettingsManager()
        entry_id = RequestHistoryService.record_send(
            identity={
                "request_id": 999_999,
                "request_name": "Ghost",
                "method": "GET",
                "url": "http://ghost.example",
            },
            response={"status_code": 404, "elapsed_ms": 1.0, "body": "nf"},
            original_request={
                "method": "GET",
                "url": "http://ghost.example",
                "name": "Ghost",
            },
            settings=settings,
        )
        assert entry_id is not None
        window = MainWindow()
        qtbot.addWidget(window)
        finish_main_window_startup(window)
        window._run_open_from_global_history(entry_id)
        qtbot.wait(100)
        ctx = window._current_tab_context()
        assert ctx is not None
        assert ctx.request_id is None
        assert "ghost.example" in ctx.require_editor()._url_input.text()

    def test_record_send_refreshes_global_panel(
        self,
        tmp_path,
        monkeypatch,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """on_send_finished refresh path updates the global history list."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        from tests.ui.conftest import finish_main_window_startup
        from ui.main_window.send_pipeline_postresponse import _record_request_history
        from ui.styling.history_settings_manager import HistorySettingsManager

        window = MainWindow()
        qtbot.addWidget(window)
        finish_main_window_startup(window)
        window._history_settings = HistorySettingsManager()
        window._pending_history_context = {
            "request_id": None,
            "request_name": "",
            "method": "POST",
            "url": "http://refresh-global.example",
            "tab_type": "request",
        }
        panel = window._global_history_panel
        panel.refresh()
        before = len(panel._items)
        _record_request_history(
            window,
            None,
            {
                "status_code": 204,
                "elapsed_ms": 2.0,
                "body": "created",
                "request_method": "POST",
                "request_url": "http://refresh-global.example",
            },
        )
        assert len(panel._items) == before + 1
