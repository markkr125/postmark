"""Tests for the Test Results tab in ResponseViewerWidget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.request.response_viewer import ResponseViewerWidget


def _make_viewer(qtbot):
    """Create a viewer attached to *qtbot*."""
    viewer = ResponseViewerWidget()
    qtbot.addWidget(viewer)
    return viewer


class TestTestResultsTab:
    """Test the Test Results tab behaviour."""

    def test_tab_hidden_initially(self, qapp: QApplication, qtbot) -> None:
        viewer = _make_viewer(qtbot)
        assert not viewer._tabs.isTabVisible(viewer._test_tab_index)

    def test_load_results_shows_tab(self, qapp: QApplication, qtbot) -> None:
        viewer = _make_viewer(qtbot)
        results = [{"name": "check", "passed": True, "error": None, "duration_ms": 1.0}]
        viewer.load_test_results(results)
        assert viewer._tabs.isTabVisible(viewer._test_tab_index)

    def test_load_empty_results_hides_tab(self, qapp: QApplication, qtbot) -> None:
        viewer = _make_viewer(qtbot)
        viewer.load_test_results([{"name": "a", "passed": True}])
        assert viewer._tabs.isTabVisible(viewer._test_tab_index)
        viewer.load_test_results([])
        assert not viewer._tabs.isTabVisible(viewer._test_tab_index)

    def test_summary_all_passed(self, qapp: QApplication, qtbot) -> None:
        viewer = _make_viewer(qtbot)
        viewer.load_test_results(
            [
                {"name": "a", "passed": True},
                {"name": "b", "passed": True},
            ]
        )
        assert "2/2" in viewer._test_results_summary.text()

    def test_summary_some_failed(self, qapp: QApplication, qtbot) -> None:
        viewer = _make_viewer(qtbot)
        viewer.load_test_results(
            [
                {"name": "a", "passed": True},
                {"name": "b", "passed": False, "error": "expected 1 to equal 2"},
            ]
        )
        assert "1/2" in viewer._test_results_summary.text()

    def test_result_rows_created(self, qapp: QApplication, qtbot) -> None:
        viewer = _make_viewer(qtbot)
        viewer.load_test_results(
            [
                {"name": "first", "passed": True},
                {"name": "second", "passed": False, "error": "fail"},
                {"name": "third", "passed": True},
            ]
        )
        # Layout has 3 result rows + 1 stretch = 4 items.
        assert viewer._test_results_list.count() == 4

    def test_clear_resets_test_results(self, qapp: QApplication, qtbot) -> None:
        viewer = _make_viewer(qtbot)
        viewer.load_test_results([{"name": "a", "passed": True}])
        assert viewer._tabs.isTabVisible(viewer._test_tab_index)
        viewer.clear()
        assert not viewer._tabs.isTabVisible(viewer._test_tab_index)
        # Only the stretch remains.
        assert viewer._test_results_list.count() == 1

    def test_reload_replaces_old_rows(self, qapp: QApplication, qtbot) -> None:
        viewer = _make_viewer(qtbot)
        viewer.load_test_results([{"name": "old", "passed": True}])
        viewer.load_test_results(
            [
                {"name": "new1", "passed": True},
                {"name": "new2", "passed": False, "error": "err"},
            ]
        )
        assert viewer._test_results_list.count() == 3  # 2 rows + stretch
        assert "2" in viewer._test_results_summary.text()

    def test_runtime_error_shows_script_error_summary(self, qapp: QApplication, qtbot) -> None:
        """Runtime errors alone show 'Script error' instead of pass/fail count."""
        viewer = _make_viewer(qtbot)
        viewer.load_test_results(
            [
                {
                    "name": "(runtime error)",
                    "passed": False,
                    "error": "ReferenceError: n is not defined",
                    "source_name": "Hyperguest",
                }
            ]
        )
        summary = viewer._test_results_summary.text()
        assert "Script error" in summary
        assert "Hyperguest" in summary
        assert "/1" not in summary  # No misleading pass count

    def test_runtime_error_mixed_with_tests(self, qapp: QApplication, qtbot) -> None:
        """When runtime errors coexist with real tests, show pass/fail count."""
        viewer = _make_viewer(qtbot)
        viewer.load_test_results(
            [
                {"name": "(runtime error)", "passed": False, "error": "err"},
                {"name": "real test", "passed": True},
            ]
        )
        summary = viewer._test_results_summary.text()
        assert "1/2" in summary


class TestPreRequestTab:
    """Tests for the Pre-request tab in ResponseViewerWidget."""

    def test_tab_hidden_initially(self, qapp: QApplication, qtbot) -> None:
        """Pre-request tab is hidden by default."""
        viewer = _make_viewer(qtbot)
        assert not viewer._tabs.isTabVisible(viewer._pre_tab_index)

    def test_load_data_shows_tab(self, qapp: QApplication, qtbot) -> None:
        """Loading pre-request data makes the tab visible."""
        viewer = _make_viewer(qtbot)
        viewer.load_pre_request_data(
            console_logs=[{"level": "log", "message": "hello", "timestamp": 0}],
            variable_changes={},
            errors=[],
        )
        assert viewer._tabs.isTabVisible(viewer._pre_tab_index)

    def test_console_output_displayed(self, qapp: QApplication, qtbot) -> None:
        """Console log messages appear in the output area."""
        viewer = _make_viewer(qtbot)
        viewer.load_pre_request_data(
            console_logs=[
                {"level": "log", "message": "setup done", "timestamp": 0},
                {"level": "warn", "message": "low balance", "timestamp": 0},
            ],
            variable_changes={},
            errors=[],
        )
        text = viewer._pre_request_output.toHtml()
        assert "setup done" in text
        assert "low balance" in text

    def test_variable_changes_displayed(self, qapp: QApplication, qtbot) -> None:
        """Variable changes are shown in the variables label."""
        viewer = _make_viewer(qtbot)
        viewer.load_pre_request_data(
            console_logs=[],
            variable_changes={"token": "abc123", "host": "api.example.com"},
            errors=[],
        )
        assert not viewer._pre_request_vars_edit.isHidden()
        text = viewer._pre_request_vars_edit.toPlainText()
        assert "token" in text
        assert "abc123" in text
        assert "host" in text

    def test_no_variable_changes_hides_label(self, qapp: QApplication, qtbot) -> None:
        """Empty variable changes hides the variables label."""
        viewer = _make_viewer(qtbot)
        viewer.load_pre_request_data(
            console_logs=[{"level": "log", "message": "x", "timestamp": 0}],
            variable_changes={},
            errors=[],
        )
        assert viewer._pre_request_vars_edit.isHidden()

    def test_error_shows_red_tab_label(self, qapp: QApplication, qtbot) -> None:
        """Pre-request errors turn the tab label red."""
        viewer = _make_viewer(qtbot)
        viewer.load_pre_request_data(
            console_logs=[],
            variable_changes={},
            errors=[
                {"source_name": "MyFolder", "error": "n is not defined"},
            ],
        )
        bar = viewer._tabs.tabBar()
        tab_color = bar.tabTextColor(viewer._pre_tab_index)
        assert tab_color.isValid()
        # Red channel should dominate (COLOR_DANGER is red-ish).
        assert tab_color.red() > tab_color.green()

    def test_success_header(self, qapp: QApplication, qtbot) -> None:
        """Successful execution shows a green summary header."""
        viewer = _make_viewer(qtbot)
        viewer.load_pre_request_data(
            console_logs=[],
            variable_changes={},
            errors=[],
        )
        assert "executed" in viewer._pre_request_header.text().lower()

    def test_error_header(self, qapp: QApplication, qtbot) -> None:
        """Errors show the source and message in the header."""
        viewer = _make_viewer(qtbot)
        viewer.load_pre_request_data(
            console_logs=[],
            variable_changes={},
            errors=[
                {"source_name": "Hyperguest", "error": "n is not defined"},
            ],
        )
        text = viewer._pre_request_header.text()
        assert "Hyperguest" in text
        assert "n is not defined" in text

    def test_clear_hides_tab(self, qapp: QApplication, qtbot) -> None:
        """Clearing the viewer hides the Pre-request tab."""
        viewer = _make_viewer(qtbot)
        viewer.load_pre_request_data(
            console_logs=[{"level": "log", "message": "hi", "timestamp": 0}],
            variable_changes={},
            errors=[],
        )
        assert viewer._tabs.isTabVisible(viewer._pre_tab_index)
        viewer.clear()
        assert not viewer._tabs.isTabVisible(viewer._pre_tab_index)

    def test_clear_resets_tab_color(self, qapp: QApplication, qtbot) -> None:
        """Clearing the viewer resets the tab label colour."""
        viewer = _make_viewer(qtbot)
        viewer.load_pre_request_data(
            console_logs=[],
            variable_changes={},
            errors=[{"source_name": "X", "error": "err"}],
        )
        viewer.clear()
        assert not viewer._pre_request_has_error
