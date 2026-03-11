"""Save Request dialog — lets the user pick a name and collection for a draft request.

Shown when saving a request that has not yet been persisted to any
collection (i.e. ``request_id is None``).  Displays a searchable
tree of existing collections and a "New Collection" button for
creating one inline.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.collection_service import CollectionService
from ui.styling.icons import phi

logger = logging.getLogger(__name__)

# Qt data role used to store the collection ID on each tree item
_ROLE_COLLECTION_ID = Qt.ItemDataRole.UserRole


class SaveRequestDialog(QDialog):
    """Modal dialog for saving a draft request into a collection.

    After the dialog is accepted, call :meth:`request_name` and
    :meth:`selected_collection_id` to retrieve the user's choices.
    """

    def __init__(
        self,
        *,
        default_name: str = "Untitled Request",
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the dialog with a name field and collection tree."""
        super().__init__(parent)
        self.setWindowTitle("Save Request")
        self.setMinimumWidth(420)
        self.setMinimumHeight(460)

        self._collection_id: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # -- Request name field ----------------------------------------
        name_label = QLabel("Request name")
        name_label.setObjectName("sectionLabel")
        root.addWidget(name_label)

        self._name_input = QLineEdit()
        self._name_input.setText(default_name)
        self._name_input.selectAll()
        root.addWidget(self._name_input)

        # -- "Save to" label -------------------------------------------
        save_to_label = QLabel("Save to")
        save_to_label.setObjectName("sectionLabel")
        root.addWidget(save_to_label)

        # -- Search / filter -------------------------------------------
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search for collection or folder")
        search_icon = phi("magnifying-glass")
        self._search_input.addAction(search_icon, QLineEdit.ActionPosition.LeadingPosition)
        self._search_input.textChanged.connect(self._on_search_changed)
        root.addWidget(self._search_input)

        # -- Collection tree -------------------------------------------
        self._tree = QTreeWidget()
        self._tree.setObjectName("collectionTree")
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemCollapsed.connect(self._on_item_collapsed)
        root.addWidget(self._tree, 1)

        # -- "New Collection" button -----------------------------------
        new_coll_btn = QPushButton("New Collection")
        new_coll_btn.setIcon(phi("folder-plus"))
        new_coll_btn.setObjectName("flatAccentButton")
        new_coll_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_coll_btn.clicked.connect(self._on_new_collection)
        root.addWidget(new_coll_btn)

        # -- Action buttons --------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("dismissButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._save_btn = QPushButton("Save")
        self._save_btn.setObjectName("primaryButton")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._save_btn)

        root.addLayout(btn_row)

        # -- Populate tree ---------------------------------------------
        self._load_collections()

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------
    def request_name(self) -> str:
        """Return the user-entered request name."""
        return self._name_input.text().strip() or "Untitled Request"

    def selected_collection_id(self) -> int | None:
        """Return the ID of the selected collection, or ``None``."""
        return self._collection_id

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def _load_collections(self) -> None:
        """Fetch all collections and populate the tree widget."""
        tree_data = CollectionService.fetch_all()
        self._tree.clear()
        folder_icon = phi("folder")
        self._build_tree(tree_data, parent_item=None, folder_icon=folder_icon)

    def _build_tree(
        self,
        node: dict[str, Any],
        parent_item: QTreeWidgetItem | None,
        folder_icon: Any,
    ) -> None:
        """Recursively build QTreeWidgetItems from the nested collection dict."""
        for _key, child in sorted(node.items(), key=lambda kv: kv[1].get("name", "")):
            if child.get("type") == "folder":
                item = QTreeWidgetItem()
                item.setText(0, child["name"])
                item.setIcon(0, folder_icon)
                item.setData(0, _ROLE_COLLECTION_ID, child["id"])
                item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                if parent_item is not None:
                    parent_item.addChild(item)
                else:
                    self._tree.addTopLevelItem(item)
                children = child.get("children", {})
                if children:
                    self._build_tree(children, parent_item=item, folder_icon=folder_icon)

    # ------------------------------------------------------------------
    # Search / filter
    # ------------------------------------------------------------------
    def _on_search_changed(self, text: str) -> None:
        """Filter the tree based on search text, showing matching items and their ancestors."""
        needle = text.strip().lower()
        if not needle:
            self._set_all_visible(True)
            self._tree.collapseAll()
            return
        # Hide everything, then reveal matches and their ancestors
        self._set_all_visible(False)
        self._filter_tree_items(needle)

    def _set_all_visible(self, visible: bool) -> None:
        """Set visibility on every item in the tree."""
        iterator = _tree_item_iterator(self._tree)
        for item in iterator:
            item.setHidden(not visible)

    def _filter_tree_items(self, needle: str) -> None:
        """Show items matching *needle* and all their ancestors."""
        iterator = _tree_item_iterator(self._tree)
        for item in iterator:
            if needle in item.text(0).lower():
                _reveal_with_ancestors(item)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Swap to open-folder icon when a folder is expanded."""
        item.setIcon(0, phi("folder-open"))

    def _on_item_collapsed(self, item: QTreeWidgetItem) -> None:
        """Restore closed-folder icon when a folder is collapsed."""
        item.setIcon(0, phi("folder"))

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Update selection state when a collection is clicked."""
        self._collection_id = item.data(0, _ROLE_COLLECTION_ID)
        self._save_btn.setEnabled(self._collection_id is not None)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Accept the dialog on double-click."""
        self._on_item_clicked(item, 0)
        if self._collection_id is not None:
            self.accept()

    def _on_new_collection(self) -> None:
        """Create a new top-level collection and add it to the tree."""
        try:
            new_coll = CollectionService.create_collection("New Collection")
        except Exception:
            logger.exception("Failed to create collection from save dialog")
            return
        folder_icon = phi("folder")
        item = QTreeWidgetItem()
        item.setText(0, new_coll.name)
        item.setIcon(0, folder_icon)
        item.setData(0, _ROLE_COLLECTION_ID, new_coll.id)
        self._tree.addTopLevelItem(item)
        self._tree.setCurrentItem(item)
        self._collection_id = new_coll.id
        self._save_btn.setEnabled(True)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------
def _tree_item_iterator(tree: QTreeWidget) -> list[QTreeWidgetItem]:
    """Return a flat list of every QTreeWidgetItem in *tree*."""
    items: list[QTreeWidgetItem] = []

    def _walk(parent_item: QTreeWidgetItem) -> None:
        items.append(parent_item)
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child is not None:
                _walk(child)

    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        if top is not None:
            _walk(top)
    return items


def _reveal_with_ancestors(item: QTreeWidgetItem) -> None:
    """Unhide *item* and all its ancestor items, expanding as needed."""
    item.setHidden(False)
    parent = item.parent()
    while parent is not None:
        parent.setHidden(False)
        parent.setExpanded(True)
        parent = parent.parent()
