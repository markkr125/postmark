"""MainWindow tests for wrapped-tab navigation shortcuts."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from services.collection_service import CollectionService
from ui.main_window import MainWindow


class TestMainWindowTabNavigation:
    """Tests for keyboard-style tab navigation at the MainWindow level."""

    def test_next_and_previous_tab_actions_cycle_tabs(self, qapp: QApplication, qtbot) -> None:
        """Next/previous tab actions delegate to the wrapped deck."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req1 = svc.create_request(coll.id, "GET", "http://one.com", "One")
        req2 = svc.create_request(coll.id, "POST", "http://two.com", "Two")
        req3 = svc.create_request(coll.id, "PUT", "http://three.com", "Three")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req1.id, push_history=True)
        window._open_request(req2.id, push_history=True)
        window._open_request(req3.id, push_history=True)
        window._tab_bar.setCurrentIndex(0)

        window._next_tab_action.trigger()
        assert window._tab_bar.currentIndex() == 1

        window._previous_tab_action.trigger()
        assert window._tab_bar.currentIndex() == 0
