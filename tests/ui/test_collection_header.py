"""Tests for the CollectionHeader widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.collections.collection_header import CollectionHeader


class TestCollectionHeader:
    """Tests for the header widget (buttons and search bar)."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Header can be instantiated without errors."""
        header = CollectionHeader()
        qtbot.addWidget(header)
        assert header is not None
        assert header.height() == 75

    def test_new_collection_signal(self, qapp: QApplication, qtbot) -> None:
        """Clicking the + menu emits ``new_collection_requested(None)``."""
        header = CollectionHeader()
        qtbot.addWidget(header)

        with qtbot.waitSignal(header.new_collection_requested, timeout=1000) as blocker:
            # Directly trigger the action instead of clicking through the menu
            actions = header._plus_menu.actions()
            assert len(actions) >= 1, "Plus menu should have at least one action"
            actions[0].trigger()

        assert blocker.args == [None]

    def test_search_changed_signal(self, qapp: QApplication, qtbot) -> None:
        """Typing in the search box emits ``search_changed``."""
        header = CollectionHeader()
        qtbot.addWidget(header)

        with qtbot.waitSignal(header.search_changed, timeout=1000) as blocker:
            header._search.setText("hello")

        assert blocker.args == ["hello"]
