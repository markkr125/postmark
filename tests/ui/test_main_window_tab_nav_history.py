"""MainWindow tests for tab activation history (Go Back/Forward)."""

from __future__ import annotations

from typing import cast

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QMenu

from services.collection_service import CollectionService
from ui.main_window import MainWindow


def _activate_tab(window: MainWindow, index: int) -> None:
    """Select a tab and run the tab-changed handler (mirrors user click)."""
    window._tab_bar.setCurrentIndex(index)
    window._on_tab_changed(index)


class TestTabActivationHistoryBasic:
    """Happy-path tab activation back/forward."""

    def test_tab_back_and_forward_cycle(self, qapp: QApplication, qtbot) -> None:
        """Activation order A→B→C; back→B; forward→C."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req_a = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req_b = svc.create_request(coll.id, "GET", "http://b.com", "B")
        req_c = svc.create_request(coll.id, "GET", "http://c.com", "C")

        window = MainWindow()
        qtbot.addWidget(window)

        window._open_request(req_a.id, push_history=False)
        window._open_request(req_b.id, push_history=False)
        window._open_request(req_c.id, push_history=False)

        idx_b = next(idx for idx, ctx in window._tabs.items() if ctx.request_id == req_b.id)
        idx_c = next(idx for idx, ctx in window._tabs.items() if ctx.request_id == req_c.id)
        token_b = window._tabs[idx_b].nav_token
        token_c = window._tabs[idx_c].nav_token

        window.tab_back_action.trigger()
        assert window._tab_nav_current == token_b
        assert window._tab_bar.currentIndex() == idx_b

        window.tab_forward_action.trigger()
        assert window._tab_nav_current == token_c
        assert window._tab_bar.currentIndex() == idx_c

    def test_same_tab_activation_does_not_grow_back_stack(self, qapp: QApplication, qtbot) -> None:
        """Repeated _on_tab_changed for the same index does not push history."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://a.com", "A")

        window = MainWindow()
        qtbot.addWidget(window)
        window._open_request(req.id, push_history=False)

        window._on_tab_changed(0)
        window._on_tab_changed(0)
        assert window._tab_nav_back == []

    def test_tab_nav_actions_disabled_when_stacks_empty(self, qapp: QApplication, qtbot) -> None:
        """Tab back/forward start disabled with empty stacks."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert not window.tab_back_action.isEnabled()
        assert not window.tab_forward_action.isEnabled()

    def test_seed_after_restore_clears_stacks(self, qapp: QApplication, qtbot) -> None:
        """_seed_tab_nav_after_restore clears stacks but sets current token."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://a.com", "A")

        window = MainWindow()
        qtbot.addWidget(window)
        window._open_request(req.id, push_history=False)
        window._tab_nav_back.append(999)
        window._tab_nav_forward.append(998)

        window._seed_tab_nav_after_restore()
        assert window._tab_nav_back == []
        assert window._tab_nav_forward == []
        assert window._tab_nav_current == window._tabs[0].nav_token
        assert not window.tab_back_action.isEnabled()


class TestTabActivationHistoryEdgeCases:
    """Close, reorder, deferred, and mixed tab types."""

    def test_close_tab_then_back_skips_closed_token(self, qapp: QApplication, qtbot) -> None:
        """Closing the middle tab removes its token from the back stack."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req_a = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req_b = svc.create_request(coll.id, "GET", "http://b.com", "B")
        req_c = svc.create_request(coll.id, "GET", "http://c.com", "C")

        window = MainWindow()
        qtbot.addWidget(window)
        window._open_request(req_a.id, push_history=False)
        window._open_request(req_b.id, push_history=False)
        window._open_request(req_c.id, push_history=False)

        idx_a = next(idx for idx, ctx in window._tabs.items() if ctx.request_id == req_a.id)
        idx_b = next(idx for idx, ctx in window._tabs.items() if ctx.request_id == req_b.id)
        token_a = window._tabs[idx_a].nav_token
        window._on_tab_close(idx_b)
        window.tab_back_action.trigger()
        assert window._tab_nav_current == token_a

    def test_reorder_then_back_follows_activation_not_bar_order(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Visual reorder does not change activation back/forward order."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req_a = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req_b = svc.create_request(coll.id, "GET", "http://b.com", "B")
        req_c = svc.create_request(coll.id, "GET", "http://c.com", "C")

        window = MainWindow()
        qtbot.addWidget(window)
        window._open_request(req_a.id, push_history=False)
        window._open_request(req_b.id, push_history=False)
        window._open_request(req_c.id, push_history=False)

        idx_b = next(idx for idx, ctx in window._tabs.items() if ctx.request_id == req_b.id)
        idx_c = next(idx for idx, ctx in window._tabs.items() if ctx.request_id == req_c.id)
        token_b = window._tabs[idx_b].nav_token
        window._tab_bar.move_tab(idx_c, 0)
        window.tab_back_action.trigger()
        assert window._tab_nav_current == token_b

    def test_deferred_tab_back_uses_same_nav_token(self, qapp: QApplication, qtbot) -> None:
        """Tab back returns to the same nav_token after a deferred tab was activated."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req_a = svc.create_request(coll.id, "GET", "http://a.com", "A")
        req_b = svc.create_request(coll.id, "GET", "http://b.com", "B")

        window = MainWindow()
        qtbot.addWidget(window)
        window._restore_request_deferred({"method": "GET", "name": "A"}, req_a.id)
        window._restore_request_deferred({"method": "GET", "name": "B"}, req_b.id)
        token_a = window._deferred_tabs[0]["nav_token"]

        _activate_tab(window, 0)
        assert 0 in window._tabs
        assert window._tabs[0].nav_token == token_a

        _activate_tab(window, 1)
        window.tab_back_action.trigger()
        assert window._tab_nav_current == token_a
        assert window._tab_bar.currentIndex() == 0

    def test_mixed_tab_types_activation_order(self, qapp: QApplication, qtbot) -> None:
        """Back/forward works across request and folder tabs."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://a.com", "A")

        window = MainWindow()
        qtbot.addWidget(window)
        window._open_request(req.id, push_history=False)
        token_req = window._tabs[0].nav_token

        window._open_folder(coll.id, show_missing_warning=False)
        folder_idx = window._tab_bar.currentIndex()
        token_folder = window._tabs[folder_idx].nav_token

        window.tab_back_action.trigger()
        assert window._tab_nav_current == token_req

        window.tab_forward_action.trigger()
        assert window._tab_nav_current == token_folder


class TestTabActivationHistoryMenu:
    """Go menu and shortcut bindings."""

    def test_tab_nav_shortcuts(self, qapp: QApplication, qtbot) -> None:
        """Tab back/forward actions use Ctrl+Alt+arrow shortcuts."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert QKeySequence("Ctrl+Alt+Left") in window.tab_back_action.shortcuts()
        assert QKeySequence("Ctrl+Alt+Right") in window.tab_forward_action.shortcuts()

    def test_go_menu_contains_tab_nav_actions(self, qapp: QApplication, qtbot) -> None:
        """Go menu lists tab Back and Forward actions."""
        window = MainWindow()
        qtbot.addWidget(window)
        from tests.ui.conftest import finish_main_window_startup

        finish_main_window_startup(window)
        menubar = window.menuBar()
        go_top = next(
            (a for a in menubar.actions() if a.text().replace("&", "") == "Go"),
            None,
        )
        assert go_top is not None
        go_menu = cast(QMenu, go_top.menu())
        texts = [act.text().replace("&", "") for act in go_menu.actions() if not act.isSeparator()]
        assert "Back" in texts
        assert "Forward" in texts
