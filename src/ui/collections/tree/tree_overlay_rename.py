"""Overlay rename helpers for collection and local-scripts trees."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QLineEdit, QTreeWidgetItem
from shiboken6 import Shiboken

from ui.collections.tree.constants import (
    ITEM_TYPE_FOLDER,
    ROLE_ITEM_ID,
    ROLE_ITEM_TYPE,
    ROLE_LINE_EDIT,
    ROLE_OLD_LANGUAGE,
    ROLE_OLD_MODULE_FORMAT,
    ROLE_OLD_NAME,
    is_leaf_item_type,
)
from ui.local_scripts.script_filename import folder_name_from_input, script_folder_label_rect
from ui.widgets.tree_rename_overlay import TreeRenameClickAway

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from ui.collections.tree.draggable_tree_widget import DraggableTreeWidget

    _TreeOverlayRenameBase = QObject
else:
    _TreeOverlayRenameBase = object


class _TreeOverlayRenameMixin(_TreeOverlayRenameBase):
    """Click-away overlay rename for collection/local-scripts folders and requests."""

    _tree: DraggableTreeWidget
    collection_rename_requested: Signal
    request_rename_requested: Signal
    item_name_changed: Signal

    def _rename_click_away(self) -> TreeRenameClickAway:
        """Return the shared click-away helper for overlay renames."""
        helper = getattr(self, "_tree_rename_click_away", None)
        if helper is None:
            helper = TreeRenameClickAway(self)  # type: ignore[arg-type]
            self._tree_rename_click_away = helper  # type: ignore[attr-defined]
        return helper

    def _rename_overlay_active(self) -> bool:
        """Return whether a tree rename overlay editor is open."""
        return self._rename_click_away().is_active()

    def _arm_rename_overlay(
        self,
        line_edit: QLineEdit,
        *,
        on_commit: Callable[[bool], None],
        on_cancel: Callable[[], None],
    ) -> None:
        """Defer ``editingFinished`` commit and wire click-away / Escape."""
        line_edit.setProperty("rename_armed", False)

        def _safe_commit(from_return: bool) -> None:
            if not Shiboken.isValid(line_edit):
                return
            on_commit(from_return)

        line_edit.returnPressed.connect(lambda: _safe_commit(True))

        def _arm() -> None:
            if not Shiboken.isValid(line_edit):
                return
            line_edit.setProperty("rename_armed", True)
            line_edit.editingFinished.connect(lambda: _safe_commit(False))

        arm_timer = QTimer(line_edit)
        arm_timer.setSingleShot(True)
        arm_timer.timeout.connect(_arm)
        arm_timer.start(0)
        self._rename_click_away().arm(
            line_edit,
            on_commit=lambda: on_commit(False),
            on_cancel=on_cancel,
        )

    def _rename_folder_overlay(self, _item_id: int, tree_item: QTreeWidgetItem) -> None:
        """Overlay rename for a collection or local-scripts folder row."""
        old_name = tree_item.text(0)
        tree_item.setData(1, ROLE_OLD_NAME, old_name)
        item_rect = self._tree.visualItemRect(tree_item)
        name_rect = script_folder_label_rect(self._tree, tree_item, item_rect)
        line_edit = QLineEdit(old_name, self._tree.viewport())
        line_edit.setObjectName("scriptTreeRenameEdit")
        line_edit.setGeometry(name_rect)
        line_edit.selectAll()
        line_edit.show()
        line_edit.setFocus()
        tree_item.setData(1, ROLE_LINE_EDIT, line_edit)

        self._arm_rename_overlay(
            line_edit,
            on_commit=lambda from_return: self._finish_folder_rename(
                tree_item, line_edit, from_return
            ),
            on_cancel=lambda: self._cancel_folder_rename(tree_item, line_edit),
        )

    def _rename_request_overlay(self, _item_id: int, tree_item: QTreeWidgetItem) -> None:
        """Overlay rename for a collection request row (name in column 1)."""
        old_name = tree_item.text(1)
        tree_item.setData(1, ROLE_OLD_NAME, old_name)
        item_rect = self._tree.visualItemRect(tree_item)
        line_edit = QLineEdit(old_name, self._tree.viewport())
        line_edit.setObjectName("scriptTreeRenameEdit")
        line_edit.setGeometry(item_rect)
        line_edit.selectAll()
        line_edit.show()
        line_edit.setFocus()
        tree_item.setData(1, ROLE_LINE_EDIT, line_edit)

        self._arm_rename_overlay(
            line_edit,
            on_commit=lambda from_return: self._finish_request_rename(
                tree_item, line_edit, from_return
            ),
            on_cancel=lambda: self._cancel_request_rename(tree_item, line_edit),
        )

    def _cancel_folder_rename(self, tree_item: QTreeWidgetItem, line_edit: QLineEdit) -> None:
        """Discard folder rename edits and close the overlay."""
        old_name = tree_item.data(1, ROLE_OLD_NAME)
        if not isinstance(old_name, str):
            old_name = tree_item.text(0)
        line_edit.hide()
        line_edit.deleteLater()
        tree_item.setData(1, ROLE_LINE_EDIT, None)
        tree_item.setText(0, old_name)
        tree_item.setData(1, ROLE_OLD_NAME, None)
        self._rename_click_away().release()

    def _cancel_request_rename(self, tree_item: QTreeWidgetItem, line_edit: QLineEdit) -> None:
        """Discard request rename edits and close the overlay."""
        old_name = tree_item.data(1, ROLE_OLD_NAME)
        if not isinstance(old_name, str):
            old_name = tree_item.text(1) or ""
        line_edit.hide()
        line_edit.deleteLater()
        tree_item.setData(1, ROLE_LINE_EDIT, None)
        tree_item.setText(1, old_name)
        tree_item.setData(1, ROLE_OLD_NAME, None)
        self._rename_click_away().release()

    def _cancel_script_rename(self, tree_item: QTreeWidgetItem, line_edit: QLineEdit) -> None:
        """Discard script rename edits and close the overlay."""
        old_basename = tree_item.data(1, ROLE_OLD_NAME)
        if not isinstance(old_basename, str):
            old_basename = ""
        line_edit.hide()
        line_edit.deleteLater()
        tree_item.setData(1, ROLE_LINE_EDIT, None)
        tree_item.setText(1, old_basename)
        tree_item.setData(1, ROLE_OLD_NAME, None)
        tree_item.setData(1, ROLE_OLD_LANGUAGE, None)
        tree_item.setData(1, ROLE_OLD_MODULE_FORMAT, None)
        self._rename_click_away().release()

    def _finish_folder_rename(
        self,
        tree_item: QTreeWidgetItem,
        line_edit: QLineEdit,
        from_return: bool,
    ) -> None:
        """Persist a folder rename from the overlay editor."""
        if line_edit is None:
            return
        if getattr(self, "_rename_committing", False):
            return
        if not from_return and not line_edit.isVisible():
            return
        if not from_return and not line_edit.property("rename_armed"):
            return

        self._rename_committing = True  # type: ignore[attr-defined]
        try:
            old_name = tree_item.data(1, ROLE_OLD_NAME)
            if not isinstance(old_name, str):
                return

            new_name = line_edit.text().strip()
            line_edit.hide()
            line_edit.deleteLater()
            tree_item.setData(1, ROLE_LINE_EDIT, None)
            self._rename_click_away().release()

            if not new_name or new_name == old_name:
                tree_item.setText(0, old_name)
                tree_item.setData(1, ROLE_OLD_NAME, None)
                return

            is_scripts = getattr(self, "_tree_kind", "collections") == "local_scripts"
            if is_scripts:
                validated = folder_name_from_input(new_name)
                if validated is None:
                    tree_item.setText(0, old_name)
                    tree_item.setData(1, ROLE_OLD_NAME, None)
                    return
                new_name = validated

            item_id = tree_item.data(0, ROLE_ITEM_ID)
            item_type = tree_item.data(1, ROLE_ITEM_TYPE) or ITEM_TYPE_FOLDER
            tree_item.setText(0, new_name)
            tree_item.setData(1, ROLE_OLD_NAME, None)
            self.collection_rename_requested.emit(item_id, new_name)
            self.item_name_changed.emit(item_type, item_id, new_name)
        finally:
            self._rename_committing = False  # type: ignore[attr-defined]

    def _finish_request_rename(
        self,
        tree_item: QTreeWidgetItem,
        line_edit: QLineEdit,
        from_return: bool,
    ) -> None:
        """Persist a request rename from the overlay editor."""
        if line_edit is None or not tree_item:
            return
        if getattr(self, "_rename_committing", False):
            return
        if not from_return and not line_edit.isVisible():
            return
        if not from_return and not line_edit.property("rename_armed"):
            return

        self._rename_committing = True  # type: ignore[attr-defined]
        try:
            old_name = tree_item.data(1, ROLE_OLD_NAME)
            if not isinstance(old_name, str):
                return

            new_name = line_edit.text().strip()
            line_edit.hide()
            line_edit.deleteLater()
            tree_item.setData(1, ROLE_LINE_EDIT, None)
            self._rename_click_away().release()

            if not new_name or new_name == old_name:
                tree_item.setText(1, old_name)
                tree_item.setData(1, ROLE_OLD_NAME, None)
                return

            item_id = tree_item.data(0, ROLE_ITEM_ID)
            tree_item.setText(1, new_name)
            tree_item.setData(1, ROLE_OLD_NAME, None)
            self.request_rename_requested.emit(item_id, new_name)
            item_type = tree_item.data(1, ROLE_ITEM_TYPE)
            if isinstance(item_type, str) and is_leaf_item_type(item_type):
                self.item_name_changed.emit(item_type, item_id, new_name)
        finally:
            self._rename_committing = False  # type: ignore[attr-defined]
