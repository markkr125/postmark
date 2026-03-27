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
