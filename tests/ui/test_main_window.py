"""Smoke tests for the top-level MainWindow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from services.collection_service import CollectionService
from ui.collections.collection_widget import CollectionWidget
from ui.main_window import MainWindow
from ui.request.request_editor import RequestEditorWidget
from ui.request.response_viewer import ResponseViewerWidget
from ui.styling.tab_settings_manager import TabSettingsManager


class TestMainWindow:
    """Smoke tests for the top-level application window."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """MainWindow can be instantiated without errors."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert window.windowTitle() == "Postmark"

    def test_has_collection_widget(self, qapp: QApplication, qtbot) -> None:
        """MainWindow contains a CollectionWidget."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert isinstance(window.collection_widget, CollectionWidget)

    def test_menu_bar_exists(self, qapp: QApplication, qtbot) -> None:
        """MainWindow has a menu bar with File and Collection menus."""
        window = MainWindow()
        qtbot.addWidget(window)

        menubar = window.menuBar()
        menu_titles = [a.text() for a in menubar.actions()]
        assert "&File" in menu_titles
        assert "&Collection" in menu_titles

    def test_file_menu_has_settings(self, qapp: QApplication, qtbot) -> None:
        """File menu contains a Settings action."""
        window = MainWindow()
        qtbot.addWidget(window)

        menubar = window.menuBar()
        assert menubar is not None
        file_menu = None
        for action in menubar.actions():
            if action.text() == "&File":
                file_menu = action.menu()
                break
        assert file_menu is not None
        action_texts = [a.text() for a in file_menu.actions()]  # type: ignore[attr-defined]
        assert "&Settings\u2026" in action_texts

    def test_request_editor_is_request_editor_widget(self, qapp: QApplication, qtbot) -> None:
        """MainWindow uses RequestEditorWidget for the request pane."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert isinstance(window.request_widget, RequestEditorWidget)

    def test_response_viewer_is_response_viewer_widget(self, qapp: QApplication, qtbot) -> None:
        """MainWindow uses ResponseViewerWidget for the response pane."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert isinstance(window.response_widget, ResponseViewerWidget)

    def test_back_forward_initially_disabled(self, qapp: QApplication, qtbot) -> None:
        """Back and forward actions start disabled."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert not window.back_action.isEnabled()
        assert not window.forward_action.isEnabled()

    def test_loading_screen_transitions_to_main_ui(self, qapp: QApplication, qtbot) -> None:
        """MainWindow starts on loading screen and switches when load finishes."""
        window = MainWindow()
        qtbot.addWidget(window)

        # Initially on loading screen (index 0)
        assert window._main_stack.currentIndex() == 0
        assert window.menuBar().isHidden()

        # Simulate load finished
        window.collection_widget.load_finished.emit()

        # Switches to main UI (index 1)
        assert window._main_stack.currentIndex() == 1
        assert not window.menuBar().isHidden()


