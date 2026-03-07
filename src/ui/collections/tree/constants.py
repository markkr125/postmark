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
ROLE_ITEM_TYPE = Qt.ItemDataRole.UserRole + 1  # column 1 - "folder" or "request"
ROLE_OLD_NAME = Qt.ItemDataRole.UserRole + 2  # column 1 - original name (rename rollback)
ROLE_LINE_EDIT = Qt.ItemDataRole.UserRole + 3  # column 1 - QLineEdit ref during rename
ROLE_NAME_LABEL = Qt.ItemDataRole.UserRole + 4  # column 1 - QLabel ref during rename
ROLE_MIME_DATA = Qt.ItemDataRole.UserRole + 5  # column 3 - drag/drop QMimeData
ROLE_METHOD = Qt.ItemDataRole.UserRole + 6  # column 0 - HTTP method for requests
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
