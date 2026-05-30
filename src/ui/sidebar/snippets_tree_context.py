"""Context menus for the snippets sidebar tree."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QInputDialog, QMenu, QMessageBox, QTreeWidget, QTreeWidgetItem

from services.snippet_service import SnippetService
from ui.sidebar.snippets_tree_constants import (
    KIND_CATEGORY,
    KIND_LANGUAGE,
    KIND_SNIPPET,
    ROLE_LANG_KEY,
    ROLE_NODE_KIND,
    ROLE_SNIPPET_CATEGORY,
    ROLE_SNIPPET_ID,
)

if TYPE_CHECKING:
    from ui.sidebar.snippets_sidebar_panel import SnippetsSidebarPanel


class SnippetsTreeContextMenus:
    """Right-click menus for language, category, and snippet tree nodes."""

    def __init__(self, panel: SnippetsSidebarPanel) -> None:
        """Store *panel* for refresh and dialog helpers."""
        self._panel = panel
        self._tree: QTreeWidget | None = None
        self._menu_item: QTreeWidgetItem | None = None

        self._language_menu = QMenu()
        self._language_menu.addAction("Add new category", self._on_add_category)

        self._category_menu = QMenu()
        self._category_menu.addAction("Add new snippet", self._on_add_snippet)
        self._category_menu.addAction("Rename category", self._on_rename_category)
        self._category_menu.addSeparator()
        self._category_menu.addAction("Remove category", self._on_remove_category)

        self._snippet_menu = QMenu()
        self._snippet_menu.addAction("Edit snippet", self._on_edit_snippet)
        self._snippet_menu.addAction("Rename snippet", self._on_rename_snippet)
        self._snippet_menu.addSeparator()
        self._snippet_menu.addAction("Remove snippet", self._on_remove_snippet)

    def attach(self, tree: QTreeWidget) -> None:
        """Wire *tree* to show menus on right-click."""
        self._tree = tree
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_context_menu)

    def _on_context_menu(self, pos: QPoint) -> None:
        """Show the menu for the item under *pos*."""
        if self._tree is None:
            return
        item = self._tree.itemAt(pos)
        if item is None:
            return
        self._menu_item = item
        self._tree.setCurrentItem(item)
        kind = item.data(0, ROLE_NODE_KIND)
        if kind == KIND_LANGUAGE:
            self._language_menu.exec(self._tree.mapToGlobal(pos))
        elif kind == KIND_CATEGORY:
            self._category_menu.exec(self._tree.mapToGlobal(pos))
        elif kind == KIND_SNIPPET:
            self._snippet_menu.exec(self._tree.mapToGlobal(pos))

    def _language_key(self, item: QTreeWidgetItem | None) -> str:
        """Editor language key from a language node or any descendant."""
        node: QTreeWidgetItem | None = item
        while node is not None:
            if node.data(0, ROLE_NODE_KIND) == KIND_LANGUAGE:
                key = node.data(0, ROLE_LANG_KEY)
                if isinstance(key, str) and key:
                    return key
            node = node.parent()
        return "javascript"

    def _category_name(self, item: QTreeWidgetItem | None) -> str:
        """Category label from a category node or its parent chain."""
        if item is None:
            return "My snippets"
        if item.data(0, ROLE_NODE_KIND) == KIND_CATEGORY:
            return str(item.text(1) or item.text(0) or "My snippets")
        cat = item.data(0, ROLE_SNIPPET_CATEGORY)
        if isinstance(cat, str) and cat:
            return cat
        parent = item.parent()
        if parent is not None and parent.data(0, ROLE_NODE_KIND) == KIND_CATEGORY:
            return str(parent.text(1) or parent.text(0) or "My snippets")
        return "My snippets"

    def _on_add_category(self) -> None:
        """Prompt for a category name and open create-snippet with that category."""
        item = self._menu_item
        if item is None:
            return
        lang = self._language_key(item)
        name, ok = QInputDialog.getText(
            self._panel,
            "New category",
            "Category name:",
        )
        if not ok:
            return
        category = name.strip()
        if not category:
            QMessageBox.warning(self._panel, "New category", "Enter a category name.")
            return
        self._panel.open_create_snippet_dialog(language=lang, category=category)

    def _on_add_snippet(self) -> None:
        """Open create-snippet under the right-clicked category."""
        item = self._menu_item
        if item is None:
            return
        self._panel.open_create_snippet_dialog(
            language=self._language_key(item),
            category=self._category_name(item),
        )

    def _on_remove_category(self) -> None:
        """Delete all snippets in the right-clicked category after confirmation."""
        item = self._menu_item
        if item is None:
            return
        lang = self._language_key(item)
        category = self._category_name(item)
        count = sum(
            1
            for row in SnippetService.list_all(lang)
            if (row.get("category") or "My snippets") == category
        )
        if count == 0:
            return
        noun = "snippet" if count == 1 else "snippets"
        reply = QMessageBox.question(
            self._panel,
            "Remove category",
            f"Delete category “{category}” and all {count} {noun} inside it?\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        SnippetService.delete_snippets_in_category(lang, category)
        self._panel.refresh_after_mutation()

    def _on_edit_snippet(self) -> None:
        """Open the edit dialog for the right-clicked snippet."""
        item = self._menu_item
        if item is None:
            return
        sid = item.data(0, ROLE_SNIPPET_ID)
        if isinstance(sid, int):
            self._panel.open_edit_snippet_by_id(sid)

    def _on_rename_snippet(self) -> None:
        """Start in-place rename for the right-clicked snippet."""
        item = self._menu_item
        if item is not None:
            self._panel._inline_rename.start_snippet(item)

    def _on_rename_category(self) -> None:
        """Start in-place rename for the right-clicked category folder."""
        item = self._menu_item
        if item is not None:
            self._panel._inline_rename.start_category(item)

    def _on_remove_snippet(self) -> None:
        """Delete the right-clicked snippet after confirmation."""
        item = self._menu_item
        if item is None:
            return
        sid = item.data(0, ROLE_SNIPPET_ID)
        if not isinstance(sid, int):
            return
        name = str(item.text(1) or item.text(0) or "snippet")
        reply = QMessageBox.question(
            self._panel,
            "Remove snippet",
            f"Delete snippet “{name}”?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        SnippetService.delete(sid)
        self._panel.refresh_after_mutation()
