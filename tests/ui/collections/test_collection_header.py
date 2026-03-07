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
        assert header.height() == 70

    def test_new_collection_signal(self, qapp: QApplication, qtbot) -> None:
        """Clicking the collection tile emits ``new_collection_requested(None)``."""
        header = CollectionHeader()
        qtbot.addWidget(header)

        with qtbot.waitSignal(header.new_collection_requested, timeout=1000) as blocker:
            header._popup.new_collection_clicked.emit()

        assert blocker.args == [None]

    def test_search_changed_signal(self, qapp: QApplication, qtbot) -> None:
        """Typing in the search box emits ``search_changed``."""
        header = CollectionHeader()
        qtbot.addWidget(header)

        with qtbot.waitSignal(header.search_changed, timeout=1000) as blocker:
            header._search.setText("hello")

        assert blocker.args == ["hello"]

    def test_new_request_emits_draft_signal(self, qapp: QApplication, qtbot) -> None:
        """Clicking the request tile emits ``new_request_requested(None)`` (draft)."""
        header = CollectionHeader()
        qtbot.addWidget(header)

        with qtbot.waitSignal(header.new_request_requested, timeout=1000) as blocker:
            header._popup.new_request_clicked.emit()

        assert blocker.args == [None]

    def test_set_selected_collection_id(self, qapp: QApplication, qtbot) -> None:
        """``set_selected_collection_id`` stores the collection ID."""
        header = CollectionHeader()
        qtbot.addWidget(header)

        header.set_selected_collection_id(42)
        assert header._selected_collection_id == 42

        header.set_selected_collection_id(None)
        assert header._selected_collection_id is None
