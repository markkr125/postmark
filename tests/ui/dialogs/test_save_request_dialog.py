"""Tests for the SaveRequestDialog widget."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from services.collection_service import CollectionService
from ui.dialogs.save_request_dialog import (SaveRequestDialog,
                                            _tree_item_iterator)


class TestSaveRequestDialogConstruction:
    """Tests for initial dialog state."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """SaveRequestDialog can be instantiated without errors."""
        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "Save Request"

    def test_default_name(self, qapp: QApplication, qtbot) -> None:
        """Default request name is 'Untitled Request'."""
        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)
        assert dialog.request_name() == "Untitled Request"

    def test_custom_default_name(self, qapp: QApplication, qtbot) -> None:
        """Custom default name is shown in the name input."""
        dialog = SaveRequestDialog(default_name="http://example.com")
        qtbot.addWidget(dialog)
        assert dialog.request_name() == "http://example.com"

    def test_minimum_size(self, qapp: QApplication, qtbot) -> None:
        """Dialog has a reasonable minimum size."""
        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)
        assert dialog.minimumWidth() >= 420
        assert dialog.minimumHeight() >= 460

    def test_save_button_disabled_initially(self, qapp: QApplication, qtbot) -> None:
        """Save button is disabled when no collection is selected."""
        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)
        assert not dialog._save_btn.isEnabled()

    def test_no_collection_selected_initially(self, qapp: QApplication, qtbot) -> None:
        """No collection is selected on construction."""
        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)
        assert dialog.selected_collection_id() is None

    def test_tree_header_hidden(self, qapp: QApplication, qtbot) -> None:
        """The tree widget has its header hidden."""
        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)
        assert dialog._tree.isHeaderHidden()


class TestSaveRequestDialogCollectionTree:
    """Tests for the collection tree and selection."""

    def test_collections_populated(self, qapp: QApplication, qtbot) -> None:
        """Collections from the database appear in the tree."""
        CollectionService.create_collection("Alpha")
        CollectionService.create_collection("Beta")

        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)

        items = _tree_item_iterator(dialog._tree)
        names = [it.text(0) for it in items]
        assert "Alpha" in names
        assert "Beta" in names

    def test_nested_collections_appear_as_children(self, qapp: QApplication, qtbot) -> None:
        """Nested collections appear as child items in the tree."""
        parent = CollectionService.create_collection("Parent")
        CollectionService.create_collection("Child", parent_id=parent.id)

        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)

        # Find the parent item
        parent_item: QTreeWidgetItem | None = None
        for i in range(dialog._tree.topLevelItemCount()):
            top = dialog._tree.topLevelItem(i)
            if top is not None and top.data(0, Qt.ItemDataRole.UserRole) == parent.id:
                parent_item = top
                break

        assert parent_item is not None
        assert parent_item.childCount() >= 1

    def test_click_selects_collection(self, qapp: QApplication, qtbot) -> None:
        """Clicking a tree item selects that collection."""
        coll = CollectionService.create_collection("ClickMe")

        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)

        # Find the item for our collection
        for item in _tree_item_iterator(dialog._tree):
            if item.data(0, Qt.ItemDataRole.UserRole) == coll.id:
                dialog._on_item_clicked(item, 0)
                break

        assert dialog.selected_collection_id() == coll.id
        assert dialog._save_btn.isEnabled()

    def test_search_filters_tree(self, qapp: QApplication, qtbot) -> None:
        """Typing in the search field hides non-matching tree items."""
        CollectionService.create_collection("SearchTarget")
        CollectionService.create_collection("OtherCollection")

        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)

        dialog._search_input.setText("SearchTarget")

        visible = [it for it in _tree_item_iterator(dialog._tree) if not it.isHidden()]
        assert len(visible) >= 1
        assert all("SearchTarget" in it.text(0) for it in visible)

    def test_search_clear_restores_tree(self, qapp: QApplication, qtbot) -> None:
        """Clearing the search makes all items visible again."""
        CollectionService.create_collection("A")
        CollectionService.create_collection("B")

        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)

        dialog._search_input.setText("A")
        dialog._search_input.clear()

        all_items = _tree_item_iterator(dialog._tree)
        hidden = [it for it in all_items if it.isHidden()]
        assert len(hidden) == 0


class TestSaveRequestDialogNewCollection:
    """Tests for the 'New Collection' inline creation."""

    def test_new_collection_adds_to_tree(self, qapp: QApplication, qtbot) -> None:
        """Clicking 'New Collection' creates one and adds it to the tree."""
        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)

        count_before = len(_tree_item_iterator(dialog._tree))
        dialog._on_new_collection()
        count_after = len(_tree_item_iterator(dialog._tree))

        assert count_after == count_before + 1

    def test_new_collection_auto_selects(self, qapp: QApplication, qtbot) -> None:
        """The newly created collection is automatically selected."""
        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)

        dialog._on_new_collection()

        assert dialog.selected_collection_id() is not None
        assert dialog._save_btn.isEnabled()


class TestSaveRequestDialogRequestName:
    """Tests for the request name input."""

    def test_empty_name_returns_default(self, qapp: QApplication, qtbot) -> None:
        """An empty name field falls back to 'Untitled Request'."""
        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)
        dialog._name_input.clear()
        assert dialog.request_name() == "Untitled Request"

    def test_whitespace_name_returns_default(self, qapp: QApplication, qtbot) -> None:
        """A whitespace-only name falls back to 'Untitled Request'."""
        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)
        dialog._name_input.setText("   ")
        assert dialog.request_name() == "Untitled Request"

    def test_custom_name_returned(self, qapp: QApplication, qtbot) -> None:
        """A user-entered name is returned as-is (stripped)."""
        dialog = SaveRequestDialog()
        qtbot.addWidget(dialog)
        dialog._name_input.setText("  My Request  ")
        assert dialog.request_name() == "My Request"
        assert dialog.request_name() == "My Request"
