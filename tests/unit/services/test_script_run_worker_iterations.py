"""Tests for data-driven iteration support in :class:`ScriptRunWorker`."""

from __future__ import annotations

from unittest.mock import patch

from ui.request.request_editor.scripts.script_run_worker import (
    ScriptRunWorker,
    build_inline_context,
)


class TestScriptRunWorkerIterations:
    """Multi-iteration inline script runs."""

    def test_iteration_finished_emits_per_row(self) -> None:
        """Worker emits iteration_finished once per data row."""
        worker = ScriptRunWorker()
        ctx = build_inline_context(script_type="test")
        worker.set_params(
            script="pm.test('ok', () => pm.expect(true).to.be.true);",
            language="javascript",
            context=ctx,
        )
        worker.set_iteration_data([{"id": "1"}, {"id": "2"}], count=2)

        per_row: list[tuple[int, dict]] = []
        worker.iteration_finished.connect(
            lambda idx, out, _ms: per_row.append((idx, out)),
        )

        with patch(
            "ui.request.request_editor.scripts.script_run_worker.ScriptEngine.run_single",
            side_effect=[
                {"test_results": [{"name": "ok", "passed": True}], "console_logs": []},
                {"test_results": [{"name": "ok", "passed": False}], "console_logs": []},
            ],
        ):
            worker.run()

        assert [idx for idx, _ in per_row] == [0, 1]
        assert per_row[0][1]["test_results"][0]["passed"] is True
        assert per_row[1][1]["test_results"][0]["passed"] is False

    def test_finished_emits_list_when_iterating(self) -> None:
        """Terminal finished payload is a list of outputs for iteration runs."""
        worker = ScriptRunWorker()
        ctx = build_inline_context(script_type="pre_request")
        worker.set_params(script="console.log('x');", language="javascript", context=ctx)
        worker.set_iteration_data([{"a": "1"}], count=1)

        finished: list[tuple[object, float]] = []
        worker.finished.connect(lambda out, ms: finished.append((out, ms)))

        fake: dict[str, list[object]] = {"console_logs": [], "test_results": []}
        with patch(
            "ui.request.request_editor.scripts.script_run_worker.ScriptEngine.run_single",
            return_value=fake,
        ):
            worker.run()

        assert len(finished) == 1
        payload, _elapsed = finished[0]
        assert isinstance(payload, list)
        assert payload == [fake]

    def test_build_inline_context_passes_iteration_data(self) -> None:
        """build_inline_context forwards iteration metadata to ScriptInput."""
        ctx = build_inline_context(
            script_type="test",
            iteration=2,
            iteration_count=5,
            iteration_data={"user": "alice"},
        )
        assert ctx["info"]["iteration"] == 2
        assert ctx["info"]["iterationCount"] == 5
        assert ctx["iteration_data"] == {"user": "alice"}
