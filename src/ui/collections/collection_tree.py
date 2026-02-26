"""Tree widget displaying collections and requests with drag-drop and context menus."""

from __future__ import annotations

import logging
from typing import Any, cast

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal, Slot
from PySide6.QtGui import QAction, QDropEvent, QIcon
from PySide6.QtWidgets import (QApplication, QBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QMessageBox, QStyle,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ui.theme import (COLOR_ACCENT, COLOR_TEXT_MUTED, DEFAULT_METHOD_COLOR,
                      METHOD_COLORS)

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Data roles stored on QTreeWidgetItems
# ----------------------------------------------------------------------
ROLE_ITEM_ID = Qt.ItemDataRole.UserRole  # column 0 - database PK
ROLE_ITEM_TYPE = Qt.ItemDataRole.UserRole + 1  # column 1 - "folder" or "request"
ROLE_OLD_NAME = Qt.ItemDataRole.UserRole + 2  # column 1 - original name (rename rollback)
ROLE_LINE_EDIT = Qt.ItemDataRole.UserRole + 3  # column 1 - QLineEdit ref during rename
ROLE_NAME_LABEL = Qt.ItemDataRole.UserRole + 4  # column 1 - QLabel ref during rename
ROLE_MIME_DATA = Qt.ItemDataRole.UserRole + 5  # column 3 - drag/drop QMimeData
ROLE_PLACEHOLDER = Qt.ItemDataRole.UserRole + 10  # column 1 - "placeholder" marker

# ----------------------------------------------------------------------
# Helper constants
# ----------------------------------------------------------------------
_PLACEHOLDER_MARKER = "placeholder"

_ICON_CACHE: dict[str, QIcon] = {}


# ----------------------------------------------------------------------
# Custom QTreeWidget to handle drop events
# ----------------------------------------------------------------------
class DraggableTreeWidget(QTreeWidget):
    """QTreeWidget subclass that handles drag-and-drop between collections.

    Emits ``request_moved`` / ``collection_moved`` signals so the service
    layer can persist the change.  Drops onto request items are rejected.
    """

    # Signals emitted when a drop requires a DB update.
    # The parent ``CollectionTree`` connects these to its own signals so the
    # service layer (in ``CollectionWidget``) can do the actual persistence.
    request_moved = Signal(int, int)  # request_id, new_collection_id
    collection_moved = Signal(int, object)  # collection_id, new_parent_id (int | None)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the draggable tree widget."""
        super().__init__(parent)

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop events with validation and parent_id updates."""
        source_item = self.currentItem()
        target_item = self.itemAt(event.pos())

        if not source_item or not target_item:
            event.ignore()
            return

        # Get item types
        source_type = source_item.data(1, ROLE_ITEM_TYPE)
        target_type = target_item.data(1, ROLE_ITEM_TYPE)

        # Validation: Cannot drop request or folder into a request
        if target_type == "request":
            event.ignore()
            return

        # Get IDs
        source_id = source_item.data(0, ROLE_ITEM_ID)
        target_id = target_item.data(0, ROLE_ITEM_ID)

        new_parent_id = target_id if target_type == "folder" else None

        # Validation: Cannot drop request at root level
        if source_type == "request" and new_parent_id is None:
            event.ignore()
            return

        # Emit the appropriate signal — the service layer will persist this
        try:
            if source_type == "request":
                self.request_moved.emit(source_id, new_parent_id)
            elif source_type == "folder":
                self.collection_moved.emit(source_id, new_parent_id)
        except Exception as exc:
            logger.error("Failed to emit move signal: %s", exc)
            event.ignore()
            return

        # Accept the drop and let Qt handle the visual update
        super().dropEvent(event)


# ----------------------------------------------------------------------
# Tree management subclass
# ----------------------------------------------------------------------
class CollectionTree(QWidget):
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

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the collection tree widget and context menus."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tree = DraggableTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.currentItemChanged.connect(self._on_current_item_changed)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemCollapsed.connect(self._on_item_collapsed)

        # Forward drag-and-drop signals from the tree widget
        self._tree.request_moved.connect(self.request_moved)
        self._tree.collection_moved.connect(self.collection_moved)

        self._tree.setDragEnabled(True)
        self._tree.setAcceptDrops(True)
        self._tree.setDropIndicatorShown(True)
        self._tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self._tree.viewport().setAcceptDrops(True)

        layout.addWidget(self._tree)

        self._setup_context_menus()
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_tree_context_menu)

    def _setup_context_menus(self) -> None:
        """Create the request- and folder-specific menus and connect actions."""
        # --- Request menu ---
        self._request_menu = QMenu(self._tree)
        for act_name in ("Open", "Copy", "|", "Rename", "Delete"):
            if act_name == "|":
                self._request_menu.addSeparator()
            else:
                act = QAction(act_name, self._tree)
                act.setData(act_name)  # <-- store action type as the action's data
                act.triggered.connect(lambda checked, a=act: self._emit_menu_action(a))
                self._request_menu.addAction(act)

        # --- Folder menu ---
        self._folder_menu = QMenu(self._tree)
        for act_name in ("Add folder", "Add request", "|", "Rename", "Delete"):
            if act_name == "|":
                self._folder_menu.addSeparator()
            else:
                act = QAction(act_name, self._tree)
                act.setData(act_name)  # <-- same here
                act.triggered.connect(lambda checked, a=act: self._emit_menu_action(a))
                self._folder_menu.addAction(act)

    @Slot(QTreeWidgetItem, QTreeWidgetItem)
    def _on_current_item_changed(self, current, previous) -> None:
        """Reset any item left in editable state when the selection changes.

        When the user selects a new item we make sure that any item that was
        left in “editable” state (because the edit was cancelled) is reset.
        """
        if previous and previous.flags() & Qt.ItemFlag.ItemIsEditable:
            # Undo the flag - the editor is gone
            previous.setFlags(previous.flags() & ~Qt.ItemFlag.ItemIsEditable)

    @Slot(QTreeWidgetItem)
    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Show placeholder if folder is empty when expanded."""
        item_type = item.data(1, ROLE_ITEM_TYPE)
        if item_type == "folder":
            real_children = self._count_real_children(item)
            if real_children == 0:
                self._add_placeholder(item)

    @Slot(QTreeWidgetItem)
    def _on_item_collapsed(self, item: QTreeWidgetItem) -> None:
        """Remove placeholder when folder is collapsed."""
        self._remove_placeholder(item)

    def _count_real_children(self, item: QTreeWidgetItem) -> int:
        """Count children that are not placeholders."""
        count = 0
        for i in range(item.childCount()):
            child = item.child(i)
            if child.data(1, ROLE_PLACEHOLDER) != _PLACEHOLDER_MARKER:
                count += 1
        return count

    def _add_placeholder(self, parent_item: QTreeWidgetItem) -> None:
        """Add a placeholder item to an empty folder."""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.data(1, ROLE_PLACEHOLDER) == _PLACEHOLDER_MARKER:
                return

        placeholder = QTreeWidgetItem(parent_item, [""])
        placeholder.setData(1, ROLE_PLACEHOLDER, _PLACEHOLDER_MARKER)
        placeholder.setFlags(Qt.ItemFlag.ItemIsEnabled)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)

        _EMPTY_COLLECTION_HTML = (
            "This collection is empty.<br>"
            f'<a href="#" style="color: {COLOR_ACCENT};">Add a request</a>'
            " to start working."
        )
        label = QLabel(_EMPTY_COLLECTION_HTML)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-style: italic;")
        label.setWordWrap(True)
        label.linkActivated.connect(lambda: self._on_placeholder_link_clicked(parent_item))

        layout.addWidget(label)
        self._tree.setItemWidget(placeholder, 0, widget)

    def _remove_placeholder(self, parent_item: QTreeWidgetItem) -> None:
        """Remove placeholder item from a folder."""
        for i in range(parent_item.childCount() - 1, -1, -1):
            child = parent_item.child(i)
            if child.data(1, ROLE_PLACEHOLDER) == _PLACEHOLDER_MARKER:
                parent_item.removeChild(child)

    def _on_placeholder_link_clicked(self, parent_item: QTreeWidgetItem) -> None:
        """Handle click on 'Add a request' link in placeholder."""
        parent_id = parent_item.data(0, ROLE_ITEM_ID)
        if parent_id is not None:
            self.new_request_requested.emit(parent_id)

    @Slot(QPoint)
    def _on_tree_context_menu(self, pos: QPoint) -> None:
        """Show a context-menu depending on the clicked item's type."""
        item = self._tree.itemAt(pos)
        if not item:
            return

        # Keep a reference to the clicked item so the triggered action knows
        # which item it belongs to.
        self._current_item = item

        # Grab the stored type (set in set_collections/_add_items)
        item_type = item.data(1, ROLE_ITEM_TYPE)  # "request" or "folder"

        menu = self._request_menu if item_type == "request" else self._folder_menu
        menu.exec(self._tree.mapToGlobal(pos))

    def _emit_menu_action(self, action: QAction) -> None:
        """Dispatch context-menu actions to dedicated handler methods."""
        if not hasattr(self, "_current_item") or not self._current_item:
            return

        item_type = self._current_item.data(1, ROLE_ITEM_TYPE)
        item_id = self._current_item.data(0, ROLE_ITEM_ID)
        action_name = action.data() or action.text()

        if action_name == "Rename":
            self._handle_rename(item_id, item_type)
        elif action_name == "Delete":
            self._handle_delete(item_id, item_type)
        elif action_name == "Add folder" and item_type == "folder":
            self.new_collection_requested.emit(item_id)
        elif action_name == "Add request" and item_type == "folder":
            self.new_request_requested.emit(item_id)
        else:
            self.item_action_triggered.emit(item_type, item_id, action_name)

    def _handle_rename(self, item_id: int, item_type: str) -> None:
        """Start in-place rename for the current item."""
        if item_type == "folder":
            self._rename_folder(item_id, self._current_item)
        elif item_type == "request":
            self._rename_request(item_id, self._current_item)

    def _handle_delete(self, item_id: int, item_type: str) -> None:
        """Show a confirmation dialog and delete the item if accepted."""
        if item_type == "folder":
            child_count = self._current_item.childCount()
            if child_count > 0:
                msg = (
                    "Are you sure you want to delete this folder?\n\n"
                    f"This will also delete {child_count} item(s) inside it."
                )
            else:
                msg = "Are you sure you want to delete this folder?"
        else:
            msg = "Are you sure you want to delete this request?"

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if item_type == "folder":
            self.collection_delete_requested.emit(item_id)
        elif item_type == "request":
            self.request_delete_requested.emit(item_id)
        self.remove_item(item_id, item_type)

    def _rename_folder(self, item_id: int, tree_item: QTreeWidgetItem) -> None:
        """Initiate in-place renaming of a folder item in the UI tree.

        Parameters
        ----------
        item_id : Any
            The identifier of the item being renamed (unused in the current implementation but kept for API consistency).
        tree_item : QTreeWidgetItem
            The tree item that the user has selected to rename.

        Notes:
        -----
        The method temporarily blocks signals to prevent unwanted side-effects,
        sets the item to be editable, and triggers the built-in editor widget
        for the item. The original name is stored in the item's data for later
        reference or rollback if needed.
        """
        if tree_item is not None:
            old_name = tree_item.text(0)
            tree_item.setData(1, ROLE_OLD_NAME, old_name)
            # Block briefly to avoid interim signals
            self._tree.blockSignals(True)
            try:
                tree_item.setFlags(tree_item.flags() | Qt.ItemFlag.ItemIsEditable)
            finally:
                self._tree.blockSignals(False)
            self._tree.editItem(tree_item, 0)

    def _rename_request(self, item_id: int, tree_item: QTreeWidgetItem) -> None:
        """Initiate in-place renaming of a request item in the UI tree.

        Parameters
        ----------
        item_id : Any
            The identifier of the item being renamed (unused in the current implementation but kept for API consistency).
        tree_item : QTreeWidgetItem
            The tree item that the user has selected to rename.

        Notes:
        -----
        The method temporarily blocks signals to prevent unwanted side-effects,
        sets the item to be editable, and triggers the built-in editor widget
        for the item. The original name is stored in the item's data for later
        reference or rollback if needed.
        """
        if tree_item is not None:
            old_name = tree_item.text(1)  # Requests store name in column 1
            tree_item.setData(1, ROLE_OLD_NAME, old_name)

            # Get the widget and replace the label with a line edit
            widget = self._tree.itemWidget(tree_item, 0)
            if widget:
                layout = widget.layout()
                if layout and layout.count() >= 2:
                    # Get and hide the name label
                    layout_item = layout.itemAt(1)
                    name_label = layout_item.widget() if layout_item else None
                    if name_label:
                        name_label.hide()

                        # Create a line edit for editing
                        line_edit = QLineEdit(old_name)
                        line_edit.setStyleSheet(
                            f"padding-left: 0px; border: 1px solid {COLOR_ACCENT};"
                        )
                        line_edit.selectAll()

                        # Store references
                        tree_item.setData(1, ROLE_LINE_EDIT, line_edit)
                        tree_item.setData(1, ROLE_NAME_LABEL, name_label)

                        # Connect signals
                        line_edit.returnPressed.connect(
                            lambda: self._finish_request_rename(tree_item, line_edit, True)
                        )
                        line_edit.editingFinished.connect(
                            lambda: self._finish_request_rename(tree_item, line_edit, False)
                        )

                        # Insert the line edit after the badge
                        box_layout = cast(QBoxLayout, layout)
                        box_layout.insertWidget(1, line_edit)
                        line_edit.setFocus()

    def _finish_request_rename(
        self,
        tree_item: QTreeWidgetItem,
        line_edit: QLineEdit,
        from_return: bool,
    ) -> None:
        """Complete the request rename operation."""
        if not line_edit or not tree_item:
            return

        # Prevent multiple calls
        if not line_edit.isVisible():
            return

        new_name = line_edit.text().strip()
        old_name = tree_item.data(1, ROLE_OLD_NAME)
        name_label = tree_item.data(1, ROLE_NAME_LABEL)

        if not name_label:
            return

        # Remove the line edit
        line_edit.hide()
        line_edit.deleteLater()

        # Update if name changed
        if new_name and new_name != old_name:
            item_id = tree_item.data(0, ROLE_ITEM_ID)
            tree_item.setText(1, new_name)
            name_label.setText(new_name)
            self.request_rename_requested.emit(item_id, new_name)
        else:
            # Revert to old name
            name_label.setText(old_name)

        # Show the label again
        name_label.show()
        tree_item.setData(1, ROLE_OLD_NAME, None)
        tree_item.setData(1, ROLE_LINE_EDIT, None)
        tree_item.setData(1, ROLE_NAME_LABEL, None)

    @Slot(QTreeWidgetItem, int)
    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Persist a folder rename and make the item read-only again.

        Signals are blocked to avoid recursion from programmatic changes.
        Requests are handled separately via _finish_request_rename.
        """
        # Only handle column 0 (folders)
        if column != 0:
            return

        if item.data(1, ROLE_PLACEHOLDER) == _PLACEHOLDER_MARKER:
            return

        item_type = item.data(1, ROLE_ITEM_TYPE)
        # Skip requests as they're handled separately
        if item_type == "request":
            return

        self._tree.blockSignals(True)
        try:
            new_name = item.text(column).strip()
            old_name = item.data(1, ROLE_OLD_NAME) or "Unnamed"

            if new_name == old_name:
                return

            if not new_name:
                item.setText(column, old_name)
                return

            item_id = item.data(0, ROLE_ITEM_ID)
            item.setData(1, ROLE_OLD_NAME, None)
            self.collection_rename_requested.emit(item_id, new_name)
            self.item_name_changed.emit(item_type, item_id, new_name)

        finally:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._tree.blockSignals(False)

    def _find_item_by_id(
        self, parent: QTreeWidgetItem, target_id: int, target_type: str
    ) -> QTreeWidgetItem | None:
        """Recursively search for an item whose UserRole data matches *target_id*."""
        # Check if the current node matches
        key = f"{target_type}:{target_id}"
        current_key = f"{parent.data(1, ROLE_ITEM_TYPE)}:{parent.data(0, ROLE_ITEM_ID)}"

        # Check the current node
        if key == current_key:
            return parent

        # Search children
        for i in range(parent.childCount()):
            child = parent.child(i)
            found = self._find_item_by_id(child, target_id, target_type)
            if found:
                return found

        return None

    # ----------------------------------------------------------------------
    # Public API for tree management
    # ----------------------------------------------------------------------
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
                root_item.setData(1, ROLE_ITEM_TYPE, value.get("type"))  # type

                # 3. Apply icon / widget
                self._apply_item_properties(root_item, value)

                # 4. Add children (requests / sub-folders)
                self._add_items(root_item, value.get("children", {}))
        finally:
            self._tree.blockSignals(False)
        # self._tree.expandAll()

    def _add_items(self, parent: QTreeWidgetItem, mapping: dict[str, Any]) -> None:
        for _key, value in mapping.items():
            # Use the request name for the *visible* column,
            # the empty string for the “hidden” column that will hold the badge.
            child = QTreeWidgetItem(
                parent, [value["name"] if value.get("type") != "request" else "", value["name"]]
            )

            # Store the ID on the item (folder or request)
            child.setData(0, ROLE_ITEM_ID, value.get("id"))  # id
            child.setData(1, ROLE_ITEM_TYPE, value.get("type"))  # type

            # Only show indicator for folders
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
        item_type = spec.get("type", "folder")
        method = spec.get("method", "GET")

        # Store the data that will be read in dropEvent
        mime = QMimeData()
        mime.setText(str(spec["id"]))  # the id of the item
        mime.setData("application/x-itemtype", item_type.encode())  # "folder" or "request"

        # Tell the widget to use that mime data for the drag
        item.setData(3, ROLE_MIME_DATA, mime)  # a custom role just for drag data

        if item_type == "folder":
            self._set_item_icon(item, item_type, method)
        else:
            self._set_item_widget(item, method, item.text(1))

    # ----------------------------------------------------------------------
    # UI helpers (update setItemWidget and setIcon to use self._tree)
    # ----------------------------------------------------------------------
    def _method_color(self, method: str) -> str:
        """Return the theme colour for a given HTTP method."""
        return METHOD_COLORS.get(method.upper(), DEFAULT_METHOD_COLOR)

    def _set_item_widget(self, item: QTreeWidgetItem, method: str, url: str) -> None:
        """Place a coloured badge (method) next to the request URL."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        badge = QLabel(method.upper())
        badge.setStyleSheet(
            f"""
            background-color: {self._method_color(method)};
            color: white;
            padding: 0px 0px 0 2px;
            margin-right: 3px;
            border-radius: 3px;
            font-weight: bold;
            font-size: 8px;

            """
        )
        label = QLabel(url)
        label.setStyleSheet("padding-left: 0px;")
        layout.addWidget(badge)
        layout.addWidget(label)
        layout.addStretch(1)
        self._tree.setItemWidget(item, 0, widget)  # <-- Use self._tree

    def _set_item_icon(self, item: QTreeWidgetItem, i_type: str, method: str) -> None:
        """Use a system icon if available; otherwise use the Qt style's standard icon."""
        if i_type not in _ICON_CACHE:
            theme_icon = QIcon.fromTheme(i_type)
            if theme_icon.isNull():
                style = QApplication.style()
                theme_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
            _ICON_CACHE[i_type] = theme_icon
        item.setIcon(0, _ICON_CACHE[i_type])

    def select_item_by_id(self, item_id: int, item_type: str) -> None:
        """Select and scroll to the item with the given ID and type after data load."""
        target = self._find_item_by_id(self._tree.invisibleRootItem(), item_id, item_type)
        if target:
            self._tree.setCurrentItem(target)
            self._tree.scrollToItem(target, QTreeWidget.ScrollHint.EnsureVisible)

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
                root_item.setData(1, ROLE_ITEM_TYPE, spec["type"])
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
                child.setData(1, ROLE_ITEM_TYPE, spec["type"])
                child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                self._apply_item_properties(child, spec)
                parent_item.setExpanded(True)
        finally:
            self._tree.blockSignals(False)

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

            child = QTreeWidgetItem(
                parent_item, [spec["name"] if spec.get("type") != "request" else "", spec["name"]]
            )
            child.setData(0, ROLE_ITEM_ID, spec.get("id"))  # id
            child.setData(1, ROLE_ITEM_TYPE, spec.get("type"))  # type
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
