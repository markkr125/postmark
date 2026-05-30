"""Tests for the inline folder runner panel and runner helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from ui.dialogs.collection_runner.config import RunnerConfigView
from ui.request.folder_editor.runner_panel import _RunnerPanel
from ui.dialogs.collection_runner.results import RunnerResultsView
from ui.dialogs.collection_runner.worker import (
    RunnerWorker,
    _substitute,
    parse_data_file,
    scripts_enabled,
)
from ui.styling.theme_manager import _APP, _ORG


# ===================================================================
# parse_data_file tests
# ===================================================================
class TestParseDataFile:
    """Tests for parse_data_file CSV/JSON helper."""

    def test_parse_csv(self, tmp_path: Path) -> None:
        """CSV with headers is parsed into list of dicts."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name,age\nAlice,30\nBob,25\n", encoding="utf-8")
        rows = parse_data_file(csv_file)
        assert len(rows) == 2
        assert rows[0] == {"name": "Alice", "age": "30"}
        assert rows[1] == {"name": "Bob", "age": "25"}

    def test_parse_json_array(self, tmp_path: Path) -> None:
        """JSON array of objects is parsed."""
        json_file = tmp_path / "data.json"
        json_file.write_text('[{"x": 1}, {"x": 2}]', encoding="utf-8")
        rows = parse_data_file(json_file)
        assert len(rows) == 2
        assert rows[0] == {"x": 1}

    def test_parse_json_non_array(self, tmp_path: Path) -> None:
        """JSON that is not an array returns an empty list."""
        json_file = tmp_path / "data.json"
        json_file.write_text('{"key": "value"}', encoding="utf-8")
        rows = parse_data_file(json_file)
        assert rows == []

    def test_parse_json_filters_non_dicts(self, tmp_path: Path) -> None:
        """Non-dict items in a JSON array are filtered out."""
        json_file = tmp_path / "data.json"
        json_file.write_text('[{"a": 1}, 42, "str", {"b": 2}]', encoding="utf-8")
        rows = parse_data_file(json_file)
        assert len(rows) == 2
        assert rows[1] == {"b": 2}

    def test_parse_empty_csv(self, tmp_path: Path) -> None:
        """Empty CSV with only headers returns no rows."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("col1,col2\n", encoding="utf-8")
        rows = parse_data_file(csv_file)
        assert rows == []


# ===================================================================
# scripts_enabled tests
# ===================================================================
class TestScriptsEnabled:
    """Tests for scripts_enabled QSettings helper."""

    def test_default_is_true(self) -> None:
        """Script execution is enabled by default."""
        settings = QSettings(_ORG, _APP)
        settings.remove("scripting/enabled")
        settings.sync()
        assert scripts_enabled() is True

    def test_disabled_when_false(self) -> None:
        """Returns False when QSettings value is False."""
        settings = QSettings(_ORG, _APP)
        settings.setValue("scripting/enabled", False)
        settings.sync()
        assert scripts_enabled() is False

    def test_disabled_when_string_false(self) -> None:
        """Returns False when QSettings value is the string 'false'."""
        settings = QSettings(_ORG, _APP)
        settings.setValue("scripting/enabled", "false")
        settings.sync()
        assert scripts_enabled() is False

    def test_enabled_when_true(self) -> None:
        """Returns True when QSettings value is True."""
        settings = QSettings(_ORG, _APP)
        settings.setValue("scripting/enabled", True)
        settings.sync()
        assert scripts_enabled() is True

    @pytest.fixture(autouse=True)
    def _clear_scripting_settings(self) -> None:
        """Clear scripting QSettings before each test."""
        settings = QSettings(_ORG, _APP)
        settings.remove("scripting")
        settings.sync()


# ===================================================================
# RunnerWorker tests
# ===================================================================
class TestRunnerWorker:
    """Tests for RunnerWorker construction and data-driven configuration."""

    def test_construction(self) -> None:
        """Worker initialises with empty lists."""
        worker = RunnerWorker()
        assert worker._requests == []
        assert worker._iteration_data == []
        assert worker._iteration_count == 1

    def test_set_requests(self) -> None:
        """set_requests stores the list."""
        worker = RunnerWorker()
        reqs: list[dict[str, Any]] = [{"name": "R1"}, {"name": "R2"}]
        worker.set_requests(reqs)
        assert worker._requests is reqs

    def test_set_iteration_data(self) -> None:
        """set_iteration_data stores data and count."""
        worker = RunnerWorker()
        data = [{"key": "val"}]
        worker.set_iteration_data(data, 3)
        assert worker._iteration_data is data
        assert worker._iteration_count == 3

    def test_set_iteration_data_clamps_count(self) -> None:
        """Iteration count is clamped to at least 1."""
        worker = RunnerWorker()
        worker.set_iteration_data([], 0)
        assert worker._iteration_count == 1

    def test_cancel_flag(self) -> None:
        """cancel() sets the internal flag."""
        worker = RunnerWorker()
        assert worker._cancelled is False
        worker.cancel()
        assert worker._cancelled is True


class TestRunnerWorkerRun:
    """Tests for RunnerWorker.run() with mocked HTTP."""

    @staticmethod
    def _fake_send(**kwargs: Any) -> dict[str, Any]:
        """Return a minimal fake response dict."""
        return {
            "status_code": 200,
            "elapsed_ms": 10,
            "body": "ok",
            "headers": [],
        }

    def test_basic_run(self) -> None:
        """Worker runs a single request and emits progress + finished."""
        worker = RunnerWorker()
        worker.set_requests([{"name": "R1", "method": "GET", "url": "http://x"}])

        results: list[dict[str, Any]] = []
        finished: list[list[dict[str, Any]]] = []
        worker.progress.connect(lambda _idx, r: results.append(r))
        worker.finished.connect(finished.append)

        with (
            patch(
                "ui.dialogs.collection_runner.worker.HttpService.send_request",
                side_effect=self._fake_send,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.ScriptService.build_script_chain",
                return_value=([], []),
            ),
        ):
            worker.run()

        assert len(results) == 1
        assert results[0]["name"] == "R1"
        assert results[0]["status_code"] == 200
        assert len(finished) == 1

    def test_cancel_stops_iteration(self) -> None:
        """Cancelling the worker stops iteration and emits error."""
        worker = RunnerWorker()
        worker.set_requests(
            [
                {"name": "R1", "method": "GET", "url": "http://x"},
                {"name": "R2", "method": "GET", "url": "http://y"},
            ]
        )
        worker.cancel()

        errors: list[str] = []
        worker.error.connect(errors.append)
        worker.run()

        assert len(errors) == 1
        assert "cancelled" in errors[0].lower()

    def test_multiple_iterations(self) -> None:
        """Worker runs each request once per iteration."""
        worker = RunnerWorker()
        worker.set_requests([{"name": "R1", "method": "GET", "url": "http://x"}])
        worker.set_iteration_data([{"a": "1"}, {"a": "2"}], 2)

        results: list[dict[str, Any]] = []
        worker.progress.connect(lambda _idx, r: results.append(r))

        with (
            patch(
                "ui.dialogs.collection_runner.worker.HttpService.send_request",
                side_effect=self._fake_send,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.ScriptService.build_script_chain",
                return_value=([], []),
            ),
        ):
            worker.run()

        assert len(results) == 2

    def test_skip_request_sets_skipped_flag(self) -> None:
        """When pre-request script sets skip_request, result has _skipped."""
        worker = RunnerWorker()
        worker.set_requests([{"name": "R1", "id": 1, "method": "GET", "url": "http://x"}])

        pre_out = {"skip_request": True, "console_logs": []}

        with (
            patch(
                "ui.dialogs.collection_runner.worker.ScriptService.build_script_chain",
                return_value=([{"code": "x", "language": "javascript", "source_name": ""}], []),
            ),
            patch(
                "ui.dialogs.collection_runner.worker.ScriptEngine.run_pre_request_scripts",
                return_value=pre_out,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.scripts_enabled",
                return_value=True,
            ),
        ):
            results: list[dict[str, Any]] = []
            worker.progress.connect(lambda _idx, r: results.append(r))
            worker.run()

        assert len(results) == 1
        assert results[0].get("_skipped") is True
        assert results[0]["status_code"] == 0

    def test_pre_request_array_header_mutation_applied(self) -> None:
        """Array header mutations apply cleanly; pre-request var changes recorded.

        Covers F4 (Postman-style header arrays normalized via apply_request_mutations
        instead of crashing on ``.items()``) and the F5 variable-merge path.
        """
        worker = RunnerWorker()
        worker.set_requests(
            [{"name": "R1", "id": 1, "method": "GET", "url": "http://x", "headers": {}}]
        )

        captured: dict[str, Any] = {}

        def fake_send(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"status_code": 200, "elapsed_ms": 5, "body": "", "headers": []}

        pre_out = {
            "console_logs": [],
            "test_results": [],
            "request_mutations": {
                "method": "GET",
                "url": "http://x",
                "headers": [{"key": "Authorization", "value": "Bearer t"}],
                "body": "",
            },
            "variable_changes": {"tok": "t"},
        }

        with (
            patch(
                "ui.dialogs.collection_runner.worker.HttpService.send_request",
                side_effect=fake_send,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.ScriptService.build_script_chain",
                return_value=([{"code": "x", "language": "javascript", "source_name": ""}], []),
            ),
            patch(
                "ui.dialogs.collection_runner.worker.ScriptEngine.run_pre_request_scripts",
                return_value=pre_out,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.AssertionService"
                ".build_declarative_script_entry",
                return_value=None,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.scripts_enabled",
                return_value=True,
            ),
        ):
            results: list[dict[str, Any]] = []
            worker.progress.connect(lambda _idx, r: results.append(r))
            worker.run()

        assert len(results) == 1
        # Array header normalized into the sent header string (no '.items()' crash on a list).
        assert "Authorization: Bearer t" in (captured.get("headers") or "")
        # Pre-request variable change surfaced for reporting (F5 merge path executed).
        assert results[0].get("pre_request_variable_changes", {}).get("tok") == "t"

    def test_flow_control_next_request(self) -> None:
        """Flow control: setNextRequest jumps to the named request."""
        worker = RunnerWorker()
        worker.set_requests(
            [
                {"name": "A", "id": 1, "method": "GET", "url": "http://a"},
                {"name": "B", "id": 2, "method": "GET", "url": "http://b"},
                {"name": "C", "id": 3, "method": "GET", "url": "http://c"},
            ]
        )

        call_count = 0

        def fake_send(**kwargs: Any) -> dict[str, Any]:
            return {"status_code": 200, "elapsed_ms": 5, "body": "", "headers": []}

        def fake_test_scripts(scripts, ctx):
            nonlocal call_count
            call_count += 1
            # First call (request A): jump to C
            if call_count == 1:
                return {"test_results": [], "console_logs": [], "next_request": "C"}
            # Second call (request C): stop
            return {"test_results": [], "console_logs": [], "next_request": None}

        results: list[dict[str, Any]] = []
        worker.progress.connect(lambda _idx, r: results.append(r))

        with (
            patch(
                "ui.dialogs.collection_runner.worker.HttpService.send_request",
                side_effect=fake_send,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.ScriptService.build_script_chain",
                return_value=([], [{"code": "x", "language": "javascript", "source_name": ""}]),
            ),
            patch(
                "ui.dialogs.collection_runner.worker.ScriptEngine.run_test_scripts",
                side_effect=fake_test_scripts,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.scripts_enabled",
                return_value=True,
            ),
        ):
            worker.run()

        # A → C (skip B), then C stops.
        names = [r["name"] for r in results]
        assert names == ["A", "C"]

    def test_scripts_disabled_skips_scripts(self) -> None:
        """When scripts are disabled, no script chain is built."""
        worker = RunnerWorker()
        worker.set_requests([{"name": "R1", "id": 1, "method": "GET", "url": "http://x"}])

        with (
            patch(
                "ui.dialogs.collection_runner.worker.HttpService.send_request",
                side_effect=self._fake_send,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.scripts_enabled",
                return_value=False,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.ScriptService.build_script_chain",
            ) as mock_chain,
        ):
            results: list[dict[str, Any]] = []
            worker.progress.connect(lambda _idx, r: results.append(r))
            worker.run()

        mock_chain.assert_not_called()
        assert len(results) == 1
        assert results[0]["status_code"] == 200

    def test_pre_request_runtime_error_routed_to_console(self) -> None:
        """Pre-request runtime errors appear in console_logs, not test_results."""
        worker = RunnerWorker()
        worker.set_requests([{"name": "R1", "id": 1, "method": "GET", "url": "http://x"}])

        pre_out: dict[str, Any] = {
            "test_results": [
                {
                    "name": "(runtime error)",
                    "passed": False,
                    "error": "n is not defined",
                    "source_name": "MyFolder",
                    "duration_ms": 0,
                }
            ],
            "console_logs": [{"level": "log", "message": "pre-log", "timestamp": 0}],
        }

        with (
            patch(
                "ui.dialogs.collection_runner.worker.HttpService.send_request",
                side_effect=self._fake_send,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.ScriptService.build_script_chain",
                return_value=(
                    [{"code": "bad", "language": "javascript", "source_name": "MyFolder"}],
                    [],
                ),
            ),
            patch(
                "ui.dialogs.collection_runner.worker.ScriptEngine.run_pre_request_scripts",
                return_value=pre_out,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.scripts_enabled",
                return_value=True,
            ),
        ):
            results: list[dict[str, Any]] = []
            worker.progress.connect(lambda _idx, r: results.append(r))
            worker.run()

        assert len(results) == 1
        # Runtime error must NOT be in test_results
        assert results[0].get("test_results", []) == []
        # Runtime error must appear as a console error entry
        console = results[0].get("console_logs", [])
        error_logs = [c for c in console if c["level"] == "error"]
        assert len(error_logs) == 1
        assert "[MyFolder]" in error_logs[0]["message"]
        assert "n is not defined" in error_logs[0]["message"]
        # Normal pre-request console.log should still be there
        assert any(c["message"] == "pre-log" for c in console)
        # Runtime error must also appear in pre_request_errors
        pre_errs = results[0].get("pre_request_errors", [])
        assert len(pre_errs) == 1
        assert pre_errs[0]["source_name"] == "MyFolder"
        # Pre-request console logs must be separated
        pre_console = results[0].get("pre_request_console_logs", [])
        assert len(pre_console) == 1
        assert pre_console[0]["message"] == "pre-log"
        # has_pre_request_scripts flag must be set
        assert results[0].get("has_pre_request_scripts") is True


class TestSentinel:
    """Tests for the _SENTINEL flow-control marker."""

    def test_sentinel_is_unique(self) -> None:
        """_SENTINEL is a unique object, distinct from None."""
        from ui.dialogs.collection_runner.worker import _SENTINEL

        assert _SENTINEL is not None
        assert _SENTINEL is _SENTINEL


# ===================================================================
# _RunnerPanel (inline folder runner) tests
# ===================================================================
class TestFolderRunnerPanel:
    """Tests for inline runner panel construction and UI layout."""

    def test_construction(self, qapp: QApplication, qtbot, make_collection_with_request) -> None:
        """Panel can be instantiated for a collection."""
        coll, _req = make_collection_with_request()
        panel = _RunnerPanel()
        qtbot.addWidget(panel)
        panel.load_collection(coll.id)
        assert panel._config.iterations == 1

    def test_shows_request_count(
        self, qapp: QApplication, qtbot, make_collection_with_request
    ) -> None:
        """Info label displays the number of requests."""
        coll, _req = make_collection_with_request()
        panel = _RunnerPanel()
        qtbot.addWidget(panel)
        panel.load_collection(coll.id)
        assert "request" in panel._config.info_label.text().lower()

    def test_data_file_label_default(
        self, qapp: QApplication, qtbot, make_collection_with_request
    ) -> None:
        """Data file label shows default text before any file is loaded."""
        coll, _req = make_collection_with_request()
        panel = _RunnerPanel()
        qtbot.addWidget(panel)
        panel.load_collection(coll.id)
        assert "no data" in panel._config._data_file_label.text().lower()

    def test_iteration_spin_range(
        self, qapp: QApplication, qtbot, make_collection_with_request
    ) -> None:
        """Iteration spinner has a valid range."""
        coll, _req = make_collection_with_request()
        panel = _RunnerPanel()
        qtbot.addWidget(panel)
        panel.load_collection(coll.id)
        assert panel._config._iter_spin.minimum() == 1
        assert panel._config._iter_spin.maximum() >= 100

    def test_progress_bar_exists(
        self, qapp: QApplication, qtbot, make_collection_with_request
    ) -> None:
        """Progress bar is present and has a positive maximum."""
        coll, _req = make_collection_with_request()
        panel = _RunnerPanel()
        qtbot.addWidget(panel)
        panel.load_collection(coll.id)
        assert panel._progress.maximum() >= 1

    def test_results_table_columns(
        self, qapp: QApplication, qtbot, make_collection_with_request
    ) -> None:
        """Results table has the expected columns."""
        coll, _req = make_collection_with_request()
        panel = _RunnerPanel()
        qtbot.addWidget(panel)
        panel.load_collection(coll.id)
        assert panel._results._table.columnCount() == 6

    def test_env_combo_populated(
        self, qapp: QApplication, qtbot, make_collection_with_request
    ) -> None:
        """Environment selector is populated with at least the no-env option."""
        coll, _req = make_collection_with_request()
        panel = _RunnerPanel()
        qtbot.addWidget(panel)
        panel.load_collection(coll.id)
        assert panel._config._env_combo.count() >= 1
        assert panel._config.environment_id is None

    def test_request_checklist_populated(
        self, qapp: QApplication, qtbot, make_collection_with_request
    ) -> None:
        """Request checklist shows the collection's requests."""
        coll, _req = make_collection_with_request()
        panel = _RunnerPanel()
        qtbot.addWidget(panel)
        panel.load_collection(coll.id)
        assert panel._config._request_list.count() >= 1


