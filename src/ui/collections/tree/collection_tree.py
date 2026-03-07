"""Tree widget displaying collections and requests with drag-drop and context menus."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QLabel,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.collections.tree.collection_tree_delegate import CollectionTreeDelegate
from ui.collections.tree.constants import (
    EMPTY_COLLECTION_HTML,
    PLACEHOLDER_MARKER,
    ROLE_ITEM_ID,
    ROLE_ITEM_TYPE,
    ROLE_METHOD,
    ROLE_PLACEHOLDER,
)
from ui.collections.tree.draggable_tree_widget import DraggableTreeWidget
from ui.collections.tree.tree_actions import _TreeActionsMixin
from ui.styling.icons import phi

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Tree management subclass
# ----------------------------------------------------------------------
class CollectionTree(_TreeActionsMixin, QWidget):
    """Manages the QTreeWidget for collections.

    Includes building, context menus, and item interactions.
    Composable into the parent CollectionWidget.
    """

    item_action_triggered = Signal(str, int, str)
    item_name_changed = Signal(str, int, str)

    # --- Signals that the service layer should connect to ---
    collection_rename_requested = Signal(int, str)  # collection_id, new_name
    collection_delete_requested = Signal(int)  # collection_id
    request_rename_requested = Signal(int, str)  # request_id, new_name
    request_delete_requested = Signal(int)  # request_id
    request_moved = Signal(int, int)  # request_id, new_collection_id
    collection_moved = Signal(int, object)  # collection_id, new_parent_id
    new_collection_requested = Signal(object)  # parent_id (int | None)
    new_request_requested = Signal(object)  # parent_collection_id
    selected_collection_changed = Signal(object)  # collection_id (int | None)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the collection tree widget and context menus."""
        super().__init__(parent)

        self._current_item: QTreeWidgetItem | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stacked widget: page 0 = empty state, page 1 = tree, page 2 = loading
        self._stack = QStackedWidget()

        # Empty state placeholder
        empty_widget = QWidget()
        empty_layout = QVBoxLayout(empty_widget)
        empty_layout.setContentsMargins(20, 40, 20, 20)
        self._empty_label = QLabel("No collections yet.\nClick + to create one.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("emptyStateLabel")
        self._empty_label.setWordWrap(True)
        empty_layout.addWidget(self._empty_label)
        empty_layout.addStretch()
        self._stack.addWidget(empty_widget)  # index 0

        self._tree = DraggableTreeWidget()
        self._tree.setItemDelegate(CollectionTreeDelegate(self._tree))
        self._tree.setHeaderHidden(True)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.currentItemChanged.connect(self._on_current_item_changed)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemCollapsed.connect(self._on_item_collapsed)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        # Forward drag-and-drop signals from the tree widget
        self._tree.request_moved.connect(self.request_moved)
        self._tree.collection_moved.connect(self.collection_moved)

        self._tree.setDragEnabled(True)
        self._tree.setAcceptDrops(True)
        self._tree.setDropIndicatorShown(True)
        self._tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self._tree.viewport().setAcceptDrops(True)

        # Column 1 holds metadata (name, type) via data roles — hide visually
        self._tree.hideColumn(1)

        # Selection, hover, and row height styling is handled by global QSS
        self._tree.setIndentation(16)

        self._stack.addWidget(self._tree)  # index 1

        # Loading state placeholder
        loading_widget = QWidget()
        loading_layout = QVBoxLayout(loading_widget)
        loading_layout.setContentsMargins(20, 40, 20, 20)
        self._loading_label = QLabel("Loading collections")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setObjectName("emptyStateLabel")
        self._loading_label.setWordWrap(True)
        loading_layout.addWidget(self._loading_label)
        loading_layout.addStretch()
        self._stack.addWidget(loading_widget)  # index 2

        # Animated dots timer for the loading label
        self._loading_dot_count = 0
        self._loading_timer = QTimer(self)
        self._loading_timer.setInterval(400)
        self._loading_timer.timeout.connect(self._animate_loading_dots)

        layout.addWidget(self._stack)
        self._stack.setCurrentIndex(2)  # start with loading state

        self._setup_context_menus()
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_tree_context_menu)

        # Keyboard shortcuts — intercept via event filter
        self._tree.installEventFilter(self)

    # -- Item interaction callbacks ------------------------------------

    def _on_current_item_changed(self, current, previous) -> None:
        """Track the current item and emit ``selected_collection_changed``."""
        self._current_item = current

        if current is None:
            self.selected_collection_changed.emit(None)
            return

        item_type = current.data(1, ROLE_ITEM_TYPE)
        item_id = current.data(0, ROLE_ITEM_ID)

        if item_type == "folder":
            self.selected_collection_changed.emit(item_id)
        elif item_type == "request":
            parent = current.parent()
            if parent:
                self.selected_collection_changed.emit(parent.data(0, ROLE_ITEM_ID))
            else:
                self.selected_collection_changed.emit(None)
        else:
            self.selected_collection_changed.emit(None)

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Replace the folder icon with an open-folder variant on expand."""
        item_type = item.data(1, ROLE_ITEM_TYPE)
        if item_type != "folder":
            return
        item.setIcon(0, phi("folder-open"))

        # Show placeholder if the folder has no real children
        if self._count_real_children(item) == 0:
            self._add_placeholder(item)

    def _on_item_collapsed(self, item: QTreeWidgetItem) -> None:
        """Restore the closed-folder icon on collapse."""
        if item.data(1, ROLE_ITEM_TYPE) == "folder":
            item.setIcon(0, phi("folder"))

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Emit a ``Preview`` action when a request item is clicked."""
        item_type = item.data(1, ROLE_ITEM_TYPE)
        if item_type == "request":
            item_id = item.data(0, ROLE_ITEM_ID)
            self.item_action_triggered.emit(item_type, item_id, "Preview")

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Emit an ``Open`` action when a request item is double-clicked."""
        item_type = item.data(1, ROLE_ITEM_TYPE)
        if item_type != "request":
            return
        item_id = item.data(0, ROLE_ITEM_ID)
        self.item_action_triggered.emit(item_type, item_id, "Open")

    def _count_real_children(self, item: QTreeWidgetItem) -> int:
        """Count children excluding placeholder sentinel items."""
        count = 0
        for i in range(item.childCount()):
            child = item.child(i)
            if child.data(1, ROLE_PLACEHOLDER) != PLACEHOLDER_MARKER:
                count += 1
        return count

    def _add_placeholder(self, parent_item: QTreeWidgetItem) -> None:
        """Insert an HTML placeholder child when an empty folder is expanded."""
        # Check if a placeholder already exists
        for i in range(parent_item.childCount()):
            child_item = parent_item.child(i)
            if child_item and child_item.data(1, ROLE_PLACEHOLDER) == PLACEHOLDER_MARKER:
                return

        placeholder = QTreeWidgetItem(parent_item)
        placeholder.setData(1, ROLE_PLACEHOLDER, PLACEHOLDER_MARKER)
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)

        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(EMPTY_COLLECTION_HTML)
        label.setContentsMargins(0, 0, 0, 0)
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(lambda _: self._on_placeholder_link_clicked(parent_item))
        self._tree.setItemWidget(placeholder, 0, label)

    def _remove_placeholder(self, parent_item: QTreeWidgetItem) -> None:
        """Remove the placeholder child from a folder item if present."""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child and child.data(1, ROLE_PLACEHOLDER) == PLACEHOLDER_MARKER:
                parent_item.removeChild(child)
                return

    def _on_placeholder_link_clicked(self, parent_item: QTreeWidgetItem) -> None:
        """Handle clicks on the "Add request" link inside empty-folder placeholders."""
        parent_id = parent_item.data(0, ROLE_ITEM_ID)
        self.new_request_requested.emit(parent_id)

    def _expand_all_recursive(self, item: QTreeWidgetItem, *, expand: bool) -> None:
        """Recursively expand or collapse *item* and all its folder descendants."""
        item.setExpanded(expand)
        for i in range(item.childCount()):
            child = item.child(i)
            if child.data(1, ROLE_ITEM_TYPE) == "folder":
                self._expand_all_recursive(child, expand=expand)

    def _find_item_by_id(
        self, parent: QTreeWidgetItem, target_id: int, target_type: str
    ) -> QTreeWidgetItem | None:
        """Recursively search for an item whose UserRole data matches *target_id*."""
        key = f"{target_type}:{target_id}"
        current_key = f"{parent.data(1, ROLE_ITEM_TYPE)}:{parent.data(0, ROLE_ITEM_ID)}"

        if key == current_key:
            return parent

        for i in range(parent.childCount()):
            child = parent.child(i)
            found = self._find_item_by_id(child, target_id, target_type)
            if found:
                return found

        return None

    # ----------------------------------------------------------------------
    # Public API for tree management
    # ----------------------------------------------------------------------
    def filter_items(self, text: str) -> None:
        """Show/hide tree items based on a case-insensitive substring match.

        Folders that contain matching descendants remain visible.
        When *text* is empty all items are shown.
        """
        needle = text.strip().lower()
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            self._filter_recursive(root.child(i), needle)

    def _filter_recursive(self, item: QTreeWidgetItem, needle: str) -> bool:
        """Hide *item* unless it or a descendant matches *needle*.

        Returns ``True`` if *item* should remain visible.
        """
        # Skip placeholders
        if item.data(1, ROLE_PLACEHOLDER) == PLACEHOLDER_MARKER:
            item.setHidden(bool(needle))
            return False

        item_type = item.data(1, ROLE_ITEM_TYPE)

        # Determine the display name
        if item_type == "request":
            name = (item.text(1) or "").lower()
        else:
            name = (item.text(0) or "").lower()

        # 1. Check children first
        any_child_visible = False
        for i in range(item.childCount()):
            child = item.child(i)
            if self._filter_recursive(child, needle):
                any_child_visible = True

        # 2. Determine visibility
        if not needle:
            item.setHidden(False)
            return True

        matches = needle in name
        visible = matches or any_child_visible
        item.setHidden(not visible)

        # Expand folders that have matching descendants
        if any_child_visible and item_type == "folder":
            item.setExpanded(True)

        return visible

    def set_collections(self, data: dict[str, Any]) -> None:
        """Replace the entire tree contents from a nested collection dict."""
        self._tree.blockSignals(True)
        try:
            self._tree.clear()

            for _key, value in sorted(
                data.items(), key=lambda kv: kv[1]["name"].lower(), reverse=False
            ):
                # 1. Create the root folder item
                root_item = QTreeWidgetItem(self._tree, [value["name"]])
                root_item.setChildIndicatorPolicy(
                    QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
                )

                # 2. Store the ID on the root item
                root_item.setData(0, ROLE_ITEM_ID, value.get("id"))  # id
                root_item.setData(0, ROLE_ITEM_TYPE, value.get("type"))  # type (col 0 for delegate)
                root_item.setData(1, ROLE_ITEM_TYPE, value.get("type"))  # type (col 1 legacy)

                # 3. Apply icon / widget
                self._apply_item_properties(root_item, value)

                # 4. Add children (requests / sub-folders)
                self._add_items(root_item, value.get("children", {}))
        finally:
            self._tree.blockSignals(False)

        # Show empty state or tree based on content
        self._update_stack_visibility()

    def _add_items(self, parent: QTreeWidgetItem, mapping: dict[str, Any]) -> None:
        """Recursively add child items (folders and requests) under *parent*."""
        for _key, value in mapping.items():
            child = QTreeWidgetItem(
                parent, [value["name"] if value.get("type") != "request" else "", value["name"]]
            )

            child.setData(0, ROLE_ITEM_ID, value.get("id"))  # id
            child.setData(0, ROLE_ITEM_TYPE, value.get("type"))  # type (col 0 for delegate)
            child.setData(1, ROLE_ITEM_TYPE, value.get("type"))  # type (col 1 legacy)

            if value.get("type") == "folder":
                child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            else:
                child.setChildIndicatorPolicy(
                    QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator
                )
            self._apply_item_properties(child, value)

            if value.get("children"):
                self._add_items(child, value["children"])

    def _apply_item_properties(self, item: QTreeWidgetItem, spec: dict[str, Any]) -> None:
        """Set icon, tooltip, and data roles for the given tree item."""
        item_type = spec.get("type", "folder")
        method = spec.get("method", "GET")
        name = spec.get("name", "")

        if item_type == "request":
            item.setToolTip(0, f"{method} {name}")
            item.setData(0, ROLE_METHOD, method)
        else:
            item.setToolTip(0, name)
            self._set_item_icon(item, item_type, method)

    # ----------------------------------------------------------------------
    # UI helpers
    # ----------------------------------------------------------------------

    def _set_item_icon(self, item: QTreeWidgetItem, i_type: str, method: str) -> None:
        """Set the Phosphor folder icon on a tree item."""
        item.setIcon(0, phi("folder"))

    def select_item_by_id(self, item_id: int, item_type: str) -> None:
        """Select and scroll to the item with the given ID and type after data load."""
        target = self._find_item_by_id(self._tree.invisibleRootItem(), item_id, item_type)
        if target:
            self._tree.setCurrentItem(target)
            self._tree.scrollToItem(target, QTreeWidget.ScrollHint.EnsureVisible)

    def start_rename_by_id(self, item_id: int, item_type: str) -> None:
        """Select the item and immediately enter in-place rename mode."""
        target = self._find_item_by_id(self._tree.invisibleRootItem(), item_id, item_type)
        if target is None:
            return
        self._tree.setCurrentItem(target)
        self._tree.scrollToItem(target, QTreeWidget.ScrollHint.EnsureVisible)
        self._current_item = target
        self._handle_rename(item_id, item_type)

    def update_item_name(self, item_id: int, item_type: str, new_name: str) -> None:
        """Programmatically update the display text of a tree item.

        Finds the item by *item_id* / *item_type* and sets its text
        without triggering rename signals.  Requests use column 1
        (read by the delegate), folders use column 0.
        """
        target = self._find_item_by_id(self._tree.invisibleRootItem(), item_id, item_type)
        if target is None:
            return
        col = 1 if item_type == "request" else 0
        self._tree.blockSignals(True)
        try:
            target.setText(col, new_name)
        finally:
            self._tree.blockSignals(False)

        # Force an immediate repaint — the delegate reads column 1 but
        # paints in column 0, so Qt may not schedule a repaint on its own.
        self._tree.viewport().update()

    def update_request_method(self, request_id: int, method: str) -> None:
        """Update the HTTP method badge of a request tree item in-place.

        Finds the item by *request_id* and updates its ``ROLE_METHOD``
        data and tooltip without rebuilding the entire tree.
        """
        target = self._find_item_by_id(self._tree.invisibleRootItem(), request_id, "request")
        if target is None:
            return
        self._tree.blockSignals(True)
        try:
            target.setData(0, ROLE_METHOD, method)
            name = target.text(1) or target.text(0)
            target.setToolTip(0, f"{method} {name}")
        finally:
            self._tree.blockSignals(False)
        self._tree.viewport().update()

        # --- Incremental helpers ---

    def add_collection(self, new_collection: dict, parent_id: int | None) -> None:
        """Insert a new collection folder into the tree."""
        spec = {
            "name": new_collection["name"],
            "id": new_collection["id"],
            "type": "folder",
            "children": {},
        }

        self._tree.blockSignals(True)  # <<< NEW
        try:
            if parent_id is None:
                root_item = QTreeWidgetItem(self._tree, [spec["name"]])
                root_item.setData(0, ROLE_ITEM_ID, spec["id"])
                root_item.setData(0, ROLE_ITEM_TYPE, spec["type"])  # col 0 for delegate
                root_item.setData(1, ROLE_ITEM_TYPE, spec["type"])  # col 1 legacy
                self._apply_item_properties(root_item, spec)
                self._tree.addTopLevelItem(root_item)
            else:
                parent_item = self._find_item_by_id(
                    self._tree.invisibleRootItem(), parent_id, "folder"
                )
                if parent_item is None:
                    logger.warning("Parent folder id=%s not found in tree; skipping", parent_id)
                    return
                self._remove_placeholder(parent_item)
                child = QTreeWidgetItem(parent_item, [spec["name"]])
                child.setData(0, ROLE_ITEM_ID, spec["id"])
                child.setData(0, ROLE_ITEM_TYPE, spec["type"])  # col 0 for delegate
                child.setData(1, ROLE_ITEM_TYPE, spec["type"])  # col 1 legacy
                child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                self._apply_item_properties(child, spec)
                parent_item.setExpanded(True)
        finally:
            self._tree.blockSignals(False)
        self._update_stack_visibility()

    def add_request(self, new_request: dict, parent_id: int) -> None:
        """Insert a new request item under the given parent collection."""
        spec = {
            "name": new_request["name"],
            "id": new_request["id"],
            "type": "request",
            "method": new_request["method"].upper(),
            "url": new_request["url"],
        }
        self._tree.blockSignals(True)  # <<< NEW
        try:
            parent_item = self._find_item_by_id(self._tree.invisibleRootItem(), parent_id, "folder")
            if parent_item is None:
                logger.warning("Parent folder id=%s not found in tree; skipping", parent_id)
                return

            # Remove placeholder if it exists
            self._remove_placeholder(parent_item)

            child = QTreeWidgetItem(parent_item, ["", spec["name"]])
            child.setData(0, ROLE_ITEM_ID, spec.get("id"))  # id
            child.setData(0, ROLE_ITEM_TYPE, spec.get("type"))  # type (col 0 for delegate)
            child.setData(1, ROLE_ITEM_TYPE, spec.get("type"))  # type (col 1 legacy)
            child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator)

            self._apply_item_properties(child, spec)
            parent_item.setExpanded(True)
        finally:
            self._tree.blockSignals(False)

    def remove_item(self, item_id: int, item_type: str) -> None:
        """Remove the item with *item_id* and *item_type* from the tree."""
        root = self._tree.invisibleRootItem()
        item = self._find_item_by_id(root, item_id, item_type)
        if item:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                self._tree.takeTopLevelItem(self._tree.indexOfTopLevelItem(item))
        self._update_stack_visibility()

    # ------------------------------------------------------------------
    # Loading state
    # ------------------------------------------------------------------
    def show_loading(self) -> None:
        """Switch the stack to the loading page and start the dot animation."""
        self._loading_dot_count = 0
        self._loading_label.setText("Loading collections")
        self._stack.setCurrentIndex(2)
        self._loading_timer.start()

    def hide_loading(self) -> None:
        """Stop the loading animation (caller should set the real page next)."""
        self._loading_timer.stop()

    def _animate_loading_dots(self) -> None:
        """Cycle the trailing dots on the loading label (0-3)."""
        self._loading_dot_count = (self._loading_dot_count + 1) % 4
        dots = "." * self._loading_dot_count
        self._loading_label.setText(f"Loading collections{dots}")

    def _update_stack_visibility(self) -> None:
        """Switch between the empty-state placeholder and the tree."""
        has_items = self._tree.topLevelItemCount() > 0
        self._stack.setCurrentIndex(1 if has_items else 0)
