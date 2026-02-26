"""QTreeWidget subclass with drag-and-drop support for collection items."""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QTreeWidget, QWidget

from ui.collections.tree.constants import ROLE_ITEM_ID, ROLE_ITEM_TYPE

logger = logging.getLogger(__name__)


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

        # Emit the appropriate signal -- the service layer will persist this
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