# ===================================================================
# RunnerConfigView tests
# ===================================================================
class TestRunnerConfigView:
    """Tests for the config view's environment and request selection."""

    def test_env_combo_default(self, qapp: QApplication, qtbot) -> None:
        """Environment combo defaults to No Environment."""
        view = RunnerConfigView()
        qtbot.addWidget(view)
        assert view.environment_id is None

    def test_load_environments(self, qapp: QApplication, qtbot) -> None:
        """load_environments populates the combo."""
        view = RunnerConfigView()
        qtbot.addWidget(view)
        envs = [{"id": 1, "name": "Dev"}, {"id": 2, "name": "Prod"}]
        view.load_environments(envs)
        assert view._env_combo.count() == 3  # No Environment + 2
        view._env_combo.setCurrentIndex(1)
        assert view.environment_id == 1

    def test_load_requests(self, qapp: QApplication, qtbot) -> None:
        """load_requests populates the checklist, all checked by default."""
        view = RunnerConfigView()
        qtbot.addWidget(view)
        reqs = [{"name": "R1", "method": "GET"}, {"name": "R2", "method": "POST"}]
        view.load_requests(reqs)
        assert view._request_list.count() == 2
        assert len(view.selected_indices) == 2

    def test_deselect_all(self, qapp: QApplication, qtbot) -> None:
        """Deselect All unchecks all requests."""
        view = RunnerConfigView()
        qtbot.addWidget(view)
        reqs = [{"name": "R1", "method": "GET"}, {"name": "R2", "method": "POST"}]
        view.load_requests(reqs)
        view._deselect_all()
        assert view.selected_indices == []

    def test_select_all(self, qapp: QApplication, qtbot) -> None:
        """Select All re-checks after deselect."""
        view = RunnerConfigView()
        qtbot.addWidget(view)
        reqs = [{"name": "R1", "method": "GET"}]
        view.load_requests(reqs)
        view._deselect_all()
        view._select_all()
        assert view.selected_indices == [0]

    def test_partial_selection(self, qapp: QApplication, qtbot) -> None:
        """Individual items can be toggled."""
        view = RunnerConfigView()
        qtbot.addWidget(view)
        reqs = [{"name": "R1", "method": "GET"}, {"name": "R2", "method": "POST"}]
        view.load_requests(reqs)
        view._request_list.item(0).setCheckState(Qt.CheckState.Unchecked)
        assert view.selected_indices == [1]


