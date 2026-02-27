"""Tests for the RequestTabBar widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QTabBar

from ui.request.request_tab_bar import RequestTabBar


class TestRequestTabBar:
    """Tests for tab bar construction and basic operations."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Tab bar can be instantiated without errors."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        assert bar.count() == 0

    def test_add_request_tab(self, qapp: QApplication, qtbot) -> None:
        """Adding a request tab increases the count and returns an index."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        idx = bar.add_request_tab("GET", "My Request")
        assert idx == 0
        assert bar.count() == 1

    def test_add_multiple_tabs(self, qapp: QApplication, qtbot) -> None:
        """Adding multiple tabs keeps them in order."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        idx0 = bar.add_request_tab("GET", "First")
        idx1 = bar.add_request_tab("POST", "Second")
        assert idx0 == 0
        assert idx1 == 1
        assert bar.count() == 2

    def test_remove_request_tab(self, qapp: QApplication, qtbot) -> None:
        """Removing a tab decreases the count."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        bar.add_request_tab("GET", "A")
        bar.add_request_tab("POST", "B")
        bar.remove_request_tab(0)
        assert bar.count() == 1

    def test_tab_label_exists(self, qapp: QApplication, qtbot) -> None:
        """Tab label widget is stored and retrievable."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        bar.add_request_tab("DELETE", "Remove Me")
        label = bar.tab_label(0)
        assert label is not None

    def test_update_tab_method(self, qapp: QApplication, qtbot) -> None:
        """Updating a tab method changes the badge text."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        bar.add_request_tab("GET", "Req")
        bar.update_tab(0, method="POST")
        label = bar.tab_label(0)
        assert label is not None
        assert label._method == "POST"

    def test_update_tab_name(self, qapp: QApplication, qtbot) -> None:
        """Updating a tab name changes the display text."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        bar.add_request_tab("GET", "Old Name")
        bar.update_tab(0, name="New Name")
        label = bar.tab_label(0)
        assert label is not None
        assert label._name == "New Name"

    def test_update_tab_dirty(self, qapp: QApplication, qtbot) -> None:
        """Setting dirty flag shows a bullet in the tab label."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        bar.add_request_tab("GET", "Req")
        bar.update_tab(0, is_dirty=True)
        label = bar.tab_label(0)
        assert label is not None
        assert label._name_label.text().startswith("\u2022 ")

    def test_update_tab_preview(self, qapp: QApplication, qtbot) -> None:
        """Setting preview flag renders the name in italic."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        bar.add_request_tab("GET", "Preview Req", is_preview=True)
        label = bar.tab_label(0)
        assert label is not None
        assert label._name_label.font().italic()

    def test_promote_preview(self, qapp: QApplication, qtbot) -> None:
        """Clearing preview flag removes italic from the name."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        bar.add_request_tab("GET", "Preview", is_preview=True)
        bar.update_tab(0, is_preview=False)
        label = bar.tab_label(0)
        assert label is not None
        assert not label._name_label.font().italic()

    def test_close_signal(self, qapp: QApplication, qtbot) -> None:
        """Closing a tab emits tab_close_requested."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        bar.add_request_tab("GET", "Close Me")
        with qtbot.waitSignal(bar.tab_close_requested, timeout=1000):
            bar.tabCloseRequested.emit(0)

    def test_remove_reindexes_labels(self, qapp: QApplication, qtbot) -> None:
        """After removing a tab, remaining labels are re-indexed."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        bar.add_request_tab("GET", "A")
        bar.add_request_tab("POST", "B")
        bar.add_request_tab("PUT", "C")
        bar.remove_request_tab(0)
        # "B" should now be at index 0, "C" at index 1
        label_b = bar.tab_label(0)
        label_c = bar.tab_label(1)
        assert label_b is not None
        assert label_b._name == "B"
        assert label_c is not None
        assert label_c._name == "C"


class TestRequestTabBarCloseButton:
    """Tests that tab close buttons are visible and functional."""

    def test_tabs_closable(self, qapp: QApplication, qtbot) -> None:
        """Tab bar has close buttons enabled."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        assert bar.tabsClosable()

    def test_close_button_not_hidden(self, qapp: QApplication, qtbot) -> None:
        """Close button widget on a tab is not force-hidden."""
        bar = RequestTabBar()
        qtbot.addWidget(bar)
        bar.add_request_tab("GET", "Test")

        # The close button is on the RightSide by default
        close_btn = bar.tabButton(0, QTabBar.ButtonPosition.RightSide)
        if close_btn is not None:
            assert not close_btn.isHidden()


class TestMainWindowMultiTab:
    """Tests for multi-tab behaviour in MainWindow."""

    def test_open_creates_tab(self, qapp: QApplication, qtbot) -> None:
        """Opening a request creates a tab in the tab bar."""
        from services.collection_service import CollectionService
        from ui.main_window import MainWindow

        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://example.com", "Req")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req.id, push_history=True)
        assert window._tab_bar.count() == 1

    def test_open_same_request_reuses_tab(self, qapp: QApplication, qtbot) -> None:
        """Opening the same request twice does not create a second tab."""
        from services.collection_service import CollectionService
        from ui.main_window import MainWindow

        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://example.com", "Req")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req.id, push_history=True)
        window._open_request(req.id, push_history=True)
        assert window._tab_bar.count() == 1

    def test_open_different_replaces_preview(self, qapp: QApplication, qtbot) -> None:
        """Opening a different request replaces the preview tab."""
        from services.collection_service import CollectionService
        from ui.main_window import MainWindow

        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req2 = svc.create_request(coll.id, "POST", "http://b.com", "B")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req1.id, push_history=True, is_preview=True)
        window._open_request(req2.id, push_history=True, is_preview=True)
        # Preview tab replaced, still just one tab
        assert window._tab_bar.count() == 1
        assert window.request_widget._url_input.text() == "http://b.com"

    def test_double_click_promotes_preview(self, qapp: QApplication, qtbot) -> None:
        """Double-clicking a preview tab promotes it to permanent."""
        from services.collection_service import CollectionService
        from ui.main_window import MainWindow

        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req2 = svc.create_request(coll.id, "POST", "http://b.com", "B")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req1.id, push_history=True, is_preview=True)
        window._on_tab_double_click(0)  # promote
        window._open_request(req2.id, push_history=True, is_preview=True)
        # Promoted tab stays, new preview tab added
        assert window._tab_bar.count() == 2

    def test_close_tab(self, qapp: QApplication, qtbot) -> None:
        """Closing a tab removes it and its context."""
        from services.collection_service import CollectionService
        from ui.main_window import MainWindow

        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req2 = svc.create_request(coll.id, "POST", "http://b.com", "B")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req1.id, push_history=True, is_preview=True)
        window._on_tab_double_click(0)  # promote so second request opens new tab
        window._open_request(req2.id, push_history=True, is_preview=True)

        assert window._tab_bar.count() == 2
        window._on_tab_close(0)
        assert window._tab_bar.count() == 1
