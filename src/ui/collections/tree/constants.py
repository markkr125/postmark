"""Shared data roles and constants used by tree widget modules.

All custom ``Qt.ItemDataRole`` values and marker constants live here so they
can be imported by ``DraggableTreeWidget``, ``CollectionTree``, and test
code without circular dependencies.
"""

from __future__ import annotations

from PySide6.QtCore import Qt

from ui.styling.theme import COLOR_ACCENT

# ----------------------------------------------------------------------
# Data roles stored on QTreeWidgetItems
# ----------------------------------------------------------------------
ROLE_ITEM_ID = Qt.ItemDataRole.UserRole  # column 0 - database PK
ROLE_ITEM_TYPE = Qt.ItemDataRole.UserRole + 1  # column 1 - "folder", "request", or "script"
ITEM_TYPE_FOLDER = "folder"
ITEM_TYPE_REQUEST = "request"
ITEM_TYPE_SCRIPT = "script"
LEAF_ITEM_TYPES = frozenset({ITEM_TYPE_REQUEST, ITEM_TYPE_SCRIPT})
ROLE_OLD_NAME = Qt.ItemDataRole.UserRole + 2  # column 1 - original name (rename rollback)
ROLE_LINE_EDIT = Qt.ItemDataRole.UserRole + 3  # column 1 - QLineEdit ref during rename
ROLE_NAME_LABEL = Qt.ItemDataRole.UserRole + 4  # column 1 - QLabel ref during rename
ROLE_MIME_DATA = Qt.ItemDataRole.UserRole + 5  # column 3 - drag/drop QMimeData
ROLE_METHOD = Qt.ItemDataRole.UserRole + 6  # column 0 - HTTP method for requests
ROLE_LANGUAGE = Qt.ItemDataRole.UserRole + 7  # column 0 - script language code
ROLE_OLD_LANGUAGE = Qt.ItemDataRole.UserRole + 8  # column 1 - language before rename
ROLE_MODULE_FORMAT = Qt.ItemDataRole.UserRole + 9  # column 0 - esm | commonjs
ROLE_OLD_MODULE_FORMAT = Qt.ItemDataRole.UserRole + 11  # column 1 - format before rename
ROLE_PLACEHOLDER = Qt.ItemDataRole.UserRole + 10  # column 1 - "placeholder" marker

# ----------------------------------------------------------------------
# Helper constants
# ----------------------------------------------------------------------
PLACEHOLDER_MARKER = "placeholder"

EMPTY_COLLECTION_HTML = (
    "This collection is empty.<br>"
    f'<a href="#" style="color: {COLOR_ACCENT};">Add a request</a>'
    " to start working."
)

EMPTY_SCRIPT_FOLDER_HTML = (
    "This folder is empty.<br>"
    f'<a href="#" style="color: {COLOR_ACCENT};">Add a script</a>'
    " to start working."
)


def is_leaf_item_type(item_type: str | None) -> bool:
    """Return whether *item_type* is a tree leaf (request or local script)."""
    return item_type in LEAF_ITEM_TYPES