class TestMainWindowNavigation:
    """Tests for request open and back/forward navigation."""

    def test_open_request_loads_editor(self, qapp: QApplication, qtbot) -> None:
        """Opening a request populates the request editor."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "POST", "https://example.com", "My Req")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req.id, push_history=True)

        assert window.request_widget._url_input.text() == "https://example.com"
        assert window.request_widget._method_combo.currentText() == "POST"

    def test_navigation_history_back(self, qapp: QApplication, qtbot) -> None:
        """Navigating back goes to the previous request."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://a.com", "Req1")
        req2 = svc.create_request(coll.id, "GET", "http://b.com", "Req2")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req1.id, push_history=True)
        window._open_request(req2.id, push_history=True)

        assert window.back_action.isEnabled()
        window._navigate_back()

        assert window.request_widget._url_input.text() == "http://a.com"
        assert window.forward_action.isEnabled()

    def test_navigation_history_forward(self, qapp: QApplication, qtbot) -> None:
        """Navigating forward goes to the next request."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://a.com", "Req1")
        req2 = svc.create_request(coll.id, "GET", "http://b.com", "Req2")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req1.id, push_history=True)
        window._open_request(req2.id, push_history=True)
        window._navigate_back()
        window._navigate_forward()

        assert window.request_widget._url_input.text() == "http://b.com"

    def test_item_action_open_triggers_editor(self, qapp: QApplication, qtbot) -> None:
        """Emitting item_action_triggered with 'Open' loads the editor."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "PUT", "http://c.com", "EditReq")

        window = MainWindow()
        qtbot.addWidget(window)

        window.collection_widget.item_action_triggered.emit("request", req.id, "Open")

        assert window.request_widget._url_input.text() == "http://c.com"

    def test_preview_setting_can_disable_preview_tabs(self, qapp: QApplication, qtbot) -> None:
        """When preview tabs are disabled, Preview opens a permanent tab."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://preview-off.com", "Preview Off")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.enable_preview_tab = False

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window.collection_widget.item_action_triggered.emit("request", req.id, "Preview")

        assert window._tab_bar.count() == 1
        assert not window._tabs[0].is_preview

    def test_tab_limit_closes_least_recently_used_safe_tab(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Opening past the tab limit closes the least-recently-used safe tab."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://one.com", "One")
        req2 = svc.create_request(coll.id, "GET", "http://two.com", "Two")
        req3 = svc.create_request(coll.id, "GET", "http://three.com", "Three")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.tab_limit = 2
        tab_settings.tab_limit_policy = "close_unused"

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window._open_request(req1.id, push_history=True)
        window._open_request(req2.id, push_history=True)
        window._open_request(req3.id, push_history=True)

        open_request_ids = {ctx.request_id for ctx in window._tabs.values()}
        assert window._tab_bar.count() == 2
        assert req1.id not in open_request_ids
        assert req2.id in open_request_ids
        assert req3.id in open_request_ids

    def test_close_unchanged_protects_dirty_tabs(self, qapp: QApplication, qtbot) -> None:
        """The close-unchanged policy skips tabs with unsaved edits."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://one.com", "One")
        req2 = svc.create_request(coll.id, "GET", "http://two.com", "Two")
        req3 = svc.create_request(coll.id, "GET", "http://three.com", "Three")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.tab_limit = 2
        tab_settings.tab_limit_policy = "close_unchanged"

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window._open_request(req1.id, push_history=True)
        window._open_request(req2.id, push_history=True)
        window._tab_bar.setCurrentIndex(0)
        window._tabs[0].editor._set_dirty(True)

        window._open_request(req3.id, push_history=True)

        open_request_ids = {ctx.request_id for ctx in window._tabs.values()}
        assert req1.id in open_request_ids
        assert req2.id not in open_request_ids
        assert req3.id in open_request_ids

    def test_close_unchanged_respects_manual_reorder(self, qapp: QApplication, qtbot) -> None:
        """Manual tab reordering changes which unchanged tab is evicted first."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://one.com", "One")
        req2 = svc.create_request(coll.id, "GET", "http://two.com", "Two")
        req3 = svc.create_request(coll.id, "GET", "http://three.com", "Three")
        req4 = svc.create_request(coll.id, "GET", "http://four.com", "Four")

        tab_settings = TabSettingsManager(qapp)
        tab_settings.tab_limit = 3
        tab_settings.tab_limit_policy = "close_unchanged"

        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        window._open_request(req1.id, push_history=True)
        window._open_request(req2.id, push_history=True)
        window._open_request(req3.id, push_history=True)

        window._tab_bar.move_tab(1, 0)
        window._open_request(req4.id, push_history=True)

        open_request_ids = {ctx.request_id for ctx in window._tabs.values()}
        assert req2.id not in open_request_ids
        assert req1.id in open_request_ids
        assert req3.id in open_request_ids
        assert req4.id in open_request_ids


class TestMainWindowSendRequest:
    """Tests for the HTTP send pipeline wiring."""

    def test_send_with_empty_url_shows_error(self, qapp: QApplication, qtbot) -> None:
        """Sending with an empty URL shows an error in the response viewer."""
        window = MainWindow()
        qtbot.addWidget(window)

        window.request_widget._url_input.setText("")
        window._on_send_request()

        assert not window.response_widget._error_label.isHidden()
        assert "empty" in window.response_widget._error_label.text().lower()

    @patch("ui.request.http_worker.HttpSendWorker")
    @patch("ui.main_window.send_pipeline.QThread")
    def test_send_creates_worker_and_thread(
        self,
        mock_thread_cls: MagicMock,
        mock_worker_cls: MagicMock,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Sending a request creates a worker and thread."""
        mock_worker = MagicMock()
        mock_worker.finished = MagicMock()
        mock_worker.error = MagicMock()
        mock_worker_cls.return_value = mock_worker

        mock_thread = MagicMock()
        mock_thread.started = MagicMock()
        mock_thread.isRunning.return_value = False
        mock_thread_cls.return_value = mock_thread

        window = MainWindow()
        qtbot.addWidget(window)

        window.request_widget._url_input.setText("http://example.com")
        window.request_widget._method_combo.setCurrentText("GET")
        window._on_send_request()

        mock_worker.set_request.assert_called_once()
        mock_worker.moveToThread.assert_called_once_with(mock_thread)
        mock_thread.start.assert_called_once()

    def test_on_send_finished_populates_response(self, qapp: QApplication, qtbot) -> None:
        """Receiving a finished signal populates the response viewer."""
        window = MainWindow()
        qtbot.addWidget(window)

        data = {
            "status_code": 200,
            "status_text": "OK",
            "headers": [],
            "body": "hello",
            "elapsed_ms": 10.0,
            "size_bytes": 5,
        }
        window._on_send_finished(data)

        assert "200" in window.response_widget._status_label.text()
        assert window.response_widget._body_edit.toPlainText() == "hello"

    def test_on_send_error_shows_error(self, qapp: QApplication, qtbot) -> None:
        """Receiving an error signal shows the error state."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._on_send_error("Connection refused")

        assert not window.response_widget._error_label.isHidden()
        assert "Connection refused" in window.response_widget._error_label.text()

    def test_send_disables_button(self, qapp: QApplication, qtbot) -> None:
        """The Send button switches to Cancel while a request is in flight."""
        window = MainWindow()
        qtbot.addWidget(window)

        window.request_widget._url_input.setText("http://example.com")

        # Directly simulate what _on_send_request does to the button
        window._set_send_button_cancel(True)
        assert window.request_widget._send_btn.text() == "Cancel"

        # Simulate finished callback
        window._on_send_finished(
            {
                "status_code": 200,
                "status_text": "OK",
                "headers": [],
                "body": "",
                "elapsed_ms": 1.0,
                "size_bytes": 0,
            }
        )
        assert window.request_widget._send_btn.text() == "Send"

    def test_cleanup_send_thread(self, qapp: QApplication, qtbot) -> None:
        """Cleanup releases thread and worker references."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._send_thread = MagicMock()
        window._send_thread.isRunning.return_value = False
        window._send_worker = MagicMock()

        window._cleanup_send_thread()

        assert window._send_thread is None
        assert window._send_worker is None

    def test_cancel_send_shows_cancelled_message(self, qapp: QApplication, qtbot) -> None:
        """Cancelling a send shows the cancelled error message."""
        window = MainWindow()
        qtbot.addWidget(window)

        mock_worker = MagicMock()
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True
        window._send_worker = mock_worker
        window._send_thread = mock_thread

        window._cancel_send()

        mock_worker.cancel.assert_called_once()
        assert "cancelled" in window.response_widget._error_label.text().lower()
        assert window.request_widget._send_btn.text() == "Send"
        assert window._send_thread is None
        assert window._send_worker is None

    def test_send_button_toggles_to_cancel(self, qapp: QApplication, qtbot) -> None:
        """The button text toggles between Send and Cancel."""
        window = MainWindow()
        qtbot.addWidget(window)

        assert window.request_widget._send_btn.text() == "Send"
        window._set_send_button_cancel(True)
        assert window.request_widget._send_btn.text() == "Cancel"
        window._set_send_button_cancel(False)
        assert window.request_widget._send_btn.text() == "Send"


