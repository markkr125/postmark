"""Regression tests for local-scripts folder expand/rename display."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.collections.tree import ROLE_OLD_NAME, CollectionTree

from ..conftest import top_level_items


class TestLocalScriptsFolderExpand:
    """Expanding a folder must not corrupt its display name."""

    def test_expand_legacy_folder_name_stays_visible(self, qapp: QApplication, qtbot) -> None:
        """Legacy names with spaces are not replaced by ``Unnamed`` on expand."""
        tree = CollectionTree(tree_kind="local_scripts")
        qtbot.addWidget(tree)

        tree.set_collections(
            {
                "1": {
                    "id": 1,
                    "name": "New Folder",
                    "type": "folder",
                    "children": {
                        "2": {
                            "id": 2,
                            "name": "test",
                            "type": "script",
                            "language": "javascript",
                        },
                    },
                },
            }
        )

        folder = top_level_items(tree)[0]
        assert folder.text(0) == "New Folder"
        folder.setExpanded(True)
        tree._on_item_expanded(folder)
        assert folder.text(0) == "New Folder"

    def test_item_changed_without_rename_marker_is_ignored(self, qapp: QApplication, qtbot) -> None:
        """``itemChanged`` without ``ROLE_OLD_NAME`` does not rewrite the label."""
        tree = CollectionTree(tree_kind="local_scripts")
        qtbot.addWidget(tree)

        tree.set_collections(
            {
                "1": {
                    "id": 1,
                    "name": "my_pkg",
                    "type": "folder",
                    "children": {},
                },
            }
        )

        folder = top_level_items(tree)[0]
        folder.setText(0, "my_pkg")
        tree._on_item_changed(folder, 0)
        assert folder.text(0) == "my_pkg"
        assert folder.data(1, ROLE_OLD_NAME) is None

    def test_invalid_rename_reverts_to_stored_old_name(self, qapp: QApplication, qtbot) -> None:
        """Failed path-safe validation restores the name captured at rename start."""
        from PySide6.QtWidgets import QLineEdit

        tree = CollectionTree(tree_kind="local_scripts")
        qtbot.addWidget(tree)

        tree.set_collections(
            {
                "1": {
                    "id": 1,
                    "name": "my_pkg",
                    "type": "folder",
                    "children": {},
                },
            }
        )

        folder = top_level_items(tree)[0]
        tree._current_item = folder
        tree._rename_folder(1, folder)
        qapp.processEvents()
        edit = tree._tree.viewport().findChild(QLineEdit, "scriptTreeRenameEdit")
        assert edit is not None
        edit.setText("bad folder name")
        edit.returnPressed.emit()
        qapp.processEvents()
        assert folder.text(0) == "my_pkg"