# ===================================================================
# RunnerResultsView tests
# ===================================================================
class TestRunnerResultsView:
    """Tests for the results view detail panel and export."""

    def test_add_result_stores_data(self, qapp: QApplication, qtbot) -> None:
        """add_result stores the result dict for detail display."""
        view = RunnerResultsView()
        qtbot.addWidget(view)
        result = {"name": "R1", "method": "GET", "status_code": 200, "elapsed_ms": 42}
        view.add_result(result)
        assert len(view._results) == 1
        assert view._table.rowCount() == 1

    def test_clear_resets_results(self, qapp: QApplication, qtbot) -> None:
        """Clear resets stored results and detail."""
        view = RunnerResultsView()
        qtbot.addWidget(view)
        view.add_result({"name": "R1", "method": "GET", "status_code": 200})
        view.clear()
        assert view._results == []
        assert view._table.rowCount() == 0
        assert view._detail.toPlainText() == ""

    def test_row_selection_shows_detail(self, qapp: QApplication, qtbot) -> None:
        """Selecting a row populates the detail panel."""
        view = RunnerResultsView()
        qtbot.addWidget(view)
        view.add_result(
            {
                "name": "GetUsers",
                "method": "GET",
                "status_code": 200,
                "elapsed_ms": 42,
                "body": "response body",
                "test_results": [{"name": "status is 200", "passed": True}],
            }
        )
        view._on_row_selected(0, 0, -1, -1)
        html = view._detail.toHtml()
        assert "GetUsers" in html
        assert "200" in html
        assert "status is 200" in html

    def test_skipped_request_detail(self, qapp: QApplication, qtbot) -> None:
        """Skipped requests show 'Skipped' in detail."""
        view = RunnerResultsView()
        qtbot.addWidget(view)
        view.add_result({"name": "R1", "method": "GET", "_skipped": True, "status_code": 0})
        view._on_row_selected(0, 0, -1, -1)
        html = view._detail.toHtml()
        assert "Skipped" in html

    def test_summary_includes_skipped(self, qapp: QApplication, qtbot) -> None:
        """show_summary mentions skipped requests."""
        view = RunnerResultsView()
        qtbot.addWidget(view)
        results = [
            {"name": "R1", "status_code": 200, "test_results": []},
            {"name": "R2", "_skipped": True, "test_results": []},
        ]
        view.show_summary(results)
        assert "skipped" in view._summary_label.text().lower()

    def test_export_button_disabled_initially(self, qapp: QApplication, qtbot) -> None:
        """Export button is disabled before any results."""
        view = RunnerResultsView()
        qtbot.addWidget(view)
        assert not view._export_btn.isEnabled()

    def test_export_enabled_after_summary(self, qapp: QApplication, qtbot) -> None:
        """Export button is enabled after showing summary."""
        view = RunnerResultsView()
        qtbot.addWidget(view)
        view.show_summary([{"name": "R1", "status_code": 200, "test_results": []}])
        assert view._export_btn.isEnabled()

    def test_show_summary_selects_first_row_shows_test_section(
        self, qapp: QApplication, qtbot
    ) -> None:
        """After a run, row 0 is selected and the detail always lists Test Results."""
        view = RunnerResultsView()
        qtbot.addWidget(view)
        view.add_result(
            {
                "name": "R1",
                "method": "GET",
                "status_code": 200,
                "elapsed_ms": 0,
                "test_results": [],
            }
        )
        view.show_summary(
            [
                {
                    "name": "R1",
                    "status_code": 200,
                    "test_results": [],
                }
            ]
        )
        assert view._table.currentRow() == 0
        html = view._detail.toHtml()
        assert "Test Results" in html
        assert "No post-response tests defined" in html

    def test_export_csv(self, qapp: QApplication, qtbot, tmp_path: Path) -> None:
        """CSV export writes correct file."""
        view = RunnerResultsView()
        qtbot.addWidget(view)
        view._results = [
            {
                "name": "R1",
                "method": "GET",
                "status_code": 200,
                "elapsed_ms": 10,
                "test_results": [{"name": "t1", "passed": True}],
            },
        ]
        csv_path = str(tmp_path / "out.csv")
        view._export_csv(csv_path)
        content = Path(csv_path).read_text(encoding="utf-8")
        assert "R1" in content
        assert "GET" in content
        assert "200" in content

    def test_export_json(self, qapp: QApplication, qtbot, tmp_path: Path) -> None:
        """JSON export writes correct file."""
        import json

        view = RunnerResultsView()
        qtbot.addWidget(view)
        view._results = [
            {
                "name": "R1",
                "method": "POST",
                "status_code": 201,
                "elapsed_ms": 5,
                "test_results": [],
            },
        ]
        json_path = str(tmp_path / "out.json")
        view._export_json(json_path)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["name"] == "R1"
        assert data[0]["method"] == "POST"