class TestMainWindowViewToggles:
    """Tests for the View menu toggle actions."""

    def test_view_menu_exists(self, qapp: QApplication, qtbot) -> None:
        """MainWindow has a View menu."""
        window = MainWindow()
        qtbot.addWidget(window)
        menubar = window.menuBar()
        menu_titles = [a.text() for a in menubar.actions()]
        assert "&View" in menu_titles

    def test_toggle_response_pane(self, qapp: QApplication, qtbot) -> None:
        """Toggling the response pane hides and shows it."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert not window._response_area.isHidden()
        window._toggle_response_pane()
        assert window._response_area.isHidden()
        window._toggle_response_pane()
        assert not window._response_area.isHidden()

    def test_toggle_sidebar(self, qapp: QApplication, qtbot) -> None:
        """Toggling the sidebar hides and shows the collection widget."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert not window.collection_widget.isHidden()
        window._toggle_sidebar()
        assert window.collection_widget.isHidden()
        window._toggle_sidebar()
        assert not window.collection_widget.isHidden()

    def test_toggle_bottom_panel(self, qapp: QApplication, qtbot) -> None:
        """Toggling the bottom panel hides and shows it."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert window._bottom_panel.isHidden()
        window._toggle_bottom_panel()
        assert not window._bottom_panel.isHidden()
        window._toggle_bottom_panel()
        assert window._bottom_panel.isHidden()

    def test_toggle_layout_orientation(self, qapp: QApplication, qtbot) -> None:
        """Toggling layout switches the right splitter between vertical and horizontal."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert window._right_splitter.orientation() == Qt.Orientation.Vertical
        window._toggle_layout_orientation()
        assert window._right_splitter.orientation() == Qt.Orientation.Horizontal
        window._toggle_layout_orientation()
        assert window._right_splitter.orientation() == Qt.Orientation.Vertical


