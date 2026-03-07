"""Tree action mixin — context menus, rename, delete, and keyboard shortcuts.

Provides ``_TreeActionsMixin`` with context-menu setup, in-place
rename editing, delete confirmation, and keyboard shortcut handling.
Mixed into ``CollectionTree``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal, Slot
from PySide6.QtGui import QAction, QKeyEvent
from PySide6.QtWidgets import QLineEdit, QMenu, QMessageBox, QTreeWidgetItem

from ui.collections.tree.constants import (
    PLACEHOLDER_MARKER,
    ROLE_ITEM_ID,
    ROLE_ITEM_TYPE,
    ROLE_OLD_NAME,
    ROLE_PLACEHOLDER,
)
from ui.styling.theme import COLOR_ACCENT

if TYPE_CHECKING:
    from ui.collections.tree.draggable_tree_widget import DraggableTreeWidget

    _TreeActionsBase = QObject
else:
    _TreeActionsBase = object


class _TreeActionsMixin(_TreeActionsBase):
    """Mixin that adds context menus, rename/delete actions, and key shortcuts.

    Expects the host class to provide ``_tree``, ``_current_item``,
    ``item_action_triggered``, ``item_name_changed``,
    ``collection_rename_requested``, ``collection_delete_requested``,
    ``request_rename_requested``, ``request_delete_requested``,
    ``new_collection_requested``, and ``new_request_requested`` signals.
    """

    # -- Host-class interface (declared for mypy) -----------------------
    _tree: DraggableTreeWidget
    _current_item: QTreeWidgetItem | None
    item_action_triggered: Signal
    item_name_changed: Signal
    collection_rename_requested: Signal
    collection_delete_requested: Signal
    request_rename_requested: Signal
    request_delete_requested: Signal
    new_collection_requested: Signal
    new_request_requested: Signal

    if TYPE_CHECKING:

        def _count_real_children(self, item: QTreeWidgetItem) -> int: ...
        def _expand_all_recursive(self, item: QTreeWidgetItem, *, expand: bool) -> None: ...
        def remove_item(self, item_id: int, item_type: str) -> None: ...

    # -- Context menus -------------------------------------------------

    def _setup_context_menus(self) -> None:
        """Create the context menus for request and folder items."""
        # --- Request menu ---
        self._request_menu = QMenu(self._tree)
        for label, _icon_name in [
            ("Open", "arrow-square-out"),
            ("Rename", "pencil-simple"),
            ("Delete", "trash"),
        ]:
            action = self._request_menu.addAction(label)
            action.setData(label)
        self._request_menu.triggered.connect(self._emit_menu_action)

        # --- Folder menu ---
        self._folder_menu = QMenu(self._tree)
        for label, _icon_name in [
            ("Overview", "eye"),
            ("Add request", "plus"),
            ("Add folder", "folder-plus"),
        ]:
            action = self._folder_menu.addAction(label)
            action.setData(label)
        self._folder_menu.addSeparator()
        for label, _icon_name in [
            ("Expand all", "arrows-out"),
            ("Collapse all", "arrows-in"),
        ]:
            action = self._folder_menu.addAction(label)
            action.setData(label)
        self._folder_menu.addSeparator()
        for label, _icon_name in [
            ("Rename", "pencil-simple"),
            ("Delete", "trash"),
        ]:
            action = self._folder_menu.addAction(label)
            action.setData(label)
        self._folder_menu.triggered.connect(self._emit_menu_action)

    # -- Keyboard shortcut handling ------------------------------------

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Handle F2 (rename) and Delete keyboard shortcuts on the tree."""
        if obj is not self._tree or event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, event)  # type: ignore[misc]

        key_event: QKeyEvent = event  # type: ignore[assignment]
        key = key_event.key()

        current = self._tree.currentItem()
        if current is None:
            return super().eventFilter(obj, event)  # type: ignore[misc]

        item_id = current.data(0, ROLE_ITEM_ID)
        item_type = current.data(1, ROLE_ITEM_TYPE)
        if item_id is None or item_type is None:
            return super().eventFilter(obj, event)  # type: ignore[misc]

        self._current_item = current

        if key == Qt.Key.Key_F2:
            self._handle_rename(item_id, item_type)
            return True
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._handle_delete(item_id, item_type)
            return True

        return super().eventFilter(obj, event)  # type: ignore[misc]

    # -- Context menu dispatch -----------------------------------------

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
        if not self._current_item:
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
        elif action_name == "Overview" and item_type == "folder":
            self.item_action_triggered.emit("folder", item_id, "Open")
        elif action_name == "Expand all" and item_type == "folder":
            self._expand_all_recursive(self._current_item, expand=True)
        elif action_name == "Collapse all" and item_type == "folder":
            self._expand_all_recursive(self._current_item, expand=False)
        else:
            self.item_action_triggered.emit(item_type, item_id, action_name)

    # -- Rename / Delete handlers --------------------------------------

    def _handle_rename(self, item_id: int, item_type: str) -> None:
        """Start in-place rename for the current item."""
        if self._current_item is None:
            return
        if item_type == "folder":
            self._rename_folder(item_id, self._current_item)
        elif item_type == "request":
            self._rename_request(item_id, self._current_item)

    def _handle_delete(self, item_id: int, item_type: str) -> None:
        """Show a confirmation dialog and delete the item if accepted."""
        if self._current_item is None:
            return
        if item_type == "folder":
            child_count = self._count_real_children(self._current_item)
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
            self._tree,
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

        An overlay ``QLineEdit`` is positioned over the item's visual
        rectangle inside the tree viewport.  This avoids relying on
        ``setItemWidget`` which is no longer used for request items.
        """
        if tree_item is None:
            return

        old_name = tree_item.text(1)  # Requests store name in column 1
        tree_item.setData(1, ROLE_OLD_NAME, old_name)

        # Calculate geometry inside the viewport
        item_rect = self._tree.visualItemRect(tree_item)
        viewport = self._tree.viewport()

        line_edit = QLineEdit(old_name, viewport)
        line_edit.setStyleSheet(f"padding-left: 2px; border: 1px solid {COLOR_ACCENT};")
        line_edit.setGeometry(item_rect)
        line_edit.selectAll()
        line_edit.show()
        line_edit.setFocus()

        # Connect signals
        line_edit.returnPressed.connect(
            lambda: self._finish_request_rename(tree_item, line_edit, True)
        )
        line_edit.editingFinished.connect(
            lambda: self._finish_request_rename(tree_item, line_edit, False)
        )

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

        # Remove the overlay line edit
        line_edit.hide()
        line_edit.deleteLater()

        # Update if name changed
        if new_name and new_name != old_name:
            item_id = tree_item.data(0, ROLE_ITEM_ID)
            tree_item.setText(1, new_name)
            self.request_rename_requested.emit(item_id, new_name)

        tree_item.setData(1, ROLE_OLD_NAME, None)

    @Slot(QTreeWidgetItem, int)
    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Persist a folder rename and make the item read-only again.

        Signals are blocked to avoid recursion from programmatic changes.
        Requests are handled separately via _finish_request_rename.
        """
        # Only handle column 0 (folders)
        if column != 0:
            return

        if item.data(1, ROLE_PLACEHOLDER) == PLACEHOLDER_MARKER:
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
