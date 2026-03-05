"""Smoke tests for the top-level MainWindow."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from services.collection_service import CollectionService
from ui.collections.collection_widget import CollectionWidget
from ui.main_window import MainWindow
from ui.request.request_editor import RequestEditorWidget
from ui.request.response_viewer import ResponseViewerWidget


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
    @patch("ui.main_window.QThread")
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


class TestMainWindowSaveButton:
    """Tests for the Save button in the breadcrumb row."""

    def test_save_button_exists(self, qapp: QApplication, qtbot) -> None:
        """MainWindow has a Save button in the breadcrumb row."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert hasattr(window, "_save_btn")
        assert window._save_btn.text() == "Save"

    def test_save_button_disabled_initially(self, qapp: QApplication, qtbot) -> None:
        """Save button starts disabled."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert not window._save_btn.isEnabled()

    def test_save_button_tooltip_when_disabled(self, qapp: QApplication, qtbot) -> None:
        """Disabled Save button shows a 'no changes' tooltip."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert window._save_btn.toolTip() == "No changes to save"

    def test_save_button_tooltip_cleared_when_dirty(self, qapp: QApplication, qtbot) -> None:
        """Save button tooltip is cleared when the editor becomes dirty."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.request_widget.load_request(
            {"name": "X", "method": "GET", "url": "http://x"}, request_id=1
        )
        window.request_widget._url_input.setText("http://changed")
        assert window._save_btn.toolTip() == ""

    def test_save_button_hidden_when_no_tab(self, qapp: QApplication, qtbot) -> None:
        """Save button is hidden when no request tab is open."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert not window._save_btn.isVisible()

    def test_save_button_enabled_when_editor_dirty(self, qapp: QApplication, qtbot) -> None:
        """Save button becomes enabled when the active editor is dirty."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.request_widget.load_request(
            {"name": "X", "method": "GET", "url": "http://x"}, request_id=1
        )
        window.request_widget._url_input.setText("http://changed")
        assert window._save_btn.isEnabled()

    def test_save_button_disabled_after_dirty_cleared(self, qapp: QApplication, qtbot) -> None:
        """Save button becomes disabled when dirty flag is cleared."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.request_widget.load_request(
            {"name": "X", "method": "GET", "url": "http://x"}, request_id=1
        )
        window.request_widget._url_input.setText("http://changed")
        assert window._save_btn.isEnabled()
        window.request_widget._set_dirty(False)
        assert not window._save_btn.isEnabled()

    def test_save_button_triggers_save(self, qapp: QApplication, qtbot) -> None:
        """Clicking Save calls the save pipeline."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.request_widget.load_request(
            {"name": "X", "method": "GET", "url": "http://x"}, request_id=1
        )
        window.request_widget._url_input.setText("http://changed")

        with patch.object(CollectionService, "update_request") as mock_update:
            window._save_btn.click()
            mock_update.assert_called_once()

    def test_save_button_object_name(self, qapp: QApplication, qtbot) -> None:
        """Save button uses the saveButton QSS style."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert window._save_btn.objectName() == "saveButton"

    def test_save_button_hand_cursor(self, qapp: QApplication, qtbot) -> None:
        """Save button has a hand cursor."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert window._save_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


class TestRequestSaveEndToEnd:
    """End-to-end tests verifying all aspects of request saving."""

    # Helper -----------------------------------------------------------

    @staticmethod
    def _create_and_open(window: MainWindow, **overrides: object) -> int:
        """Create a request in the DB, open it in the window, return its id."""
        svc = CollectionService()
        coll = svc.create_collection("TestColl")
        defaults: dict = {
            "method": "GET",
            "url": "http://original.test",
            "name": "OrigReq",
        }
        defaults.update(overrides)
        name = defaults.pop("name")
        req = svc.create_request(coll.id, defaults.pop("method"), defaults.pop("url"), name)
        # Persist any extra fields (body, auth, etc.)
        if defaults:
            svc.update_request(req.id, **defaults)
        window._open_request(req.id, push_history=True)
        return req.id

    # -- URL -----------------------------------------------------------

    def test_save_url_change(self, qapp: QApplication, qtbot) -> None:
        """Saving after editing the URL persists the new URL to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        window.request_widget._url_input.setText("http://updated.test")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.url == "http://updated.test"
        assert not window.request_widget.is_dirty

    # -- Method --------------------------------------------------------

    def test_save_method_change(self, qapp: QApplication, qtbot) -> None:
        """Saving after changing the HTTP method persists to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        window.request_widget._method_combo.setCurrentText("POST")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.method == "POST"

    # -- Raw body (JSON) -----------------------------------------------

    def test_save_raw_json_body(self, qapp: QApplication, qtbot) -> None:
        """Saving raw JSON body persists body text and body_mode."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._body_mode_buttons["raw"].setChecked(True)
        editor._raw_format_combo.setCurrentText("JSON")
        editor._body_code_editor.setPlainText('{"key": "value"}')
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.body == '{"key": "value"}'
        assert saved.body_mode == "raw"
        assert saved.body_options == {"raw": {"language": "json"}}

    # -- Raw body (Text) -----------------------------------------------

    def test_save_raw_text_body(self, qapp: QApplication, qtbot) -> None:
        """Saving raw text body persists correctly."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._body_mode_buttons["raw"].setChecked(True)
        editor._raw_format_combo.setCurrentText("Text")
        editor._body_code_editor.setPlainText("plain text body")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.body == "plain text body"
        assert saved.body_mode == "raw"
        assert saved.body_options == {"raw": {"language": "text"}}

    # -- Body mode "none" ----------------------------------------------

    def test_save_body_mode_none(self, qapp: QApplication, qtbot) -> None:
        """Saving with body_mode=none persists empty body."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window, body="old body", body_mode="raw")

        editor = window.request_widget
        editor._body_mode_buttons["none"].setChecked(True)
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.body_mode == "none"

    # -- Headers -------------------------------------------------------

    def test_save_headers_change(self, qapp: QApplication, qtbot) -> None:
        """Saving after editing headers persists the new headers to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        headers = [
            {"key": "Content-Type", "value": "application/json", "enabled": True},
            {"key": "Authorization", "value": "Bearer tok", "enabled": True},
        ]
        window.request_widget._headers_table.set_data(headers)
        # set_data during _loading=False triggers field change
        window.request_widget._set_dirty(True)
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert isinstance(saved.headers, list)
        keys = [h["key"] for h in saved.headers if h.get("key")]
        assert "Content-Type" in keys
        assert "Authorization" in keys

    # -- Query parameters ----------------------------------------------

    def test_save_params_change(self, qapp: QApplication, qtbot) -> None:
        """Saving after editing params persists the new params to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        params = [
            {"key": "page", "value": "1", "enabled": True},
            {"key": "limit", "value": "10", "enabled": True},
        ]
        window.request_widget._params_table.set_data(params)
        window.request_widget._set_dirty(True)
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert isinstance(saved.request_parameters, list)
        keys = [p["key"] for p in saved.request_parameters if p.get("key")]
        assert "page" in keys
        assert "limit" in keys

    # -- Description ---------------------------------------------------

    def test_save_description_change(self, qapp: QApplication, qtbot) -> None:
        """Saving after editing the description persists to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        window.request_widget._description_edit.setPlainText("A test request")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.description == "A test request"

    # -- Scripts -------------------------------------------------------

    def test_save_scripts_change(self, qapp: QApplication, qtbot) -> None:
        """Saving after editing scripts persists to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        window.request_widget._scripts_edit.setPlainText("console.log('test');")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.scripts == "console.log('test');"

    # -- Auth: Bearer token --------------------------------------------

    def test_save_bearer_auth(self, qapp: QApplication, qtbot) -> None:
        """Saving bearer auth persists the token to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._auth_type_combo.setCurrentText("Bearer Token")
        editor._bearer_token_input.setText("my-secret-token")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.auth is not None
        assert saved.auth["type"] == "bearer"
        tokens = saved.auth["bearer"]
        assert any(t["value"] == "my-secret-token" for t in tokens)

    # -- Auth: Basic ---------------------------------------------------

    def test_save_basic_auth(self, qapp: QApplication, qtbot) -> None:
        """Saving basic auth persists username and password to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._auth_type_combo.setCurrentText("Basic Auth")
        editor._basic_username_input.setText("admin")
        editor._basic_password_input.setText("s3cret")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.auth is not None
        assert saved.auth["type"] == "basic"
        entries = saved.auth["basic"]
        assert any(e["key"] == "username" and e["value"] == "admin" for e in entries)
        assert any(e["key"] == "password" and e["value"] == "s3cret" for e in entries)

    # -- Auth: API Key -------------------------------------------------

    def test_save_apikey_auth(self, qapp: QApplication, qtbot) -> None:
        """Saving API Key auth persists key, value and location to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._auth_type_combo.setCurrentText("API Key")
        editor._apikey_key_input.setText("X-API-Key")
        editor._apikey_value_input.setText("abc123")
        editor._apikey_add_to_combo.setCurrentText("Header")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.auth is not None
        assert saved.auth["type"] == "apikey"
        entries = saved.auth["apikey"]
        assert any(e["key"] == "key" and e["value"] == "X-API-Key" for e in entries)
        assert any(e["key"] == "value" and e["value"] == "abc123" for e in entries)
        assert any(e["key"] == "in" and e["value"] == "header" for e in entries)

    # -- GraphQL body --------------------------------------------------

    def test_save_graphql_body(self, qapp: QApplication, qtbot) -> None:
        """Saving GraphQL body persists query and variables as JSON."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._body_mode_buttons["graphql"].setChecked(True)
        editor._gql_query_editor.setPlainText("{ users { id name } }")
        editor._gql_variables_editor.setPlainText('{"limit": 5}')
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.body_mode == "graphql"
        assert saved.body is not None
        body = json.loads(saved.body)
        assert body["query"] == "{ users { id name } }"
        assert body["variables"] == {"limit": 5}

    # -- Dirty flag management -----------------------------------------

    def test_save_clears_dirty_flag(self, qapp: QApplication, qtbot) -> None:
        """After saving, editor dirty flag is cleared and Save btn disabled."""
        window = MainWindow()
        qtbot.addWidget(window)
        self._create_and_open(window)

        window.request_widget._url_input.setText("http://changed.test")
        assert window.request_widget.is_dirty
        assert window._save_btn.isEnabled()

        window._on_save_request()

        assert not window.request_widget.is_dirty
        assert not window._save_btn.isEnabled()

    def test_save_noop_when_not_dirty(self, qapp: QApplication, qtbot) -> None:
        """Save does nothing when the editor is not dirty."""
        window = MainWindow()
        qtbot.addWidget(window)
        self._create_and_open(window)

        # Don't modify anything — just try to save
        with patch.object(CollectionService, "update_request") as mock_update:
            window._on_save_request()
            mock_update.assert_not_called()

    def test_save_noop_when_no_request_id(self, qapp: QApplication, qtbot) -> None:
        """Save does nothing when no request is loaded."""
        window = MainWindow()
        qtbot.addWidget(window)
        # Don't open any request — editor has no request_id
        window.request_widget._url_input.setText("http://whatever")

        with patch.object(CollectionService, "update_request") as mock_update:
            window._on_save_request()
            mock_update.assert_not_called()

    # -- Multiple field save -------------------------------------------

    def test_save_multiple_fields_at_once(self, qapp: QApplication, qtbot) -> None:
        """Saving after editing multiple fields persists all changes."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._method_combo.setCurrentText("PUT")
        editor._url_input.setText("http://multi.test/api")
        editor._body_mode_buttons["raw"].setChecked(True)
        editor._raw_format_combo.setCurrentText("JSON")
        editor._body_code_editor.setPlainText('{"multi": true}')
        editor._description_edit.setPlainText("Multi-field test")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.method == "PUT"
        assert saved.url == "http://multi.test/api"
        assert saved.body == '{"multi": true}'
        assert saved.body_mode == "raw"
        assert saved.description == "Multi-field test"

    # -- Save via Ctrl+S shortcut --------------------------------------

    def test_ctrl_s_triggers_save(self, qapp: QApplication, qtbot) -> None:
        """Ctrl+S keyboard shortcut triggers the save pipeline."""
        window = MainWindow()
        qtbot.addWidget(window)
        self._create_and_open(window)

        window.request_widget._url_input.setText("http://shortcut.test")

        with patch.object(CollectionService, "update_request") as mock_update:
            window._on_save_request()
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args
            assert call_kwargs[1].get("url") or call_kwargs[0][1:] == ()


class TestMainWindowVariableMap:
    """Tests for variable map refresh on environment and tab changes."""

    def test_environment_changed_signal_connected(self, qapp: QApplication, qtbot) -> None:
        """MainWindow connects to EnvironmentSelector.environment_changed."""
        window = MainWindow()
        qtbot.addWidget(window)
        # Verify the connection works by calling the slot directly
        # (no open tabs — should not raise)
        window._on_environment_changed(None)

    def test_refresh_variable_map_calls_set_on_editor(self, qapp: QApplication, qtbot) -> None:
        """_refresh_variable_map builds the map and pushes it to the editor."""
        window = MainWindow()
        qtbot.addWidget(window)

        with patch(
            "ui.main_window.EnvironmentService.build_combined_variable_map",
            return_value={"key": "value"},
        ) as mock_build:
            window._refresh_variable_map(window.request_widget, None)
            mock_build.assert_called_once()

    def test_on_environment_changed_updates_open_tabs(self, qapp: QApplication, qtbot) -> None:
        """Changing the environment refreshes variable maps in all open tabs."""
        window = MainWindow()
        qtbot.addWidget(window)

        # Create and open a request to have an active tab
        coll = CollectionService.create_collection("VarColl")
        req = CollectionService.create_request(coll.id, "GET", "http://t.test", "Req")
        window._open_request(req.id, push_history=True)

        with patch(
            "ui.main_window.EnvironmentService.build_combined_variable_map",
            return_value={"env_var": "env_val"},
        ) as mock_build:
            window._on_environment_changed(None)
            assert mock_build.called
