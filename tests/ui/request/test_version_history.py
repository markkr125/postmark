"""Tests for the version history dialog and script version capture."""

from __future__ import annotations

from typing import Any

from services.script_version_service import ScriptVersionService
from ui.request.request_editor.scripts.version_history import (
    VersionHistoryDialog,
    _DiffViewer,
    _format_timestamp,
)


class TestVersionHistoryDialog:
    """Tests for the VersionHistoryDialog."""

    def _make_dialog(
        self,
        *,
        request_id: int = 1,
        current_pre: str = "pre code",
        current_test: str = "test code",
    ) -> VersionHistoryDialog:
        """Create a dialog with default parameters."""
        return VersionHistoryDialog(
            request_id=request_id,
            collection_id=None,
            current_pre=current_pre,
            current_test=current_test,
        )

    def test_dialog_creates_without_error(self, qapp: Any) -> None:
        """Dialog can be constructed with no version history."""
        dlg = self._make_dialog()
        assert dlg.windowTitle() == "Script Version History"
        dlg.close()

    def test_dialog_shows_current_entry(self, qapp: Any) -> None:
        """Each list starts with a 'Current (unsaved)' pseudo-entry."""
        dlg = self._make_dialog()
        assert dlg._pre_list.count() >= 1
        assert "Current" in (dlg._pre_list.item(0).text() or "")
        dlg.close()

    def test_dialog_shows_versions(self, qapp: Any) -> None:
        """Saved versions appear in the list after the current entry."""
        ScriptVersionService.capture(request_id=1, script_type="pre_request", content="v1")
        ScriptVersionService.capture(request_id=1, script_type="pre_request", content="v2")
        dlg = self._make_dialog()
        # 1 current + 2 saved
        assert dlg._pre_list.count() == 3
        dlg.close()

    def test_restore_returns_content(self, qapp: Any) -> None:
        """Clicking restore stores the selected version's content."""
        ScriptVersionService.capture(request_id=1, script_type="pre_request", content="old_code")
        dlg = self._make_dialog()
        # Select the second item (the saved version).
        dlg._pre_list.setCurrentRow(1)
        dlg._on_restore()
        restored = dlg.restored_content()
        assert restored is not None
        assert restored == ("pre_request", "old_code")
        dlg.close()

    def test_restore_test_tab(self, qapp: Any) -> None:
        """Restoring from the test tab produces script_type='test'."""
        ScriptVersionService.capture(request_id=1, script_type="test", content="test_old")
        dlg = self._make_dialog()
        dlg._type_tabs.setCurrentIndex(1)
        dlg._test_list.setCurrentRow(1)
        dlg._on_restore()
        restored = dlg.restored_content()
        assert restored is not None
        assert restored[0] == "test"
        dlg.close()


class TestDiffViewer:
    """Tests for the side-by-side diff viewer."""

    def test_show_single(self, qapp: Any) -> None:
        """Show_single displays content in the left editor only."""
        viewer = _DiffViewer()
        viewer.show_single("hello world")
        assert viewer._left_editor.toPlainText() == "hello world"
        assert viewer._right_editor.toPlainText() == ""
        viewer.close()

    def test_show_diff(self, qapp: Any) -> None:
        """Show_diff displays both versions side-by-side."""
        viewer = _DiffViewer()
        viewer.show_diff("line1\nline2\n", "line1\nmodified\n")
        assert viewer._left_editor.toPlainText() == "line1\nline2\n"
        assert viewer._right_editor.toPlainText() == "line1\nmodified\n"
        viewer.close()


class TestFormatTimestamp:
    """Tests for _format_timestamp."""

    def test_recent(self) -> None:
        """Timestamps within the last minute show 'Just now'."""
        from datetime import datetime

        assert _format_timestamp(datetime.now()) == "Just now"

    def test_minutes_ago(self) -> None:
        """Timestamps show minutes ago within the last hour."""
        from datetime import datetime, timedelta

        ts = datetime.now() - timedelta(minutes=5)
        assert "5m ago" in _format_timestamp(ts)

    def test_hours_ago(self) -> None:
        """Timestamps show hours ago within the last day."""
        from datetime import datetime, timedelta

        ts = datetime.now() - timedelta(hours=3)
        assert "3h ago" in _format_timestamp(ts)

    def test_old_date(self) -> None:
        """Old timestamps show a date string."""
        from datetime import datetime, timedelta

        ts = datetime.now() - timedelta(days=30)
        result = _format_timestamp(ts)
        assert "-" in result  # YYYY-MM-DD format


class TestScriptsMixinVersionCapture:
    """Tests for version capture integration in the scripts mixin."""

    def _make_editor(self, qapp: Any) -> Any:
        """Create a RequestEditorWidget for testing scripts."""
        from ui.request.request_editor.editor_widget import RequestEditorWidget

        editor = RequestEditorWidget()
        return editor

    def test_capture_scripts_now(self, qapp: Any) -> None:
        """Capture_scripts_now saves versions immediately."""
        editor = self._make_editor(qapp)
        editor._request_id = 42
        editor._loading = False

        editor._pre_request_edit.setPlainText("console.log('test')")
        editor.capture_scripts_now()

        versions = ScriptVersionService.list_versions(request_id=42, script_type="pre_request")
        assert len(versions) == 1
        assert versions[0]["content"] == "console.log('test')"
        editor.close()

    def test_cross_session_undo(self, qapp: Any) -> None:
        """Cross-session undo restores previous version content."""
        # Pre-seed a version.
        ScriptVersionService.capture(request_id=43, script_type="pre_request", content="old code")

        editor = self._make_editor(qapp)
        editor._request_id = 43
        editor._pre_request_edit.setPlainText("new code")

        result = editor._script_cross_session_undo(editor._pre_request_edit, "pre_request")
        assert result is True
        assert editor._pre_request_edit.toPlainText() == "old code"
        editor.close()

    def test_cross_session_undo_no_history(self, qapp: Any) -> None:
        """Cross-session undo returns False when no history."""
        editor = self._make_editor(qapp)
        editor._request_id = 999
        editor._pre_request_edit.setPlainText("code")

        result = editor._script_cross_session_undo(editor._pre_request_edit, "pre_request")
        assert result is False
        editor.close()

    def test_history_button_exists(self, qapp: Any) -> None:
        """The history button is present in the scripts tab."""
        editor = self._make_editor(qapp)
        assert editor._history_btn is not None
        assert editor._history_btn.text() == "History"
        editor.close()
