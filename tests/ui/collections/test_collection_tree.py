"""Tests for the CollectionTree widget."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from ui.collections.tree import ROLE_ITEM_ID, ROLE_ITEM_TYPE, CollectionTree

from ..conftest import make_collection_dict, top_level_items


class TestCollectionTree:
    """Tests for the tree widget that displays the collection hierarchy."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Tree widget can be instantiated without errors."""
        tree = CollectionTree()
        qtbot.addWidget(tree)
        assert tree is not None

    def test_set_collections_populates_tree(self, qapp: QApplication, qtbot) -> None:
        """``set_collections`` creates top-level folder items."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {"id": 1, "name": "Alpha"},
                {"id": 2, "name": "Beta"},
            ]
        )
        tree.set_collections(data)

        items = top_level_items(tree)
        assert len(items) == 2
        names = {it.text(0) for it in items}
        assert names == {"Alpha", "Beta"}

    def test_set_collections_with_nested_requests(self, qapp: QApplication, qtbot) -> None:
        """Requests appear as children of their parent folder."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 1,
                    "name": "API",
                    "requests": [
                        {"id": 10, "name": "List users", "method": "GET"},
                        {"id": 11, "name": "Create user", "method": "POST"},
                    ],
                },
            ]
        )
        tree.set_collections(data)

        items = top_level_items(tree)
        assert len(items) == 1
        folder = items[0]
        assert folder.childCount() == 2

    def test_set_collections_clears_previous(self, qapp: QApplication, qtbot) -> None:
        """Calling ``set_collections`` twice replaces old data."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.set_collections(make_collection_dict([{"id": 1, "name": "Old"}]))
        tree.set_collections(make_collection_dict([{"id": 2, "name": "New"}]))

        items = top_level_items(tree)
        assert len(items) == 1
        assert items[0].text(0) == "New"

    def test_add_collection_root(self, qapp: QApplication, qtbot) -> None:
        """``add_collection`` with parent_id=None adds a top-level folder."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.set_collections({})
        tree.add_collection({"id": 5, "name": "Root Folder"}, parent_id=None)

        items = top_level_items(tree)
        assert len(items) == 1
        assert items[0].data(0, ROLE_ITEM_ID) == 5

    def test_add_collection_nested(self, qapp: QApplication, qtbot) -> None:
        """``add_collection`` with a parent_id nests under that folder."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.set_collections(make_collection_dict([{"id": 1, "name": "Parent"}]))
        tree.add_collection({"id": 2, "name": "Child"}, parent_id=1)

        parent = top_level_items(tree)[0]
        assert parent.childCount() == 1
        child = parent.child(0)
        assert child.data(0, ROLE_ITEM_ID) == 2
        assert child.data(1, ROLE_ITEM_TYPE) == "folder"

    def test_add_request(self, qapp: QApplication, qtbot) -> None:
        """``add_request`` inserts a request child under the given folder."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.set_collections(make_collection_dict([{"id": 1, "name": "Coll"}]))
        tree.add_request(
            {"id": 10, "name": "Get items", "method": "GET", "url": "/items"},
            parent_id=1,
        )

        folder = top_level_items(tree)[0]
        assert folder.childCount() == 1
        req = folder.child(0)
        assert req.data(0, ROLE_ITEM_ID) == 10
        assert req.data(1, ROLE_ITEM_TYPE) == "request"

    def test_remove_item_folder(self, qapp: QApplication, qtbot) -> None:
        """``remove_item`` removes a top-level folder."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.set_collections(make_collection_dict([{"id": 1, "name": "Gone"}]))
        assert len(top_level_items(tree)) == 1

        tree.remove_item(1, "folder")
        assert len(top_level_items(tree)) == 0

    def test_remove_item_request(self, qapp: QApplication, qtbot) -> None:
        """``remove_item`` removes a request from its parent folder."""
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
        assert folder.childCount() == 1

        tree.remove_item(10, "request")
        assert folder.childCount() == 0

    def test_select_item_by_id(self, qapp: QApplication, qtbot) -> None:
        """``select_item_by_id`` sets the current item in the tree."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.set_collections(
            make_collection_dict(
                [
                    {"id": 1, "name": "A"},
                    {"id": 2, "name": "B"},
                ]
            )
        )
        tree.select_item_by_id(2, "folder")

        current = tree._tree.currentItem()
        assert current is not None
        assert current.data(0, ROLE_ITEM_ID) == 2

    def test_item_roles_stored_correctly(self, qapp: QApplication, qtbot) -> None:
        """Items store the correct ID and type in UserRole data."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 3,
                    "name": "Folder",
                    "requests": [{"id": 7, "name": "Req", "method": "POST"}],
                },
            ]
        )
        tree.set_collections(data)

        folder = top_level_items(tree)[0]
        assert folder.data(0, ROLE_ITEM_ID) == 3
        assert folder.data(1, ROLE_ITEM_TYPE) == "folder"

        req = folder.child(0)
        assert req.data(0, ROLE_ITEM_ID) == 7
        assert req.data(1, ROLE_ITEM_TYPE) == "request"
        assert req.data(1, ROLE_ITEM_TYPE) == "request"

    def test_update_item_name_request(self, qapp: QApplication, qtbot) -> None:
        """update_item_name updates column 1 for request items."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 1,
                    "name": "Coll",
                    "requests": [{"id": 10, "name": "OldReq", "method": "GET"}],
                },
            ]
        )
        tree.set_collections(data)

        # Before update
        folder = top_level_items(tree)[0]
        req = folder.child(0)
        assert req.text(1) == "OldReq"

        # Rename via update_item_name
        tree.update_item_name(10, "request", "NewReq")
        assert req.text(1) == "NewReq"

    def test_update_item_name_folder(self, qapp: QApplication, qtbot) -> None:
        """update_item_name updates column 0 for folder items."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict([{"id": 1, "name": "OldFolder"}])
        tree.set_collections(data)

        folder = top_level_items(tree)[0]
        assert folder.text(0) == "OldFolder"

        tree.update_item_name(1, "folder", "NewFolder")
        assert folder.text(0) == "NewFolder"


class TestCollectionTreeFilter:
    """Tests for search/filter functionality."""

    def test_filter_hides_non_matching(self, qapp: QApplication, qtbot) -> None:
        """Items that don't match the filter text are hidden."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {"id": 1, "name": "Users API"},
                {"id": 2, "name": "Products API"},
            ]
        )
        tree.set_collections(data)

        tree.filter_items("Users")
        items = top_level_items(tree)
        # Sorted alphabetically: Products API (0), Users API (1)
        assert items[1].isHidden() is False  # "Users API" matches
        assert items[0].isHidden() is True  # "Products API" hidden

    def test_filter_empty_string_shows_all(self, qapp: QApplication, qtbot) -> None:
        """Empty filter text restores all items."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {"id": 1, "name": "Users API"},
                {"id": 2, "name": "Products API"},
            ]
        )
        tree.set_collections(data)

        tree.filter_items("Users")
        tree.filter_items("")

        items = top_level_items(tree)
        assert not items[0].isHidden()
        assert not items[1].isHidden()

    def test_filter_shows_parent_of_matching_child(self, qapp: QApplication, qtbot) -> None:
        """Folders remain visible when they contain matching children."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 1,
                    "name": "API",
                    "requests": [
                        {"id": 10, "name": "Get Users", "method": "GET"},
                    ],
                },
            ]
        )
        tree.set_collections(data)

        tree.filter_items("Users")
        folder = top_level_items(tree)[0]
        assert not folder.isHidden()  # parent stays visible
        assert not folder.child(0).isHidden()  # matching request visible

    def test_filter_case_insensitive(self, qapp: QApplication, qtbot) -> None:
        """Filter matching is case-insensitive."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict([{"id": 1, "name": "Users API"}])
        tree.set_collections(data)

        tree.filter_items("users")
        assert not top_level_items(tree)[0].isHidden()


class TestCollectionTreeDoubleClick:
    """Tests for double-click to open request and folder."""

    def test_double_click_request_emits_open(self, qapp: QApplication, qtbot) -> None:
        """Double-clicking a request item emits item_action_triggered."""
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
            tree._on_item_double_clicked(req_item, 0)

        assert blocker.args == ["request", 10, "Open"]

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

    def test_single_click_folder_does_not_expand(self, qapp: QApplication, qtbot) -> None:
        """Single-clicking a folder does not toggle expand."""
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

        emitted: list[list] = []
        tree.item_action_triggered.connect(lambda *args: emitted.append(list(args)))
        tree._on_item_clicked(folder, 0)

        assert not folder.isExpanded()
        assert emitted == []

    def test_single_click_request_emits_preview(self, qapp: QApplication, qtbot) -> None:
        """Single-clicking a request emits Preview action."""
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

        assert blocker.args == ["request", 10, "Preview"]


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


class TestCollectionTreeEmptyState:
    """Tests for the empty-state placeholder."""

    def test_empty_tree_shows_placeholder(self, qapp: QApplication, qtbot) -> None:
        """When tree has no items, the empty-state page is shown."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.set_collections({})
        assert tree._stack.currentIndex() == 0  # empty state

    def test_populated_tree_shows_tree(self, qapp: QApplication, qtbot) -> None:
        """When tree has items, the tree page is shown."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict([{"id": 1, "name": "Coll"}])
        tree.set_collections(data)
        assert tree._stack.currentIndex() == 1  # tree view

    def test_remove_last_item_shows_placeholder(self, qapp: QApplication, qtbot) -> None:
        """Removing the last item switches back to the empty state."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict([{"id": 1, "name": "Coll"}])
        tree.set_collections(data)
        assert tree._stack.currentIndex() == 1

        tree.remove_item(1, "folder")
        assert tree._stack.currentIndex() == 0


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


