"""Tree sub-package — draggable tree widget, collection tree, and shared constants."""

from __future__ import annotations

from ui.collections.tree.collection_tree import CollectionTree
from ui.collections.tree.constants import (
    EMPTY_COLLECTION_HTML,
    ICON_CACHE,
    PLACEHOLDER_MARKER,
    ROLE_ITEM_ID,
    ROLE_ITEM_TYPE,
    ROLE_LINE_EDIT,
    ROLE_MIME_DATA,
    ROLE_NAME_LABEL,
    ROLE_OLD_NAME,
    ROLE_PLACEHOLDER,
)
from ui.collections.tree.draggable_tree_widget import DraggableTreeWidget

__all__ = [
    "EMPTY_COLLECTION_HTML",
    "ICON_CACHE",
    "PLACEHOLDER_MARKER",
    "ROLE_ITEM_ID",
    "ROLE_ITEM_TYPE",
    "ROLE_LINE_EDIT",
    "ROLE_MIME_DATA",
    "ROLE_NAME_LABEL",
    "ROLE_OLD_NAME",
    "ROLE_PLACEHOLDER",
    "CollectionTree",
    "DraggableTreeWidget",
]
