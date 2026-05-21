"""Tests for :class:`LocalScriptEditorWidget`."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from database.models.local_scripts.local_script_repository import create_folder, create_script
from services.local_script_service import LocalScriptService
from ui.local_scripts.local_script_editor_widget import LocalScriptEditorWidget


def test_autosave_persist_writes_script_content(qapp: QApplication) -> None:
    """Auto-save callback persists buffer text to the database."""
    folder = create_folder("Scripts")
    script = create_script(folder.id, "Helper", language="javascript", content="original")

    editor = LocalScriptEditorWidget()
    editor.load_script(LocalScriptService.get_script_load_dict(script.id) or {})
    editor._pane.editor.setPlainText("updated body")
    editor._persist_for_autosave()

    loaded = LocalScriptService.get_script_load_dict(script.id)
    assert loaded is not None
    assert loaded["content"] == "updated body"
    assert not editor.is_dirty()
