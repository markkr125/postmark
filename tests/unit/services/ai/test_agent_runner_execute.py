"""Tests for agent collection runner and data-driven iterations."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from services.ai.chat.execution.runner import run_agent_collection, run_agent_iterations
from services.ai.chat.mutation.auto_approve import CATALOG
from services.ai.chat.mutation.bridge import clear_mutation_events, drain_mutation_events
from services.ai.chat.tools.workspace_execute.tool import WorkspaceExecuteAction, _execute
from services.collection_service import CollectionService
from services.run_history_service import RunHistoryService


def _obs_ok(obs: object) -> bool:
    """Return True when an observation text reports success."""
    return "ok: true" in str(getattr(obs, "text", obs))


class TestAgentCollectionRunner:
    """execute:run_collection persistence + dispatch."""

    def setup_method(self) -> None:
        """Clear bridge queue before each case."""
        clear_mutation_events()

    def teardown_method(self) -> None:
        """Clear bridge queue after each case."""
        clear_mutation_events()

    def test_run_collection_persists_history(self) -> None:
        """Hydrated run writes RunHistory rows with source=agent."""
        coll = CollectionService.create_collection("AgentRun")
        CollectionService.create_request(
            int(coll.id),
            "GET",
            "https://example.com/a",
            "A",
        )
        CollectionService.create_request(
            int(coll.id),
            "GET",
            "https://example.com/b",
            "B",
        )

        fake_response = {
            "status_code": 200,
            "elapsed_ms": 12.0,
            "headers": [],
            "body": "ok",
            "test_results": [{"name": "t", "passed": True}],
        }

        with patch(
            "services.ai.chat.execution.runner.collection.run_shared_send",
            return_value={"ok": True, "response": fake_response},
        ):
            result = run_agent_collection(
                collection_id=int(coll.id),
                scripts_enabled=False,
            )
        assert result["ok"] is True
        run_id = int((result.get("ids") or {})["run_id"])
        runs = RunHistoryService.get_runs(int(coll.id))
        assert any(int(r["id"]) == run_id for r in runs)
        run = next(r for r in runs if int(r["id"]) == run_id)
        assert run.get("source") == "agent"
        results = RunHistoryService.get_run_results(run_id)
        assert len(results) == 2

    def test_execute_dispatch_run_collection(self) -> None:
        """Tool dispatch enqueues executed bridge event."""
        coll = CollectionService.create_collection("DispatchRun")
        CollectionService.create_request(
            int(coll.id),
            "GET",
            "https://example.com/x",
            "X",
        )
        with patch(
            "services.ai.chat.execution.runner.collection.run_shared_send",
            return_value={
                "ok": True,
                "response": {
                    "status_code": 204,
                    "elapsed_ms": 1.0,
                    "headers": [],
                    "body": "",
                    "test_results": [],
                },
            },
        ):
            obs = _execute(
                WorkspaceExecuteAction(
                    operation="run_collection",
                    collection_id=int(coll.id),
                    scripts_enabled=False,
                )
            )
        assert _obs_ok(obs)
        events = drain_mutation_events()
        executed = next(e for e in events if e.get("type") == "executed")
        assert executed["action"] == "run_collection"
        assert "collection_id" in (executed.get("ids") or {})
        assert "execute:run_collection" in CATALOG

    def test_run_collection_drain_reloads_runs(self) -> None:
        """Execute drain refreshes folder Runs table via load_runs."""
        from types import SimpleNamespace

        from ui.main_window.mutation_drain.execute_ui import apply_executed_event

        calls: list[list[object]] = []

        class _Folder:
            def load_runs(self, runs: list[object]) -> None:
                calls.append(list(runs))

        host = SimpleNamespace(
            _tabs={
                0: SimpleNamespace(
                    tab_type="folder",
                    collection_id=55,
                    folder_editor=_Folder(),
                )
            },
            _open_folder=lambda *_a, **_k: None,
        )
        apply_executed_event(
            host,
            {
                "type": "executed",
                "action": "run_collection",
                "ids": {"collection_id": 55, "run_id": 1},
                "payload": {"execution_id": "x", "summary": "done", "ok": True},
            },
        )
        assert len(calls) == 1


class TestAgentIterations:
    """execute:run_iterations with mocked ScriptEngine."""

    def setup_method(self) -> None:
        """Clear bridge queue before each case."""
        clear_mutation_events()

    def teardown_method(self) -> None:
        """Clear bridge queue after each case."""
        clear_mutation_events()

    def test_run_iterations_two_rows(self) -> None:
        """Two iteration rows produce two ScriptEngine runs with iteration_data."""
        coll = CollectionService.create_collection("IterColl")
        req = CollectionService.create_request(
            int(coll.id),
            "GET",
            "https://example.com",
            "IterReq",
            scripts={
                "test": "pm.test('ok', function () {});",
                "test_language": "javascript",
            },
        )
        calls: list[dict[str, Any]] = []

        def _fake_run_test_scripts(scripts: object, ctx: dict[str, Any]) -> dict[str, Any]:
            calls.append(dict(ctx))
            return {
                "test_results": [{"name": "ok", "passed": True}],
                "console_logs": [],
            }

        with (
            patch(
                "services.ai.chat.execution.runner.iterations.ScriptService.build_script_chain",
                return_value=([], [{"code": "x", "language": "javascript"}]),
            ),
            patch(
                "services.ai.chat.execution.runner.iterations.AssertionService"
                ".build_declarative_script_entry",
                return_value=None,
            ),
            patch(
                "services.ai.chat.execution.runner.iterations.ScriptEngine.run_test_scripts",
                side_effect=_fake_run_test_scripts,
            ),
        ):
            result = run_agent_iterations(
                request_id=int(req.id),
                iteration_data=[{"sku": "a"}, {"sku": "b"}],
            )
        assert result["ok"] is True
        assert len(calls) == 2
        assert calls[0].get("iteration_data") == {"sku": "a"}
        assert calls[1].get("iteration_data") == {"sku": "b"}
        assert calls[0]["info"]["iteration"] == 0
        assert calls[1]["info"]["iteration"] == 1

    def test_execute_dispatch_run_iterations(self) -> None:
        """Tool dispatch for run_iterations enqueues executed event."""
        coll = CollectionService.create_collection("IterDispatch")
        req = CollectionService.create_request(
            int(coll.id),
            "GET",
            "https://example.com",
            "R",
            scripts={"test": "// t", "test_language": "javascript"},
        )
        with patch(
            "services.ai.chat.execution.runner.run_agent_iterations",
            return_value={
                "ok": True,
                "summary": "Ran 2 iteration(s)",
                "ids": {"request_id": int(req.id)},
                "script_phase": "test",
                "test_results": [],
                "console_logs": [],
                "iterations": [{"iteration": 0}, {"iteration": 1}],
            },
        ):
            obs = _execute(
                WorkspaceExecuteAction(
                    operation="run_iterations",
                    request_id=int(req.id),
                    iteration_data=[{"x": 1}, {"x": 2}],
                )
            )
        assert _obs_ok(obs)
        events = drain_mutation_events()
        executed = next(e for e in events if e.get("type") == "executed")
        assert executed["action"] == "run_iterations"
        assert "execute:run_iterations" in CATALOG
