"""Tests for the CollectionTree widget."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from ui.collections.tree import CollectionTree

from ..conftest import make_collection_dict, top_level_items


class TestCollectionTreeDoubleClick:
    """Tests for double-click — now a no-op."""

    def test_double_click_request_is_noop(self, qapp: QApplication, qtbot) -> None:
        """Double-clicking a request item does not emit a signal."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 1,
                    "name": "Coll",
                    "requests": [{"id": 10, "name": "Req", "method": "GET"}],
                },
            ]
        )
        tree.set_collections(data)

        folder = top_level_items(tree)[0]
        req_item = folder.child(0)

        emitted: list[list] = []
        tree.item_action_triggered.connect(lambda *args: emitted.append(list(args)))
        tree._on_item_double_clicked(req_item, 0)

        assert emitted == []

    def test_double_click_folder_does_not_emit_signal(self, qapp: QApplication, qtbot) -> None:
        """Double-clicking a folder does not emit item_action_triggered.

        Expand/collapse is handled by Qt's built-in ``expandsOnDoubleClick``.
        """
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 5,
                    "name": "Folder",
                    "children": [{"id": 6, "name": "SubFolder"}],
                },
            ]
        )
        tree.set_collections(data)

        folder = top_level_items(tree)[0]

        emitted: list[list] = []
        tree.item_action_triggered.connect(lambda *args: emitted.append(list(args)))
        tree._on_item_double_clicked(folder, 0)
        assert emitted == []


class TestCollectionTreeContextMenuOverview:
    """Tests for the Overview context-menu action on folders."""

    def test_overview_action_emits_folder_open(self, qapp: QApplication, qtbot) -> None:
        """Selecting Overview from folder context menu emits folder Open."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 7,
                    "name": "MyFolder",
                },
            ]
        )
        tree.set_collections(data)

        folder = top_level_items(tree)[0]
        tree._current_item = folder

        # Find the Overview action in the folder menu
        overview_action = None
        for action in tree._folder_menu.actions():
            if action.data() == "Overview":
                overview_action = action
                break
        assert overview_action is not None

        with qtbot.waitSignal(tree.item_action_triggered, timeout=1000) as blocker:
            tree._emit_menu_action(overview_action)

        assert blocker.args == ["folder", 7, "Open"]


class TestCollectionTreeSingleClick:
    """Tests for single-click behaviour on tree items."""

    def test_single_click_folder_toggles_expand(self, qapp: QApplication, qtbot) -> None:
        """Single-clicking a folder toggles its expanded state."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 1,
                    "name": "Folder",
                    "requests": [{"id": 10, "name": "Req", "method": "GET"}],
                },
            ]
        )
        tree.set_collections(data)

        folder = top_level_items(tree)[0]
        folder.setExpanded(False)

        tree._on_item_clicked(folder, 0)
        assert folder.isExpanded()

        tree._on_item_clicked(folder, 0)
        assert not folder.isExpanded()

    def test_single_click_request_emits_open(self, qapp: QApplication, qtbot) -> None:
        """Single-clicking a request emits Open action."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 1,
                    "name": "Coll",
                    "requests": [{"id": 10, "name": "Req", "method": "GET"}],
                },
            ]
        )
        tree.set_collections(data)

        folder = top_level_items(tree)[0]
        req_item = folder.child(0)

        with qtbot.waitSignal(tree.item_action_triggered, timeout=1000) as blocker:
            tree._on_item_clicked(req_item, 0)

        assert blocker.args == ["request", 10, "Open"]


class TestCollectionTreeKeyboardShortcuts:
    """Tests for F2 and Delete keyboard shortcuts."""

    def test_f2_triggers_rename_folder(self, qapp: QApplication, qtbot) -> None:
        """Pressing F2 on a folder triggers rename mode."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict([{"id": 1, "name": "MyFolder"}])
        tree.set_collections(data)

        folder_item = top_level_items(tree)[0]
        tree._tree.setCurrentItem(folder_item)

        # Simulate F2 key press via event filter
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F2, Qt.KeyboardModifier.NoModifier)
        result = tree.eventFilter(tree._tree, event)
        assert result is True  # event was handled

    def test_delete_triggers_delete_request(self, qapp: QApplication, qtbot, monkeypatch) -> None:
        """Pressing Delete on a request triggers delete confirmation."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 1,
                    "name": "Coll",
                    "requests": [{"id": 10, "name": "Req", "method": "GET"}],
                },
            ]
        )
        tree.set_collections(data)

        folder = top_level_items(tree)[0]
        req_item = folder.child(0)
        tree._tree.setCurrentItem(req_item)

        # Mock the confirmation dialog to auto-accept
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
        )

        with qtbot.waitSignal(tree.request_delete_requested, timeout=1000) as blocker:
            event = QKeyEvent(
                QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier
            )
            tree.eventFilter(tree._tree, event)

        assert blocker.args == [10]


class TestCollectionTreeTooltips:
    """Tests for tooltips on tree items."""

    def test_folder_tooltip(self, qapp: QApplication, qtbot) -> None:
        """Folder items have a tooltip with the folder name."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict([{"id": 1, "name": "My Folder"}])
        tree.set_collections(data)

        folder = top_level_items(tree)[0]
        assert folder.toolTip(0) == "My Folder"

    def test_request_tooltip(self, qapp: QApplication, qtbot) -> None:
        """Request items have a tooltip with method and name."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 1,
                    "name": "Coll",
                    "requests": [{"id": 10, "name": "Get Users", "method": "GET"}],
                },
            ]
        )
        tree.set_collections(data)

        req = top_level_items(tree)[0].child(0)
        assert req.toolTip(0) == "GET Get Users"


class TestCollectionTreeSelectedCollection:
    """Tests for the selected_collection_changed signal."""

    def test_selecting_folder_emits_its_id(self, qapp: QApplication, qtbot) -> None:
        """Selecting a folder emits its ID via selected_collection_changed."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict([{"id": 1, "name": "Folder"}])
        tree.set_collections(data)

        folder = top_level_items(tree)[0]
        with qtbot.waitSignal(tree.selected_collection_changed, timeout=1000) as blocker:
            tree._tree.setCurrentItem(folder)

        assert blocker.args == [1]

    def test_selecting_request_emits_parent_id(self, qapp: QApplication, qtbot) -> None:
        """Selecting a request emits the parent folder's ID."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 1,
                    "name": "Folder",
                    "requests": [{"id": 10, "name": "Req", "method": "GET"}],
                },
            ]
        )
        tree.set_collections(data)

        req = top_level_items(tree)[0].child(0)
        with qtbot.waitSignal(tree.selected_collection_changed, timeout=1000) as blocker:
            tree._tree.setCurrentItem(req)

        assert blocker.args == [1]
