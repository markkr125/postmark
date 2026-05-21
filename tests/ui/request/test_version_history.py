"""Tests for the version history dialog and script version capture."""

from __future__ import annotations

from typing import Any

from services.script_version_service import ScriptVersionService
from ui.request.request_editor.scripts.version_history import (
    _SCREEN_FRACTION,
    VersionHistoryDialog,
    _DiffViewer,
    _format_timestamp,
    compute_fold_ranges,
)
from ui.request.request_editor.scripts.version_history.toolbar import (
    WS_IGNORE_ALL,
    WS_TRIM,
    _DiffToolbar,
)


class TestVersionHistoryDialog:
    """Tests for the VersionHistoryDialog."""

    def _make_dialog(
        self,
        *,
        request_id: int = 1,
        current_pre: str = "pre code",
        current_test: str = "test code",
        language: str = "javascript",
    ) -> VersionHistoryDialog:
        """Create a dialog with default parameters."""
        return VersionHistoryDialog(
            request_id=request_id,
            collection_id=None,
            current_pre=current_pre,
            current_test=current_test,
            language=language,
        )

    def test_dialog_creates_without_error(self, qapp: Any) -> None:
        """Dialog can be constructed with no version history."""
        dlg = self._make_dialog()
        assert dlg.windowTitle() == "Script Version History"
        dlg.close()

    def test_dialog_shows_versions(self, qapp: Any) -> None:
        """Saved versions appear in the list."""
        ScriptVersionService.capture(request_id=1, script_type="pre_request", content="v1")
        ScriptVersionService.capture(request_id=1, script_type="pre_request", content="v2")
        dlg = self._make_dialog()
        assert dlg._pre_list.count() == 2
        dlg.close()

    def test_restore_returns_content(self, qapp: Any) -> None:
        """Clicking restore stores the selected version's content."""
        ScriptVersionService.capture(request_id=1, script_type="pre_request", content="old_code")
        dlg = self._make_dialog()
        dlg._pre_list.setCurrentRow(0)
        dlg._on_restore()
        restored = dlg.restored_content()
        assert restored is not None
        assert restored == ("pre_request", "old_code")
        dlg.close()

    def test_restore_test_tab(self, qapp: Any) -> None:
        """Restoring from the test tab produces script_type='test'."""
        ScriptVersionService.capture(request_id=1, script_type="test", content="test_old")
        dlg = self._make_dialog()
        assert dlg._type_tabs is not None
        dlg._type_tabs.setCurrentIndex(1)
        dlg._test_list.setCurrentRow(0)
        dlg._on_restore()
        restored = dlg.restored_content()
        assert restored is not None
        assert restored[0] == "test"
        dlg.close()

    def test_dialog_default_size(self, qapp: Any) -> None:
        """Dialog opens at 80 % of screen dimensions."""
        from PySide6.QtGui import QGuiApplication

        dlg = self._make_dialog()
        screen = QGuiApplication.primaryScreen()
        assert screen is not None
        geo = screen.availableGeometry()
        expected_w = int(geo.width() * _SCREEN_FRACTION)
        expected_h = int(geo.height() * _SCREEN_FRACTION)
        assert dlg.width() == expected_w
        assert dlg.height() == expected_h
        dlg.close()

    def test_dialog_passes_language(self, qapp: Any) -> None:
        """Dialog passes language to diff viewers."""
        dlg = self._make_dialog(language="python")
        assert dlg._pre_viewer._language == "python"
        assert dlg._test_viewer._language == "python"
        dlg.close()

    def test_version_list_has_object_name(self, qapp: Any) -> None:
        """Version lists use the 'versionList' objectName for QSS targeting."""
        dlg = self._make_dialog()
        assert dlg._pre_list.objectName() == "versionList"
        assert dlg._test_list.objectName() == "versionList"
        dlg.close()

    def test_tabs_have_object_name(self, qapp: Any) -> None:
        """Tab widget uses 'versionTabs' objectName for QSS targeting."""
        dlg = self._make_dialog()
        assert dlg._type_tabs is not None
        assert dlg._type_tabs.objectName() == "versionTabs"
        dlg.close()

    def test_version_item_format(self, qapp: Any) -> None:
        """Saved version items show 'Change' label with date below."""
        ScriptVersionService.capture(
            request_id=1,
            script_type="pre_request",
            content="some_code",
        )
        dlg = self._make_dialog()
        item = dlg._pre_list.item(0)
        text = item.text()
        assert text.startswith("Change\n")
        # Second line is the date in DD/MM/YYYY, HH:MM format
        date_part = text.split("\n")[1]
        assert "/" in date_part
        assert "," in date_part
        dlg.close()

    def test_version_list_has_delegate(self, qapp: Any) -> None:
        """Version lists use a custom item delegate."""
        from ui.request.request_editor.scripts.version_history.delegate import _VersionItemDelegate

        dlg = self._make_dialog()
        assert isinstance(dlg._pre_list.itemDelegate(), _VersionItemDelegate)
        assert isinstance(dlg._test_list.itemDelegate(), _VersionItemDelegate)
        dlg.close()

    def test_auto_selects_first_version(self, qapp: Any) -> None:
        """First version is auto-selected when the dialog opens."""
        ScriptVersionService.capture(request_id=1, script_type="pre_request", content="v1")
        dlg = self._make_dialog()
        assert dlg._pre_list.currentRow() == 0
        dlg.close()

    def test_diff_editors_no_border(self, qapp: Any) -> None:
        """Diff editors suppress the default outer border."""
        viewer = _DiffViewer()
        assert "border: none" in viewer._left_editor.styleSheet()
        assert "border: none" in viewer._right_editor.styleSheet()
        # No extra borders on either editor
        for css in (viewer._left_editor.styleSheet(), viewer._right_editor.styleSheet()):
            assert "border-bottom" not in css
            assert "border-right" not in css
        # Column headers use objectName for QSS styling (no inline stylesheet)
        assert viewer._left_label.objectName() == "diffColumnHeader"
        assert viewer._right_label.objectName() == "diffColumnHeader"
        viewer.close()


