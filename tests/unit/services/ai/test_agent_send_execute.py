"""Tests for agent send wrappers: history recording, scripts, execute dispatch."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from services.ai.chat.execution.agent_send import (
    run_agent_scripts,
    run_agent_send_request,
)
from services.ai.chat.tools.workspace_execute.tool import (
    WorkspaceExecuteAction,
    _execute,
)
from services.collection_service import CollectionService
from services.request_history_service import RequestHistoryService


class TestAgentSendHistory:
    """record_history=True persists via RequestHistoryService on success."""

    @patch("services.ai.chat.execution.send_core.HttpService.send_request")
    def test_record_history_on_success(
        self, mock_send: MagicMock, qapp: Any, tmp_path: Any, monkeypatch: Any
    ) -> None:
        """Successful agent send writes a history row when record_history is true."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        mock_send.return_value = {
            "status_code": 200,
            "status_text": "OK",
            "headers": [],
            "body": "ok",
            "elapsed_ms": 5.0,
            "size_bytes": 2,
            "request_url": "https://example.com/ping",
            "request_method": "GET",
        }
        col = CollectionService.create_collection("Hist")
        req = CollectionService.create_request(
            int(col.id),
            "GET",
            "https://example.com/ping",
            "Ping",
        )
        result = run_agent_send_request(
            request_id=int(req.id),
            record_history=True,
            include_scripts=False,
        )
        assert result["ok"] is True
        assert "history_recording_deferred" not in str(result.get("warnings") or [])
        rows = RequestHistoryService.list_for_request(int(req.id))
        assert len(rows) >= 1
        assert rows[0]["url"] == "https://example.com/ping"
        hist_id = (result.get("ids") or {}).get("history_entry_id")
        assert isinstance(hist_id, int)
        assert hist_id == rows[0]["id"]

    @patch("services.ai.chat.execution.send_core.HttpService.send_request")
    def test_record_history_false_skips(
        self, mock_send: MagicMock, qapp: Any, tmp_path: Any, monkeypatch: Any
    ) -> None:
        """record_history=False does not create history rows."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        mock_send.return_value = {
            "status_code": 200,
            "status_text": "OK",
            "headers": [],
            "body": "ok",
            "elapsed_ms": 1.0,
            "size_bytes": 2,
            "request_url": "https://example.com/x",
            "request_method": "GET",
        }
        col = CollectionService.create_collection("NoHist")
        req = CollectionService.create_request(
            int(col.id),
            "GET",
            "https://example.com/x",
            "X",
        )
        result = run_agent_send_request(
            request_id=int(req.id),
            record_history=False,
            include_scripts=False,
        )
        assert result["ok"] is True
        assert RequestHistoryService.list_for_request(int(req.id)) == []


class TestAgentScripts:
    """run_agent_scripts runs script chains without HTTP."""

    @patch("services.scripting.engine.ScriptEngine.run_test_scripts")
    @patch("services.scripting.engine.ScriptEngine.run_pre_request_scripts")
    def test_both_phases_mocked(
        self,
        mock_pre: MagicMock,
        mock_test: MagicMock,
    ) -> None:
        """phase=both invokes pre then test engines and returns test_results."""
        mock_pre.return_value = {
            "test_results": [],
            "console_logs": [],
            "variable_changes": {},
        }
        mock_test.return_value = {
            "test_results": [{"name": "status ok", "passed": True}],
            "console_logs": [],
            "variable_changes": {},
        }
        col = CollectionService.create_collection("Scripts")
        req = CollectionService.create_request(
            int(col.id),
            "GET",
            "https://example.com",
            "Scripted",
            scripts={
                "pre_request": "console.log('pre')",
                "test": "pm.test('status ok', function () {});",
            },
        )
        # ScriptService.build_script_chain needs proper scripts shape — patch chain.
        with patch(
            "services.script_service.ScriptService.build_script_chain",
            return_value=(
                [{"code": "console.log(1)", "language": "javascript", "source_name": "pre"}],
                [{"code": "pm.test('x',()=>{})", "language": "javascript", "source_name": "test"}],
            ),
        ):
            result = run_agent_scripts(request_id=int(req.id), phase="both")
        assert result["ok"] is True
        assert mock_pre.called
        assert mock_test.called
        assert result.get("test_results") == [{"name": "status ok", "passed": True}]

    def test_missing_request(self) -> None:
        """Unknown request_id fails cleanly."""
        result = run_agent_scripts(request_id=999_999_999)
        assert result["ok"] is False
        assert result["error"] == "request_not_found"


class TestWorkspaceExecuteDispatch:
    """Execute tool dispatches to agent send helpers (mocked)."""

    def test_send_request_mocked(self, monkeypatch: Any) -> None:
        """send_request operation returns observation from run_agent_send_request."""
        called: dict[str, Any] = {}

        def _fake_send(**kwargs: Any) -> dict[str, Any]:
            called.update(kwargs)
            return {
                "ok": True,
                "summary": "Sent GET Ping",
                "status_code": 204,
                "url": "https://example.com",
                "ids": {"request_id": kwargs["request_id"]},
                "test_results": [],
            }

        monkeypatch.setattr(
            "services.ai.chat.execution.agent_send.run_agent_send_request",
            _fake_send,
        )
        obs = _execute(
            WorkspaceExecuteAction(
                operation="send_request",
                request_id=42,
                record_history=False,
                include_scripts=False,
            )
        )
        text = str(obs.text)
        assert "ok: true" in text
        assert called["request_id"] == 42
        assert called["record_history"] is False

    def test_run_scripts_mocked(self, monkeypatch: Any) -> None:
        """run_scripts operation calls run_agent_scripts."""
        called: dict[str, Any] = {}

        def _fake_scripts(**kwargs: Any) -> dict[str, Any]:
            called.update(kwargs)
            return {
                "ok": True,
                "summary": "Ran scripts",
                "test_results": [],
                "ids": {"request_id": kwargs["request_id"]},
            }

        monkeypatch.setattr(
            "services.ai.chat.execution.agent_send.run_agent_scripts",
            _fake_scripts,
        )
        obs = _execute(
            WorkspaceExecuteAction(
                operation="run_scripts",
                request_id=7,
                script_phase="pre",
            )
        )
        assert "ok: true" in str(obs.text)
        assert called["request_id"] == 7
        assert called["phase"] == "pre"