class TestMainWindowTabBugFix:
    """Tests verifying the multi-tab bug is fixed."""

    def test_open_creates_permanent_tab(self, qapp: QApplication, qtbot) -> None:
        """Opening a request via Open action creates a permanent tab."""
        svc = CollectionService()
        coll = svc.create_collection("C")
        req = svc.create_request(coll.id, "GET", "http://example.com", "R")

        window = MainWindow()
        qtbot.addWidget(window)
        window._open_request(req.id, push_history=True, is_preview=False)

        ctx = window._tabs.get(0)
        assert ctx is not None
        assert ctx.is_preview is False

    def test_multiple_permanent_tabs(self, qapp: QApplication, qtbot) -> None:
        """Multiple permanent tabs can be opened simultaneously."""
        svc = CollectionService()
        coll = svc.create_collection("C")
        req1 = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req2 = svc.create_request(coll.id, "POST", "http://b.com", "B")

        window = MainWindow()
        qtbot.addWidget(window)
        window._open_request(req1.id, push_history=True, is_preview=False)
        window._open_request(req2.id, push_history=True, is_preview=False)

        assert window._tab_bar.count() == 2

    def test_preview_promoted_on_open(self, qapp: QApplication, qtbot) -> None:
        """A preview tab is promoted when the same request is opened permanently."""
        svc = CollectionService()
        coll = svc.create_collection("C")
        req = svc.create_request(coll.id, "GET", "http://x.com", "X")

        window = MainWindow()
        qtbot.addWidget(window)
        window._open_request(req.id, push_history=True, is_preview=True)
        ctx = window._tabs.get(0)
        assert ctx is not None
        assert ctx.is_preview is True

        # Open the same request permanently — should promote, not create new
        window._open_request(req.id, push_history=True, is_preview=False)
        assert window._tab_bar.count() == 1
        assert ctx.is_preview is False


class TestMainWindowCloseEvent:
    """Tests for MainWindow.closeEvent cleanup."""

    def test_close_cleans_up_tabs(self, qapp: QApplication, qtbot) -> None:
        """Closing the main window calls cleanup on all tab contexts."""
        svc = CollectionService()
        coll = svc.create_collection("C")
        req = svc.create_request(coll.id, "GET", "http://x.com", "R")

        window = MainWindow()
        qtbot.addWidget(window)
        window._open_request(req.id, push_history=True)
        window.close()
        # Verify console handler removed (closeEvent calls cleanup)
        assert window._console_panel._handler not in __import__("logging").getLogger().handlers


class TestMainWindowContextMenuHandlers:
    """Tests for tab context menu handler methods."""

    def test_close_others(self, qapp: QApplication, qtbot) -> None:
        """Close Others closes all tabs except the specified one."""
        svc = CollectionService()
        coll = svc.create_collection("C")
        req1 = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req2 = svc.create_request(coll.id, "POST", "http://b.com", "B")
        req3 = svc.create_request(coll.id, "PUT", "http://c.com", "C")

        window = MainWindow()
        qtbot.addWidget(window)
        window._open_request(req1.id, push_history=True)
        window._open_request(req2.id, push_history=True)
        window._open_request(req3.id, push_history=True)
        assert window._tab_bar.count() == 3

        window._close_others_tabs(1)
        assert window._tab_bar.count() == 1

    def test_close_all(self, qapp: QApplication, qtbot) -> None:
        """Close All closes every tab."""
        svc = CollectionService()
        coll = svc.create_collection("C")
        req1 = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req2 = svc.create_request(coll.id, "POST", "http://b.com", "B")

        window = MainWindow()
        qtbot.addWidget(window)
        window._open_request(req1.id, push_history=True)
        window._open_request(req2.id, push_history=True)
        assert window._tab_bar.count() == 2

        window._close_all_tabs()
        assert window._tab_bar.count() == 0


