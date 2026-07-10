"""Tests for RequestEditorWidget.focus_section."""

from __future__ import annotations

from ui.request.request_editor import RequestEditorWidget


def test_focus_section_selects_test_script_subtab(qapp, qtbot) -> None:
    """focus_section opens Scripts and selects the post-response sub-tab."""
    editor = RequestEditorWidget()
    qtbot.addWidget(editor)
    editor.show()
    editor.load_request(
        {"name": "Req", "method": "GET", "url": "http://example.com"},
        request_id=1,
    )
    editor.focus_section("test")
    assert editor._tabs.currentIndex() == 5
    assert editor._scripts_editor_materialized
    assert editor._scripts_sub_tabs.currentIndex() == 1