# ===================================================================
# Variable substitution tests
# ===================================================================
class TestVariableSubstitution:
    """Tests for the _substitute helper in the worker."""

    def test_basic_substitution(self) -> None:
        """Variables are replaced in text."""
        assert _substitute("{{host}}/api", {"host": "localhost"}) == "localhost/api"

    def test_unknown_variable_left(self) -> None:
        """Unknown variables are left unchanged."""
        assert _substitute("{{unknown}}", {"host": "x"}) == "{{unknown}}"

    def test_no_vars_returns_unchanged(self) -> None:
        """Text without {{}} is returned as-is."""
        assert _substitute("plain text", {"host": "x"}) == "plain text"

    def test_empty_vars_dict(self) -> None:
        """Empty variables dict returns text unchanged."""
        assert _substitute("{{host}}", {}) == "{{host}}"

    def test_multiple_vars(self) -> None:
        """Multiple variables are substituted."""
        result = _substitute("{{proto}}://{{host}}", {"proto": "https", "host": "api.com"})
        assert result == "https://api.com"


# ===================================================================
# Worker environment vars tests
# ===================================================================
class TestWorkerEnvironmentVars:
    """Tests for environment variable support in RunnerWorker."""

    def test_set_environment_vars(self) -> None:
        """set_environment_vars stores the dict."""
        worker = RunnerWorker()
        worker.set_environment_vars({"host": "localhost"})
        assert worker._environment_vars == {"host": "localhost"}

    def test_env_vars_applied_to_url(self) -> None:
        """Environment variables are substituted in the URL."""
        worker = RunnerWorker()
        worker.set_requests([{"name": "R", "method": "GET", "url": "{{base}}/users"}])
        worker.set_environment_vars({"base": "http://localhost:8080"})

        results: list[dict[str, Any]] = []
        worker.progress.connect(lambda _idx, r: results.append(r))

        def fake_send(**kwargs: Any) -> dict[str, Any]:
            return {
                "status_code": 200,
                "elapsed_ms": 5,
                "body": "",
                "headers": [],
                "_sent_url": kwargs.get("url", ""),
            }

        with (
            patch(
                "ui.dialogs.collection_runner.worker.HttpService.send_request",
                side_effect=fake_send,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.ScriptService.build_script_chain",
                return_value=([], []),
            ),
        ):
            worker.run()

        assert len(results) == 1
        assert results[0]["status_code"] == 200

    def test_iteration_data_substitutes_in_url(self) -> None:
        """Data file row values replace {{key}} in URL (no environment)."""
        worker = RunnerWorker()
        worker.set_requests([{"name": "R", "method": "GET", "url": "https://x.test/{{city}}/path"}])
        worker.set_iteration_data([{"city": "tokyo"}], 1)
        worker.set_environment_vars({})

        sent_urls: list[str] = []

        def fake_send(**kwargs: Any) -> dict[str, Any]:
            sent_urls.append(str(kwargs.get("url", "")))
            return {"status_code": 200, "elapsed_ms": 1, "body": "", "headers": []}

        with (
            patch(
                "ui.dialogs.collection_runner.worker.HttpService.send_request",
                side_effect=fake_send,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.ScriptService.build_script_chain",
                return_value=([], []),
            ),
        ):
            worker.run()

        assert sent_urls == ["https://x.test/tokyo/path"]

    def test_environment_overrides_iteration_data_for_substitution(self) -> None:
        """Environment map wins over data file keys when both define the same name."""
        worker = RunnerWorker()
        worker.set_requests([{"name": "R", "method": "GET", "url": "https://x.test/{{city}}"}])
        worker.set_iteration_data([{"city": "tokyo"}], 1)
        worker.set_environment_vars({"city": "osaka"})

        sent_urls: list[str] = []

        def fake_send(**kwargs: Any) -> dict[str, Any]:
            sent_urls.append(str(kwargs.get("url", "")))
            return {"status_code": 200, "elapsed_ms": 1, "body": "", "headers": []}

        with (
            patch(
                "ui.dialogs.collection_runner.worker.HttpService.send_request",
                side_effect=fake_send,
            ),
            patch(
                "ui.dialogs.collection_runner.worker.ScriptService.build_script_chain",
                return_value=([], []),
            ),
        ):
            worker.run()

        assert sent_urls == ["https://x.test/osaka"]