class TestCollectionTreeLoadingState:
    """Tests for the loading / empty-state stack transitions."""

    def test_initial_state_shows_loading_page(self, qapp: QApplication, qtbot) -> None:
        """Freshly constructed tree starts on the loading page (index 2)."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        assert tree._stack.currentIndex() == 2

    def test_show_loading_activates_timer(self, qapp: QApplication, qtbot) -> None:
        """``show_loading`` sets the stack to the loading page and starts the timer."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.show_loading()

        assert tree._stack.currentIndex() == 2
        assert tree._loading_timer.isActive()

    def test_hide_loading_stops_timer(self, qapp: QApplication, qtbot) -> None:
        """``hide_loading`` stops the dot-animation timer."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.show_loading()
        assert tree._loading_timer.isActive()

        tree.hide_loading()
        assert not tree._loading_timer.isActive()

    def test_set_collections_transitions_to_tree(self, qapp: QApplication, qtbot) -> None:
        """After ``set_collections`` with data the stack shows the tree (index 1)."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict([{"id": 1, "name": "Col"}])
        tree.hide_loading()
        tree.set_collections(data)

        assert tree._stack.currentIndex() == 1

    def test_set_collections_empty_shows_empty_state(self, qapp: QApplication, qtbot) -> None:
        """After ``set_collections`` with no data the stack shows empty state (index 0)."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.hide_loading()
        tree.set_collections({})

        assert tree._stack.currentIndex() == 0

    def test_animate_loading_dots_cycles_text(self, qapp: QApplication, qtbot) -> None:
        """Each call to ``_animate_loading_dots`` appends one more dot (wraps at 4)."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.show_loading()

        expected = [
            "Loading collections.",
            "Loading collections..",
            "Loading collections...",
            "Loading collections",
        ]
        for text in expected:
            tree._animate_loading_dots()
            assert tree._loading_label.text() == text
