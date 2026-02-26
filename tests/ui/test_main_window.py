"""Smoke tests for the top-level MainWindow."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from services.collection_service import CollectionService
from ui.collections.collection_widget import CollectionWidget
from ui.main_window import MainWindow
from ui.request_editor import RequestEditorWidget


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

    def test_request_editor_is_request_editor_widget(
        self, qapp: QApplication, qtbot
    ) -> None:
        """MainWindow uses RequestEditorWidget for the request pane."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert isinstance(window.request_widget, RequestEditorWidget)

    def test_back_forward_initially_disabled(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Back and forward actions start disabled."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert not window.back_action.isEnabled()
        assert not window.forward_action.isEnabled()


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
        assert window.request_widget._title_label.text() == "My Req"

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

    def test_item_action_open_triggers_editor(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Emitting item_action_triggered with 'Open' loads the editor."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "PUT", "http://c.com", "EditReq")

        window = MainWindow()
        qtbot.addWidget(window)

        window.collection_widget.item_action_triggered.emit("request", req.id, "Open")

        assert window.request_widget._url_input.text() == "http://c.com"