class TestDiffViewer:
    """Tests for the side-by-side diff viewer."""

    def test_show_single(self, qapp: Any) -> None:
        """Show_single displays content full-width, hiding the right column."""
        viewer = _DiffViewer()
        viewer.show_single("hello world")
        assert viewer._left_editor.toPlainText() == "hello world"
        assert viewer._right_editor.toPlainText() == ""
        assert viewer._right_col.isHidden()
        viewer.close()

    def test_show_diff(self, qapp: Any) -> None:
        """Show_diff displays both versions side-by-side with right column visible."""
        viewer = _DiffViewer()
        viewer.show_diff("line1\nline2\n", "line1\nmodified\n")
        assert viewer._left_editor.toPlainText() == "line1\nline2\n"
        assert viewer._right_editor.toPlainText() == "line1\nmodified\n"
        assert not viewer._right_col.isHidden()
        viewer.close()

    def test_syntax_highlighting_language(self, qapp: Any) -> None:
        """Editors receive the configured syntax highlighting language."""
        viewer = _DiffViewer(language="python")
        assert viewer._left_editor._language == "python"
        assert viewer._right_editor._language == "python"
        viewer.close()

    def test_diff_selections_persist(self, qapp: Any) -> None:
        """Diff selections are stored via set_diff_selections."""
        viewer = _DiffViewer()
        viewer.show_diff("line1\nold\n", "line1\nnew\n")
        assert len(viewer._left_editor._diff_selections) > 0
        assert len(viewer._right_editor._diff_selections) > 0
        viewer.close()

    def test_inline_char_diff_selections(self, qapp: Any) -> None:
        """Character-level inline diffs appear for replaced lines."""
        viewer = _DiffViewer()
        viewer.show_diff("const x = 1;", "const x = 2;")
        # Line-level + inline char selections should exist
        left_sels = viewer._left_editor._diff_selections
        right_sels = viewer._right_editor._diff_selections
        # At least 1 line-level + 1 inline (the changed char)
        assert len(left_sels) >= 2
        assert len(right_sels) >= 2
        viewer.close()

    def test_gutter_stripe_colors(self, qapp: Any) -> None:
        """Diff gutter stripe colours are set for changed lines."""
        viewer = _DiffViewer()
        viewer.show_diff("same\nold\n", "same\nnew\n")
        assert 1 in viewer._left_editor._diff_line_colors
        assert 1 in viewer._right_editor._diff_line_colors
        viewer.close()

    def test_show_single_clears_diff(self, qapp: Any) -> None:
        """Show_single clears diff selections, gutter colours, and folds."""
        viewer = _DiffViewer()
        viewer.show_diff("old", "new")
        viewer.show_single("current")
        assert viewer._left_editor._diff_selections == []
        assert viewer._left_editor._diff_line_colors == {}
        assert viewer._left_editor._diff_fold_ranges == []
        assert viewer._right_editor._diff_fold_ranges == []
        assert viewer._right_col.isHidden()
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
        editor._ensure_scripts_editors()
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


