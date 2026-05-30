"""Tests for :class:`~ui.widgets.snippets.snippet_capture_dialog.SnippetCaptureDialog`."""

from __future__ import annotations

import ui.widgets.snippets.loader as snippet_loader
from services.snippet_service import SnippetService
from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.snippets.snippet_capture_dialog import SnippetCaptureDialog


def test_editor_create_persists_selection_body(qapp, qtbot) -> None:
    """Editor create mode stores the selection passed in ``body`` (no body field shown)."""
    snippet_loader.load_snippets.cache_clear()
    try:
        selection = "pm.globals.set('audit', true);"
        dlg = SnippetCaptureDialog(
            body=selection,
            language="javascript",
            script_type="test",
            parent=None,
        )
        qtbot.addWidget(dlg)
        assert dlg._body_edit is None
        assert dlg._body_fixed == selection
        dlg._name_edit.setText("EditorCreateMe")
        dlg._on_save()
        rows = SnippetService.list_all("javascript")
        match = next(r for r in rows if r["name"] == "EditorCreateMe")
        assert match["body"] == selection
        assert match["context"] == "test"
    finally:
        snippet_loader.load_snippets.cache_clear()


def test_sidebar_create_saves_stub_body(qapp, qtbot) -> None:
    """Sidebar create mode persists a non-empty stub body."""
    snippet_loader.load_snippets.cache_clear()
    try:
        dlg = SnippetCaptureDialog(from_sidebar=True, parent=None)
        qtbot.addWidget(dlg)
        assert isinstance(dlg._body_edit, CodeEditorWidget)
        dlg._name_edit.setText("FromSidebar")
        dlg._body_edit.setPlainText("// custom stub")
        dlg._on_save()
        rows = SnippetService.list_all("javascript")
        assert any(r["name"] == "FromSidebar" for r in rows)
        match = next(r for r in rows if r["name"] == "FromSidebar")
        assert "// custom stub" in match["body"]
    finally:
        snippet_loader.load_snippets.cache_clear()


def test_edit_mode_prefills_and_updates(qapp, qtbot) -> None:
    """Edit dialog loads row fields and update persists."""
    snippet_loader.load_snippets.cache_clear()
    try:
        sid = SnippetService.create(
            name="EditMe",
            language="python",
            body="print(1)",
            category="CatA",
            context="pre",
        )
        rows = SnippetService.list_all("python")
        row = next(r for r in rows if r["id"] == sid)
        dlg = SnippetCaptureDialog(snippet_id=sid, edit_row=row, parent=None)
        qtbot.addWidget(dlg)
        assert dlg._name_edit.text() == "EditMe"
        assert isinstance(dlg._body_edit, CodeEditorWidget)
        assert dlg._body_edit.language == "python"
        assert "print(1)" in dlg._body_edit.toPlainText()
        dlg._name_edit.setText("EditMeRenamed")
        dlg._body_edit.setPlainText("print(2)")
        dlg._on_save()
        updated = next(r for r in SnippetService.list_all("python") if r["id"] == sid)
        assert updated["name"] == "EditMeRenamed"
        assert "print(2)" in updated["body"]
    finally:
        snippet_loader.load_snippets.cache_clear()