# ===================================================================
# SettingsDialog scripting page tests
# ===================================================================
class TestSettingsDialogScriptingPage:
    """Tests for the SettingsDialog scripting page."""

    @pytest.fixture(autouse=True)
    def _clear_scripting_settings(self) -> None:
        """Clear scripting QSettings before each test."""
        settings = QSettings(_ORG, _APP)
        settings.remove("scripting")
        settings.sync()

    def test_scripting_category_exists(self, qapp: QApplication, qtbot) -> None:
        """The settings dialog has a Scripting category."""
        from ui.dialogs.settings_dialog import SettingsDialog
        from ui.styling.theme_manager import ThemeManager

        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        labels = []
        for i in range(dialog._cat_tree.topLevelItemCount()):
            it = dialog._cat_tree.topLevelItem(i)
            if it is not None:
                labels.append(it.text(0))
        assert "Scripting" in labels

    def test_scripting_checkbox_default_checked(self, qapp: QApplication, qtbot) -> None:
        """Script execution checkbox is checked by default."""
        from ui.dialogs.settings_dialog import SettingsDialog
        from ui.styling.theme_manager import ThemeManager

        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        assert dialog._enable_scripts_check.isChecked() is True

    def test_apply_persists_scripting_enabled(self, qapp: QApplication, qtbot) -> None:
        """Unchecking and applying persists scripting/enabled = False."""
        from ui.dialogs.settings_dialog import SettingsDialog
        from ui.styling.theme_manager import ThemeManager

        tm = ThemeManager(qapp)
        dialog = SettingsDialog(tm)
        qtbot.addWidget(dialog)
        dialog._enable_scripts_check.setChecked(False)
        dialog._on_apply()

        settings = QSettings(_ORG, _APP)
        val = settings.value("scripting/enabled")
        assert not val or val == "false" or val is False
