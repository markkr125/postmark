"""Tests for :class:`~ui.sidebar.snippets_sidebar_panel.SnippetsSidebarPanel`."""

from __future__ import annotations

import ui.widgets.snippets.loader as snippet_loader
from PySide6.QtWidgets import QLineEdit, QToolButton, QTreeWidget, QTreeWidgetItem

from services.snippet_service import SnippetService, UserSnippetDict
from ui.sidebar.snippets_sidebar_panel import SnippetsSidebarPanel
from ui.sidebar.snippets_tree_constants import KIND_CATEGORY, ROLE_NODE_KIND
from ui.sidebar.snippets_tree_delegate import SnippetsTreeDelegate


def _snippet_leaf_names(tree: QTreeWidget) -> list[str]:
    """Collect leaf snippet names from the tree."""
    names: list[str] = []
    for i in range(tree.topLevelItemCount()):
        lang = tree.topLevelItem(i)
        if lang is None:
            continue
        for c in range(lang.childCount()):
            cat = lang.child(c)
            if cat is None:
                continue
            for s in range(cat.childCount()):
                leaf = cat.child(s)
                if leaf is not None:
                    names.append(leaf.text(1) or leaf.text(0))
    return names


def _top_level_titles(tree: QTreeWidget) -> list[str]:
    """Language root labels in order."""
    titles: list[str] = []
    for i in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(i)
        if item is not None:
            titles.append(item.text(0))
    return titles


def _find_snippet_leaf(tree: QTreeWidget, name: str) -> QTreeWidgetItem | None:
    """Return the leaf item with display *name*, if present."""
    for leaf_name in _snippet_leaf_names(tree):
        if leaf_name != name:
            continue
        for i in range(tree.topLevelItemCount()):
            lang = tree.topLevelItem(i)
            if lang is None:
                continue
            for c in range(lang.childCount()):
                cat = lang.child(c)
                if cat is None:
                    continue
                for s in range(cat.childCount()):
                    item = cat.child(s)
                    if item is not None and (item.text(1) or item.text(0)) == name:
                        return item
    return None


def _find_category_item(tree: QTreeWidget, category: str) -> QTreeWidgetItem | None:
    """Return the category folder item named *category*, if present."""
    for i in range(tree.topLevelItemCount()):
        lang = tree.topLevelItem(i)
        if lang is None:
            continue
        for c in range(lang.childCount()):
            cat = lang.child(c)
            if (
                cat is not None
                and cat.data(0, ROLE_NODE_KIND) == KIND_CATEGORY
                and (cat.text(0) or "") == category
            ):
                return cat
    return None


