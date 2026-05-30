"""Data roles and node kinds for the snippets sidebar tree."""

from __future__ import annotations

from PySide6.QtCore import Qt

ROLE_SNIPPET_ID = Qt.ItemDataRole.UserRole
ROLE_NODE_KIND = Qt.ItemDataRole.UserRole + 1
ROLE_LANG_KEY = Qt.ItemDataRole.UserRole + 2
ROLE_SNIPPET_CATEGORY = Qt.ItemDataRole.UserRole + 3
ROLE_SNIPPET_CONTEXT = Qt.ItemDataRole.UserRole + 4
ROLE_SNIPPET_BODY = Qt.ItemDataRole.UserRole + 5
ROLE_SNIPPET_COUNT = Qt.ItemDataRole.UserRole + 6
ROLE_OLD_NAME = Qt.ItemDataRole.UserRole + 7

KIND_LANGUAGE = "language"
KIND_CATEGORY = "category"
KIND_SNIPPET = "snippet"
