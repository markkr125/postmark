"""Tests for get_request_data cancel_pending_persist flag."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QApplication

from ui.request.request_editor.editor_widget import RequestEditorWidget
from ui.request.request_editor.scripts.debug_metadata_persist import _DEBUG_PERSIST_MS


def test_snapshot_read_preserves_timer(
    qapp: QApplication,
    qtbot: Any,
    make_request_dict: Any,
) -> None:
    """Snapshot reads must not cancel a pending debug-metadata debounce."""
    editor = RequestEditorWidget()
    qtbot.addWidget(editor)
    editor.load_request(make_request_dict(), request_id=1)
    editor._scripts_editor_materialized = True
    editor._init_debug_metadata_persist()
    editor._schedule_debug_metadata_persist()
    assert editor._debug_metadata_timer.isActive()
    editor._scripts_editor_materialized = False
    editor.get_request_data(cancel_pending_persist=False)
    assert editor._debug_metadata_timer.isActive()
    editor.get_request_data()
    assert not editor._debug_metadata_timer.isActive()
    qtbot.wait(_DEBUG_PERSIST_MS + 50)
