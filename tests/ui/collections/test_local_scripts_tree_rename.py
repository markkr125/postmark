"""Local scripts tree inline rename (display name with stem pre-selected)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLineEdit

from database.models.local_scripts.local_script_repository import create_folder, create_script
from ui.collections.collection_widget import CollectionWidget
from ui.collections.tree.constants import ITEM_TYPE_SCRIPT, ROLE_LANGUAGE
from ui.local_scripts.script_filename import script_display_name


def test_script_rename_overlay_shows_display_name_with_stem_selected(
    qapp: QApplication,
    qtbot,
) -> None:
    """Rename editor shows the full filename but selects only the basename stem."""
    folder = create_folder("Pkg")
    script = create_script(folder.id, "helper", language="typescript")

    widget = CollectionWidget(variant="local_scripts")
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    widget._tree_widget.set_collections(
        {
            str(folder.id): {
                "id": folder.id,
                "name": folder.name,
                "type": "folder",
                "children": {
                    str(script.id): {
                        "id": script.id,
                        "name": "helper",
                        "type": ITEM_TYPE_SCRIPT,
                        "language": "typescript",
                    }
                },
            }
        }
    )

    item = widget._tree_widget._find_item_by_id(
        widget._tree_widget._tree.invisibleRootItem(),
        script.id,
        ITEM_TYPE_SCRIPT,
    )
    assert item is not None
    widget._tree_widget._current_item = item
    widget._tree_widget._rename_script(script.id, item)

    viewport = widget._tree_widget._tree.viewport()
    line_edit = next(
        (c for c in viewport.children() if c.objectName() == "scriptTreeRenameEdit"),
        None,
    )
    assert isinstance(line_edit, QLineEdit)
    display = script_display_name("helper", "typescript")
    assert line_edit.text() == display
    assert line_edit.selectedText() == "helper"


def test_script_rename_commits_basename_and_language(qapp: QApplication, qtbot) -> None:
    """Finishing rename persists basename; extension change updates language."""
    folder = create_folder("Pkg")
    script = create_script(folder.id, "old", language="javascript")

    widget = CollectionWidget(variant="local_scripts")
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    widget._tree_widget.set_collections(
        {
            str(folder.id): {
                "id": folder.id,
                "name": folder.name,
                "type": "folder",
                "children": {
                    str(script.id): {
                        "id": script.id,
                        "name": "old",
                        "type": ITEM_TYPE_SCRIPT,
                        "language": "javascript",
                    }
                },
            }
        }
    )

    renamed: list[tuple[int, str, str, str]] = []

    def on_rename(script_id: int, basename: str, language: str, module_format: str) -> None:
        renamed.append((script_id, basename, language, module_format))

    widget._tree_widget.script_rename_requested.connect(on_rename)

    item = widget._tree_widget._find_item_by_id(
        widget._tree_widget._tree.invisibleRootItem(),
        script.id,
        ITEM_TYPE_SCRIPT,
    )
    assert item is not None
    widget._tree_widget._current_item = item
    widget._tree_widget._rename_script(script.id, item)

    viewport = widget._tree_widget._tree.viewport()
    line_edit = next(
        (c for c in viewport.children() if c.objectName() == "scriptTreeRenameEdit"),
        None,
    )
    assert isinstance(line_edit, QLineEdit)
    line_edit.setText("renamed.py")
    widget._tree_widget._finish_script_rename(item, line_edit, True)

    assert renamed == [(script.id, "renamed", "python", "esm")]
    assert item.text(1) == "renamed"
    assert item.data(0, ROLE_LANGUAGE) == "python"