class TestMainWindowRightSidebar:
    """Tests for the right sidebar icon rail and flyout panels."""

    def test_toggle_right_sidebar(self, qapp: QApplication, qtbot) -> None:
        """Toggling the right sidebar opens and closes the panel."""
        window = MainWindow()
        qtbot.addWidget(window)
        # Sidebar starts with no panel open
        assert not window._right_sidebar.panel_open

        # Need a tab context to enable panels
        svc = CollectionService()
        coll = svc.create_collection("C")
        req = svc.create_request(coll.id, "GET", "http://x", "R")
        window._open_request(req.id, push_history=True)

        # No auto-open; sidebar should still be closed.
        assert not window._right_sidebar.panel_open
        window._toggle_right_sidebar()
        assert window._right_sidebar.panel_open
        window._toggle_right_sidebar()
        assert not window._right_sidebar.panel_open

    def test_sidebar_rail_always_visible(self, qapp: QApplication, qtbot) -> None:
        """The icon rail is not hidden — it is always present in the layout."""
        window = MainWindow()
        qtbot.addWidget(window)
        # The sidebar itself is not explicitly hidden
        assert not window._right_sidebar.isHidden()
        # The rail inside the sidebar is not hidden either
        assert not window._right_sidebar._rail.isHidden()

    def test_sidebar_shows_request_panels_on_tab_switch(self, qapp: QApplication, qtbot) -> None:
        """Switching to a request tab enables both sidebar icons."""
        svc = CollectionService()
        coll = svc.create_collection("C")
        req = svc.create_request(coll.id, "GET", "http://example.com", "R")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req.id, push_history=True)

        assert window._right_sidebar._var_btn.isEnabled()
        assert not window._right_sidebar._snippet_btn.isHidden()

    def test_sidebar_shows_folder_panels_on_tab_switch(self, qapp: QApplication, qtbot) -> None:
        """Switching to a folder tab enables variables but disables snippet."""
        svc = CollectionService()
        coll = svc.create_collection("Folder")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_folder(coll.id)

        assert window._right_sidebar._var_btn.isEnabled()
        assert window._right_sidebar._snippet_btn.isHidden()

    def test_sidebar_clears_when_no_tab(self, qapp: QApplication, qtbot) -> None:
        """Closing all tabs disables sidebar icons."""
        svc = CollectionService()
        coll = svc.create_collection("C")
        req = svc.create_request(coll.id, "GET", "http://x", "R")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req.id, push_history=True)
        assert window._right_sidebar._var_btn.isEnabled()

        window._on_tab_close(0)
        assert not window._right_sidebar._var_btn.isEnabled()
        assert window._right_sidebar._snippet_btn.isHidden()


class TestMainWindowFolderTabs:
    """Tests for opening and closing folder tabs."""

    def test_open_folder_creates_tab(self, qapp: QApplication, qtbot) -> None:
        """Opening a folder creates a new tab in the tab bar."""
        svc = CollectionService()
        coll = svc.create_collection("MyFolder")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_folder(coll.id)

        assert window._tab_bar.count() == 1
        ctx = window._tabs[0]
        assert ctx.tab_type == "folder"
        assert ctx.collection_id == coll.id

    def test_open_folder_shows_editor(self, qapp: QApplication, qtbot) -> None:
        """Opening a folder shows the folder editor widget."""
        svc = CollectionService()
        coll = svc.create_collection("Folder")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_folder(coll.id)

        ctx = window._tabs[0]
        assert ctx.folder_editor is not None
        assert ctx.folder_editor._title_label.text() == "Folder"

    def test_open_same_folder_twice_switches_tab(self, qapp: QApplication, qtbot) -> None:
        """Opening the same folder twice switches to the existing tab."""
        svc = CollectionService()
        coll = svc.create_collection("Folder")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_folder(coll.id)
        window._open_folder(coll.id)

        assert window._tab_bar.count() == 1

    def test_close_folder_tab(self, qapp: QApplication, qtbot) -> None:
        """Closing a folder tab removes it cleanly."""
        svc = CollectionService()
        coll = svc.create_collection("Folder")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_folder(coll.id)
        assert window._tab_bar.count() == 1

        window._on_tab_close(0)
        assert window._tab_bar.count() == 0

    def test_folder_and_request_tabs_coexist(self, qapp: QApplication, qtbot) -> None:
        """Folder and request tabs can coexist in the tab bar."""
        svc = CollectionService()
        coll = svc.create_collection("Folder")
        req = svc.create_request(coll.id, "GET", "http://x", "Req")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req.id, push_history=True)
        window._open_folder(coll.id)

        assert window._tab_bar.count() == 2
        assert window._tabs[0].tab_type == "request"
        assert window._tabs[1].tab_type == "folder"