class TestSnippetsSidebarPanel:
    """User snippet tree in the left flyout."""

    def test_header_has_info_and_search(self, qapp, qtbot) -> None:
        """Snippets section matches local scripts header controls."""
        panel = SnippetsSidebarPanel()
        qtbot.addWidget(panel)
        info_btn = panel.findChild(QToolButton, "sidebarSectionInfoButton")
        assert info_btn is not None
        assert panel._search.placeholderText() == "Search snippets"

    def test_tree_uses_snippets_delegate(self, qapp, qtbot) -> None:
        """Snippet leaves use the custom delegate (row height + trailing i)."""
        panel = SnippetsSidebarPanel()
        qtbot.addWidget(panel)
        assert isinstance(panel._tree.itemDelegate(), SnippetsTreeDelegate)

    def test_empty_state(self, qapp, qtbot) -> None:
        """Tree is empty and placeholder label is shown when there are no snippets."""
        panel = SnippetsSidebarPanel()
        qtbot.addWidget(panel)
        panel.show()
        qapp.processEvents()
        assert panel._tree.topLevelItemCount() == 0
        assert not panel._empty_label.isHidden()

    def test_refresh_builds_tree(self, qapp, qtbot) -> None:
        """Created snippets appear under language → category → leaf."""
        snippet_loader.load_snippets.cache_clear()
        try:
            SnippetService.create(
                name="TreeSnip",
                language="javascript",
                body="console.log('x');",
                category="My Cat",
            )
            panel = SnippetsSidebarPanel()
            qtbot.addWidget(panel)
            panel.show()
            panel.refresh()
            qapp.processEvents()
            assert panel._tree.topLevelItemCount() >= 1
            assert panel._empty_label.isHidden()
            assert "TreeSnip" in _snippet_leaf_names(panel._tree)
            lang = panel._tree.topLevelItem(0)
            assert lang is not None
            assert lang.text(0) == "JavaScript"
            assert lang.childCount() == 1
            assert lang.child(0).text(0) == "My Cat"
        finally:
            snippet_loader.load_snippets.cache_clear()

    def test_javascript_and_typescript_separate_roots(self, qapp, qtbot) -> None:
        """TypeScript snippets use ``ts`` storage and appear under their own root."""
        snippet_loader.load_snippets.cache_clear()
        try:
            SnippetService.create(
                name="JsOnly",
                language="javascript",
                body="// js",
            )
            SnippetService.create(
                name="TsOnly",
                language="typescript",
                body="// ts",
            )
            panel = SnippetsSidebarPanel()
            qtbot.addWidget(panel)
            panel.show()
            panel.refresh()
            qapp.processEvents()
            titles = _top_level_titles(panel._tree)
            assert "JavaScript" in titles
            assert "TypeScript" in titles
            assert titles.index("JavaScript") < titles.index("TypeScript")
            names = _snippet_leaf_names(panel._tree)
            assert names.count("JsOnly") == 1
            assert names.count("TsOnly") == 1
        finally:
            snippet_loader.load_snippets.cache_clear()

    def test_click_snippet_opens_edit(self, qapp, qtbot, monkeypatch) -> None:
        """Clicking a leaf invokes the edit dialog path."""
        snippet_loader.load_snippets.cache_clear()
        opened: list[int] = []

        def _fake_edit(self: SnippetsSidebarPanel, snip: UserSnippetDict) -> None:
            opened.append(int(snip["id"]))

        monkeypatch.setattr(SnippetsSidebarPanel, "_open_edit_dialog", _fake_edit)
        try:
            sid = SnippetService.create(
                name="ClickMe",
                language="python",
                body="print(1)",
            )
            panel = SnippetsSidebarPanel()
            qtbot.addWidget(panel)
            panel.show()
            panel.refresh()
            qapp.processEvents()
            leaf = _find_snippet_leaf(panel._tree, "ClickMe")
            assert leaf is not None
            panel._on_item_clicked(leaf, 0)
            assert opened == [sid]
        finally:
            snippet_loader.load_snippets.cache_clear()

    def test_context_edit_snippet(self, qapp, qtbot, monkeypatch) -> None:
        """Edit snippet opens the edit dialog for the leaf row."""
        snippet_loader.load_snippets.cache_clear()
        edited: list[int] = []

        def _fake_edit(self: SnippetsSidebarPanel, snippet_id: int) -> None:
            edited.append(snippet_id)

        monkeypatch.setattr(SnippetsSidebarPanel, "open_edit_snippet_by_id", _fake_edit)
        try:
            sid = SnippetService.create(
                name="EditCtx",
                language="javascript",
                body="// e",
            )
            panel = SnippetsSidebarPanel()
            qtbot.addWidget(panel)
            panel.show()
            panel.refresh()
            qapp.processEvents()
            leaf = _find_snippet_leaf(panel._tree, "EditCtx")
            assert leaf is not None
            panel._context_menus._menu_item = leaf
            panel._context_menus._on_edit_snippet()
            assert edited == [sid]
        finally:
            snippet_loader.load_snippets.cache_clear()

    def test_context_rename_snippet(self, qapp, qtbot) -> None:
        """Inline rename snippet updates the stored name."""
        snippet_loader.load_snippets.cache_clear()
        try:
            sid = SnippetService.create(
                name="OldSnip",
                language="javascript",
                body="// x",
            )
            panel = SnippetsSidebarPanel()
            qtbot.addWidget(panel)
            panel.show()
            panel.refresh()
            qapp.processEvents()
            leaf = _find_snippet_leaf(panel._tree, "OldSnip")
            assert leaf is not None
            panel._context_menus._menu_item = leaf
            panel._context_menus._on_rename_snippet()
            qapp.processEvents()
            edit = panel._tree.viewport().findChild(QLineEdit, "snippetTreeRenameEdit")
            assert edit is not None
            edit.setText("NewSnip")
            edit.returnPressed.emit()
            qapp.processEvents()
            row = next(r for r in SnippetService.list_all("javascript") if r["id"] == sid)
            assert row["name"] == "NewSnip"
        finally:
            snippet_loader.load_snippets.cache_clear()

    def test_context_rename_category(self, qapp, qtbot) -> None:
        """Inline rename category updates every snippet in that folder."""
        snippet_loader.load_snippets.cache_clear()
        try:
            SnippetService.create(
                name="InCat",
                language="python",
                body="1",
                category="Before",
            )
            panel = SnippetsSidebarPanel()
            qtbot.addWidget(panel)
            panel.show()
            panel.refresh()
            qapp.processEvents()
            cat_item = _find_category_item(panel._tree, "Before")
            assert cat_item is not None
            panel._context_menus._menu_item = cat_item
            panel._context_menus._on_rename_category()
            qapp.processEvents()
            edit = panel._tree.viewport().findChild(QLineEdit, "snippetTreeRenameEdit")
            assert edit is not None
            edit.setText("After")
            edit.returnPressed.emit()
            qapp.processEvents()
            rows = SnippetService.list_all("python")
            assert len(rows) == 1
            assert rows[0]["category"] == "After"
            panel.refresh()
            qapp.processEvents()
            assert _find_category_item(panel._tree, "After") is not None
            assert _find_category_item(panel._tree, "Before") is None
        finally:
            snippet_loader.load_snippets.cache_clear()

    def test_language_row_shows_snippet_count(self, qapp, qtbot) -> None:
        """Language roots store a snippet count for the delegate."""
        snippet_loader.load_snippets.cache_clear()
        try:
            from ui.sidebar.snippets_tree_constants import (
                KIND_LANGUAGE,
                ROLE_NODE_KIND,
                ROLE_SNIPPET_COUNT,
            )

            SnippetService.create(name="A", language="javascript", body="//")
            SnippetService.create(name="B", language="javascript", body="//")
            panel = SnippetsSidebarPanel()
            qtbot.addWidget(panel)
            panel.refresh()
            lang = panel._tree.topLevelItem(0)
            assert lang is not None
            assert lang.data(0, ROLE_NODE_KIND) == KIND_LANGUAGE
            assert lang.data(0, ROLE_SNIPPET_COUNT) == 2
        finally:
            snippet_loader.load_snippets.cache_clear()

    def test_context_remove_snippet(self, qapp, qtbot, monkeypatch) -> None:
        """Remove snippet from the leaf context menu deletes the row."""
        snippet_loader.load_snippets.cache_clear()
        try:
            sid = SnippetService.create(
                name="CtxDelete",
                language="javascript",
                body="// x",
                category="CtxCat",
            )
            panel = SnippetsSidebarPanel()
            qtbot.addWidget(panel)
            panel.show()
            panel.refresh()
            qapp.processEvents()
            leaf = _find_snippet_leaf(panel._tree, "CtxDelete")
            assert leaf is not None
            panel._context_menus._menu_item = leaf
            monkeypatch.setattr(
                "ui.sidebar.snippets_tree_context.QMessageBox.question",
                lambda *a, **k: __import__(
                    "PySide6.QtWidgets", fromlist=["QMessageBox"]
                ).QMessageBox.StandardButton.Yes,
            )
            panel._context_menus._on_remove_snippet()
            qapp.processEvents()
            assert "CtxDelete" not in _snippet_leaf_names(panel._tree)
            assert not any(r["id"] == sid for r in SnippetService.list_all("javascript"))
        finally:
            snippet_loader.load_snippets.cache_clear()

    def test_context_remove_category(self, qapp, qtbot, monkeypatch) -> None:
        """Remove category deletes every snippet in that folder."""
        snippet_loader.load_snippets.cache_clear()
        try:
            SnippetService.create(
                name="CatA1",
                language="python",
                body="1",
                category="DropCat",
            )
            SnippetService.create(
                name="CatA2",
                language="python",
                body="2",
                category="DropCat",
            )
            panel = SnippetsSidebarPanel()
            qtbot.addWidget(panel)
            panel.show()
            panel.refresh()
            qapp.processEvents()
            cat_item = _find_category_item(panel._tree, "DropCat")
            assert cat_item is not None
            panel._context_menus._menu_item = cat_item
            monkeypatch.setattr(
                "ui.sidebar.snippets_tree_context.QMessageBox.question",
                lambda *a, **k: __import__(
                    "PySide6.QtWidgets", fromlist=["QMessageBox"]
                ).QMessageBox.StandardButton.Yes,
            )
            panel._context_menus._on_remove_category()
            qapp.processEvents()
            assert _snippet_leaf_names(panel._tree) == []
        finally:
            snippet_loader.load_snippets.cache_clear()

    def test_context_add_snippet_opens_create(self, qapp, qtbot, monkeypatch) -> None:
        """Add new snippet on a category opens create dialog with that category."""
        snippet_loader.load_snippets.cache_clear()
        opened: list[tuple[str, str]] = []

        def _fake_open(self: SnippetsSidebarPanel, *, language: str, category: str = "") -> None:
            opened.append((language, category))

        monkeypatch.setattr(SnippetsSidebarPanel, "open_create_snippet_dialog", _fake_open)
        try:
            SnippetService.create(
                name="Seed",
                language="typescript",
                body="// t",
                category="My TS cat",
            )
            panel = SnippetsSidebarPanel()
            qtbot.addWidget(panel)
            panel.show()
            panel.refresh()
            qapp.processEvents()
            cat_item = panel._tree.topLevelItem(0)
            assert cat_item is not None
            cat_item = cat_item.child(0)
            assert cat_item is not None
            panel._context_menus._menu_item = cat_item
            panel._context_menus._on_add_snippet()
            assert opened == [("typescript", "My TS cat")]
        finally:
            snippet_loader.load_snippets.cache_clear()