class TestDiffToolbar:
    """Tests for _DiffToolbar widget."""

    def test_diff_count_label(self, qapp: Any) -> None:
        """set_diff_count updates the counter label text."""
        toolbar = _DiffToolbar()
        toolbar.set_diff_count(5)
        assert toolbar._counter_label.text() == "5 differences"
        toolbar.set_diff_count(1)
        assert toolbar._counter_label.text() == "1 difference"
        toolbar.close()

    def test_navigate_signals(self, qapp: Any) -> None:
        """Prev/next buttons emit navigation signals."""
        toolbar = _DiffToolbar()
        prev_emitted: list[bool] = []
        next_emitted: list[bool] = []
        toolbar.navigate_prev.connect(lambda: prev_emitted.append(True))
        toolbar.navigate_next.connect(lambda: next_emitted.append(True))
        toolbar._prev_btn.click()
        toolbar._next_btn.click()
        assert prev_emitted == [True]
        assert next_emitted == [True]
        toolbar.close()

    def test_copy_signal(self, qapp: Any) -> None:
        """Copy button emits copy_requested signal."""
        toolbar = _DiffToolbar()
        emitted: list[bool] = []
        toolbar.copy_requested.connect(lambda: emitted.append(True))
        toolbar._copy_btn.click()
        assert emitted == [True]
        toolbar.close()

    def test_whitespace_signal(self, qapp: Any) -> None:
        """Whitespace menu actions emit whitespace_changed signal."""
        toolbar = _DiffToolbar()
        modes: list[str] = []
        toolbar.whitespace_changed.connect(modes.append)
        toolbar._on_ws_changed(WS_TRIM)
        assert modes == [WS_TRIM]
        assert toolbar._ws_btn.text() == WS_TRIM
        toolbar.close()

    def test_search_signal(self, qapp: Any) -> None:
        """Typing in search emits search_changed signal."""
        toolbar = _DiffToolbar()
        terms: list[str] = []
        toolbar.search_changed.connect(terms.append)
        toolbar._search.setText("hello")
        assert terms == ["hello"]
        toolbar.close()


class TestDiffNavigation:
    """Tests for diff hunk navigation in _DiffViewer."""

    def test_navigate_next(self, qapp: Any) -> None:
        """Navigate next increments the current hunk index."""
        viewer = _DiffViewer()
        viewer.show_diff("a\nb\nc\n", "a\nx\ny\n")
        assert viewer._current_hunk_idx == 0
        viewer.navigate_next()
        assert viewer._current_hunk_idx >= 0
        viewer.close()

    def test_navigate_wraps(self, qapp: Any) -> None:
        """Navigation wraps around hunk indices."""
        viewer = _DiffViewer()
        viewer.show_diff("old", "new")
        assert len(viewer._diff_hunks) >= 1
        initial = viewer._current_hunk_idx
        for _ in range(len(viewer._diff_hunks) + 1):
            viewer.navigate_next()
        assert viewer._current_hunk_idx == (initial + 1) % len(viewer._diff_hunks)
        viewer.close()

    def test_navigate_empty(self, qapp: Any) -> None:
        """Navigation on identical content (no hunks) is a no-op."""
        viewer = _DiffViewer()
        viewer.show_diff("same", "same")
        assert viewer._diff_hunks == []
        viewer.navigate_next()
        assert viewer._current_hunk_idx == -1
        viewer.close()

    def test_diff_count_signal(self, qapp: Any) -> None:
        """show_diff emits diff_count_changed with the hunk count."""
        viewer = _DiffViewer()
        counts: list[int] = []
        viewer.diff_count_changed.connect(counts.append)
        viewer.show_diff("a\nb\n", "a\nx\n")
        assert counts == [1]
        viewer.close()

    def test_version_info_updates_column_header(self, qapp: Any) -> None:
        """set_version_info updates the left column header text."""
        viewer = _DiffViewer()
        viewer.set_version_info("Before 3h ago")
        assert viewer._left_label.text() == "Before 3h ago"
        viewer.close()


class TestComputeFoldRanges:
    """Tests for compute_fold_ranges helper."""

    def test_no_folds_for_small_equal(self) -> None:
        """Equal blocks smaller than 2*context produce no folds."""
        opcodes: list[tuple[str, int, int, int, int]] = [("equal", 0, 5, 0, 5)]
        result = compute_fold_ranges(opcodes, 5, 5, context=3)
        assert result == []

    def test_fold_for_large_equal(self) -> None:
        """Equal blocks larger than 2*context produce a fold range."""
        opcodes: list[tuple[str, int, int, int, int]] = [("equal", 0, 20, 0, 20)]
        result = compute_fold_ranges(opcodes, 20, 20, context=3)
        assert len(result) == 1
        assert result[0] == (3, 17, 3, 17)

    def test_no_folds_for_diff_only(self) -> None:
        """Replace/insert/delete blocks produce no folds."""
        opcodes: list[tuple[str, int, int, int, int]] = [("replace", 0, 5, 0, 5)]
        result = compute_fold_ranges(opcodes, 5, 5)
        assert result == []


