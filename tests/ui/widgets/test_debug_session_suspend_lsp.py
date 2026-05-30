"""LSP and heavy editor work pause while a debug session is active."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.code_editor import editor_lsp_glue as lsp_glue
from ui.widgets.code_editor.lsp_integration import EditorLspAdapter


def test_suspend_skips_lsp_flush_until_resume(qapp: QApplication, qtbot) -> None:
    """``set_debug_session_active`` must defer ``didChange`` while suspended."""
    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    adapter = EditorLspAdapter(editor)
    editor._lsp_adapter = adapter
    adapter._opened = True
    adapter._language_id = "javascript"
    adapter._uri = "file:///buffer.js"

    flush_calls = 0

    def counting_flush() -> None:
        nonlocal flush_calls
        flush_calls += 1

    adapter._flush_did_change = counting_flush  # type: ignore[method-assign]

    lsp_glue.set_debug_session_active(editor, True)
    adapter._on_contents_changed()
    assert not adapter._sync_timer.isActive()
    assert flush_calls == 0
    assert adapter._sync_dirty

    lsp_glue.set_debug_session_active(editor, False)
    assert flush_calls == 1
    assert not adapter._sync_dirty


def test_resume_all_clears_stale_suspension(qapp: QApplication, qtbot) -> None:
    """``resume_all_debug_suspended_editors`` must resume even if host pin is gone."""
    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    adapter = EditorLspAdapter(editor)
    editor._lsp_adapter = adapter
    adapter._opened = True

    lsp_glue.set_debug_session_active(editor, True)
    assert editor._debug_session_active
    lsp_glue.resume_all_debug_suspended_editors()
    assert not editor._debug_session_active
    assert not adapter._sync_suspended
