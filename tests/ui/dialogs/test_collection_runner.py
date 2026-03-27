"""Tests for the CollectionRunnerDialog and runner helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from ui.dialogs.collection_runner import (
    _SENTINEL,
    CollectionRunnerDialog,
    _parse_data_file,
    _RunnerWorker,
    _scripts_enabled,
)
from ui.styling.theme_manager import _APP, _ORG


# ===================================================================
# _parse_data_file tests
# ===================================================================
class TestParseDataFile:
    """Tests for _parse_data_file CSV/JSON helper."""

    def test_parse_csv(self, tmp_path: Path) -> None:
        """CSV with headers is parsed into list of dicts."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name,age\nAlice,30\nBob,25\n", encoding="utf-8")
        rows = _parse_data_file(csv_file)
        assert len(rows) == 2
        assert rows[0] == {"name": "Alice", "age": "30"}
        assert rows[1] == {"name": "Bob", "age": "25"}

    def test_parse_json_array(self, tmp_path: Path) -> None:
        """JSON array of objects is parsed."""
        json_file = tmp_path / "data.json"
        json_file.write_text('[{"x": 1}, {"x": 2}]', encoding="utf-8")
        rows = _parse_data_file(json_file)
        assert len(rows) == 2
        assert rows[0] == {"x": 1}

    def test_parse_json_non_array(self, tmp_path: Path) -> None:
        """JSON that is not an array returns an empty list."""
        json_file = tmp_path / "data.json"
        json_file.write_text('{"key": "value"}', encoding="utf-8")
        rows = _parse_data_file(json_file)
        assert rows == []

    def test_parse_json_filters_non_dicts(self, tmp_path: Path) -> None:
        """Non-dict items in a JSON array are filtered out."""
        json_file = tmp_path / "data.json"
        json_file.write_text('[{"a": 1}, 42, "str", {"b": 2}]', encoding="utf-8")
        rows = _parse_data_file(json_file)
        assert len(rows) == 2
        assert rows[1] == {"b": 2}

    def test_parse_empty_csv(self, tmp_path: Path) -> None:
        """Empty CSV with only headers returns no rows."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("col1,col2\n", encoding="utf-8")
        rows = _parse_data_file(csv_file)
        assert rows == []


# ===================================================================
# _scripts_enabled tests
# ===================================================================
class TestScriptsEnabled:
    """Tests for _scripts_enabled QSettings helper."""

    def test_default_is_true(self) -> None:
        """Script execution is enabled by default."""
        settings = QSettings(_ORG, _APP)
        settings.remove("scripting/enabled")
        settings.sync()
        assert _scripts_enabled() is True

    def test_disabled_when_false(self) -> None:
        """Returns False when QSettings value is False."""
        settings = QSettings(_ORG, _APP)
        settings.setValue("scripting/enabled", False)
        settings.sync()
        assert _scripts_enabled() is False

    def test_disabled_when_string_false(self) -> None:
        """Returns False when QSettings value is the string 'false'."""
        settings = QSettings(_ORG, _APP)
        settings.setValue("scripting/enabled", "false")
        settings.sync()
        assert _scripts_enabled() is False

    def test_enabled_when_true(self) -> None:
        """Returns True when QSettings value is True."""
        settings = QSettings(_ORG, _APP)
        settings.setValue("scripting/enabled", True)
        settings.sync()
        assert _scripts_enabled() is True

    @pytest.fixture(autouse=True)
    def _clear_scripting_settings(self) -> None:
        """Clear scripting QSettings before each test."""
        settings = QSettings(_ORG, _APP)
        settings.remove("scripting")
        settings.sync()


# ===================================================================
# _RunnerWorker tests
# ===================================================================
class TestRunnerWorker:
    """Tests for _RunnerWorker construction and data-driven configuration."""

    def test_construction(self) -> None:
        """Worker initialises with empty lists."""
        worker = _RunnerWorker()
        assert worker._requests == []
        assert worker._iteration_data == []
        assert worker._iteration_count == 1

    def test_set_requests(self) -> None:
        """set_requests stores the list."""
        worker = _RunnerWorker()
        reqs: list[dict[str, Any]] = [{"name": "R1"}, {"name": "R2"}]
        worker.set_requests(reqs)
        assert worker._requests is reqs

    def test_set_iteration_data(self) -> None:
        """set_iteration_data stores data and count."""
        worker = _RunnerWorker()
        data = [{"key": "val"}]
        worker.set_iteration_data(data, 3)
        assert worker._iteration_data is data
        assert worker._iteration_count == 3

    def test_set_iteration_data_clamps_count(self) -> None:
        """Iteration count is clamped to at least 1."""
        worker = _RunnerWorker()
        worker.set_iteration_data([], 0)
        assert worker._iteration_count == 1

    def test_cancel_flag(self) -> None:
        """cancel() sets the internal flag."""
        worker = _RunnerWorker()
        assert worker._cancelled is False
        worker.cancel()
        assert worker._cancelled is True


class TestRunnerWorkerRun:
    """Tests for _RunnerWorker.run() with mocked HTTP."""

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
        worker = _RunnerWorker()
        worker.set_requests([{"name": "R1", "method": "GET", "url": "http://x"}])

        results: list[dict[str, Any]] = []
        finished: list[list[dict[str, Any]]] = []
        worker.progress.connect(lambda _idx, r: results.append(r))
        worker.finished.connect(finished.append)

        with (
            patch(
                "ui.dialogs.collection_runner.HttpService.send_request",
                side_effect=self._fake_send,
            ),
            patch(
                "ui.dialogs.collection_runner.ScriptService.build_script_chain",
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
        worker = _RunnerWorker()
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
        worker = _RunnerWorker()
        worker.set_requests([{"name": "R1", "method": "GET", "url": "http://x"}])
        worker.set_iteration_data([{"a": "1"}, {"a": "2"}], 2)

        results: list[dict[str, Any]] = []
        worker.progress.connect(lambda _idx, r: results.append(r))

        with (
            patch(
                "ui.dialogs.collection_runner.HttpService.send_request",
                side_effect=self._fake_send,
            ),
            patch(
                "ui.dialogs.collection_runner.ScriptService.build_script_chain",
                return_value=([], []),
            ),
        ):
            worker.run()

        assert len(results) == 2

    def test_skip_request_sets_skipped_flag(self) -> None:
        """When pre-request script sets skip_request, result has _skipped."""
        worker = _RunnerWorker()
        worker.set_requests([{"name": "R1", "id": 1, "method": "GET", "url": "http://x"}])

        pre_out = {"skip_request": True, "console_logs": []}

        with (
            patch(
                "ui.dialogs.collection_runner.ScriptService.build_script_chain",
                return_value=([{"code": "x", "language": "javascript", "source_name": ""}], []),
            ),
            patch(
                "ui.dialogs.collection_runner.ScriptEngine.run_pre_request_scripts",
                return_value=pre_out,
            ),
            patch(
                "ui.dialogs.collection_runner._scripts_enabled",
                return_value=True,
            ),
        ):
            results: list[dict[str, Any]] = []
            worker.progress.connect(lambda _idx, r: results.append(r))
            worker.run()

        assert len(results) == 1
        assert results[0].get("_skipped") is True
        assert results[0]["status_code"] == 0

    def test_flow_control_next_request(self) -> None:
        """Flow control: setNextRequest jumps to the named request."""
        worker = _RunnerWorker()
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
                "ui.dialogs.collection_runner.HttpService.send_request",
                side_effect=fake_send,
            ),
            patch(
                "ui.dialogs.collection_runner.ScriptService.build_script_chain",
                return_value=([], [{"code": "x", "language": "javascript", "source_name": ""}]),
            ),
            patch(
                "ui.dialogs.collection_runner.ScriptEngine.run_test_scripts",
                side_effect=fake_test_scripts,
            ),
            patch(
                "ui.dialogs.collection_runner._scripts_enabled",
                return_value=True,
            ),
        ):
            worker.run()

        # A → C (skip B), then C stops.
        names = [r["name"] for r in results]
        assert names == ["A", "C"]

    def test_scripts_disabled_skips_scripts(self) -> None:
        """When scripts are disabled, no script chain is built."""
        worker = _RunnerWorker()
        worker.set_requests([{"name": "R1", "id": 1, "method": "GET", "url": "http://x"}])

        with (
            patch(
                "ui.dialogs.collection_runner.HttpService.send_request",
                side_effect=self._fake_send,
            ),
            patch(
                "ui.dialogs.collection_runner._scripts_enabled",
                return_value=False,
            ),
            patch(
                "ui.dialogs.collection_runner.ScriptService.build_script_chain",
            ) as mock_chain,
        ):
            results: list[dict[str, Any]] = []
            worker.progress.connect(lambda _idx, r: results.append(r))
            worker.run()

        mock_chain.assert_not_called()
        assert len(results) == 1
        assert results[0]["status_code"] == 200


# ===================================================================
# _SENTINEL tests
# ===================================================================
class TestSentinel:
    """Tests for the _SENTINEL flow-control marker."""

    def test_sentinel_is_unique(self) -> None:
        """_SENTINEL is a unique object, distinct from None."""
        assert _SENTINEL is not None
        assert _SENTINEL is _SENTINEL


# ===================================================================
# CollectionRunnerDialog tests
# ===================================================================
class TestCollectionRunnerDialog:
    """Tests for dialog construction and UI layout."""

    def test_construction(self, qapp: QApplication, qtbot, make_collection_with_request) -> None:
        """Dialog can be instantiated for a collection."""
        coll, _req = make_collection_with_request()
        dialog = CollectionRunnerDialog(coll.id)
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "Collection Runner"
        assert dialog._iter_spin.value() == 1

    def test_shows_request_count(
        self, qapp: QApplication, qtbot, make_collection_with_request
    ) -> None:
        """Info label displays the number of requests."""
        coll, _req = make_collection_with_request()
        dialog = CollectionRunnerDialog(coll.id)
        qtbot.addWidget(dialog)
        assert "request" in dialog._info_label.text().lower()

    def test_data_file_label_default(
        self, qapp: QApplication, qtbot, make_collection_with_request
    ) -> None:
        """Data file label shows default text before any file is loaded."""
        coll, _req = make_collection_with_request()
        dialog = CollectionRunnerDialog(coll.id)
        qtbot.addWidget(dialog)
        assert "no data" in dialog._data_file_label.text().lower()

    def test_iteration_spin_range(
        self, qapp: QApplication, qtbot, make_collection_with_request
    ) -> None:
        """Iteration spinner has a valid range."""
        coll, _req = make_collection_with_request()
        dialog = CollectionRunnerDialog(coll.id)
        qtbot.addWidget(dialog)
        assert dialog._iter_spin.minimum() == 1
        assert dialog._iter_spin.maximum() >= 100

    def test_progress_bar_exists(
        self, qapp: QApplication, qtbot, make_collection_with_request
    ) -> None:
        """Progress bar is present and has a positive maximum."""
        coll, _req = make_collection_with_request()
        dialog = CollectionRunnerDialog(coll.id)
        qtbot.addWidget(dialog)
        assert dialog._progress.maximum() >= 1

    def test_table_header_columns(
        self, qapp: QApplication, qtbot, make_collection_with_request
    ) -> None:
        """Results table has the expected columns."""
        coll, _req = make_collection_with_request()
        dialog = CollectionRunnerDialog(coll.id)
        qtbot.addWidget(dialog)
        assert dialog._table.columnCount() == 5


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
        labels = [dialog._cat_list.item(i).text() for i in range(dialog._cat_list.count())]
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