class TestDiffFolding:
    """Tests for diff fold ranges applied by _DiffViewer."""

    def _make_long_diff(self) -> tuple[str, str]:
        """Create old/new texts with a large unchanged section."""
        common = [f"line{i}" for i in range(20)]
        old_lines = [*common, "old_change", *common]
        new_lines = [*common, "new_change", *common]
        return "\n".join(old_lines), "\n".join(new_lines)

    def test_folds_applied_on_show_diff(self, qapp: Any) -> None:
        """show_diff sets fold ranges on both editors."""
        viewer = _DiffViewer()
        old_text, new_text = self._make_long_diff()
        viewer.show_diff(old_text, new_text)
        assert len(viewer._left_editor._diff_fold_ranges) > 0
        assert len(viewer._right_editor._diff_fold_ranges) > 0
        viewer.close()

    def test_fold_toggle(self, qapp: Any) -> None:
        """Toggling a fold expands then re-collapses blocks."""
        viewer = _DiffViewer()
        old_text, new_text = self._make_long_diff()
        viewer.show_diff(old_text, new_text)
        assert 0 in viewer._left_editor._collapsed_diff_folds
        viewer._left_editor.toggle_diff_fold(0)
        assert 0 not in viewer._left_editor._collapsed_diff_folds
        viewer._left_editor.toggle_diff_fold(0)
        assert 0 in viewer._left_editor._collapsed_diff_folds
        viewer.close()

    def test_fold_sync(self, qapp: Any) -> None:
        """Toggling a fold on the left mirrors to the right."""
        viewer = _DiffViewer()
        old_text, new_text = self._make_long_diff()
        viewer.show_diff(old_text, new_text)
        assert 0 in viewer._left_editor._collapsed_diff_folds
        assert 0 in viewer._right_editor._collapsed_diff_folds
        viewer._left_editor.toggle_diff_fold(0)
        assert 0 not in viewer._left_editor._collapsed_diff_folds
        assert 0 not in viewer._right_editor._collapsed_diff_folds
        viewer.close()


class TestVersionSearch:
    """Tests for version list search filtering."""

    def test_search_filters_versions(self, qapp: Any) -> None:
        """Typing in search hides non-matching items."""
        ScriptVersionService.capture(
            request_id=1,
            script_type="pre_request",
            content="alpha_code",
        )
        ScriptVersionService.capture(
            request_id=1,
            script_type="pre_request",
            content="beta_code",
        )
        dlg = VersionHistoryDialog(
            request_id=1,
            collection_id=None,
            current_pre="current",
            current_test="",
            language="javascript",
        )
        VersionHistoryDialog._filter_list(dlg._pre_list, "alpha")
        visible = [
            dlg._pre_list.item(i)
            for i in range(dlg._pre_list.count())
            if not dlg._pre_list.item(i).isHidden()
        ]
        assert len(visible) == 1
        dlg.close()

    def test_search_clear_shows_all(self, qapp: Any) -> None:
        """Clearing search shows all items."""
        ScriptVersionService.capture(
            request_id=1,
            script_type="pre_request",
            content="aaa",
        )
        ScriptVersionService.capture(
            request_id=1,
            script_type="pre_request",
            content="bbb",
        )
        dlg = VersionHistoryDialog(
            request_id=1,
            collection_id=None,
            current_pre="current",
            current_test="",
            language="javascript",
        )
        VersionHistoryDialog._filter_list(dlg._pre_list, "aaa")
        VersionHistoryDialog._filter_list(dlg._pre_list, "")
        visible = [
            dlg._pre_list.item(i)
            for i in range(dlg._pre_list.count())
            if not dlg._pre_list.item(i).isHidden()
        ]
        assert len(visible) == 2
        dlg.close()


class TestWhitespace:
    """Tests for whitespace mode affecting diff results."""

    def test_trim_mode_ignores_trailing(self, qapp: Any) -> None:
        """Trim mode treats lines differing only in trailing space as equal."""
        viewer = _DiffViewer()
        viewer._ws_mode = WS_TRIM
        viewer.show_diff("hello  \n", "hello\n")
        assert viewer._diff_hunks == []
        viewer.close()

    def test_ignore_all_mode(self, qapp: Any) -> None:
        """Ignore-all mode treats lines differing only in spaces as equal."""
        viewer = _DiffViewer()
        viewer._ws_mode = WS_IGNORE_ALL
        viewer.show_diff("a b c\n", "abc\n")
        assert viewer._diff_hunks == []
        viewer.close()

    def test_default_mode_detects_whitespace_diff(self, qapp: Any) -> None:
        """Default mode detects whitespace differences."""
        viewer = _DiffViewer()
        viewer.show_diff("hello  \n", "hello\n")
        assert len(viewer._diff_hunks) > 0
        viewer.close()
