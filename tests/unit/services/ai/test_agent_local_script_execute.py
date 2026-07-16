"""Tests for agent local script execute + local mutate bridge kinds."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from services.ai.chat.execution.agent_local_script import run_agent_local_script
from services.ai.chat.mutation.auto_approve import (
    add_rule,
    kind_from_action_event,
)
from services.ai.chat.tools.workspace_execute.tool import (
    WorkspaceExecuteAction,
    _execute,
)
from services.local_script_service import LocalScriptService


class TestRunAgentLocalScript:
    """run_agent_local_script dispatches through run_local_entry."""

    def test_missing_script(self) -> None:
        """Unknown local_script_id fails cleanly."""
        result = run_agent_local_script(local_script_id=999_999_999)
        assert result["ok"] is False
        assert result["error"] == "local_script_not_found"

    @patch("services.scripting.local_scripts_project.runner.run_local_entry")
    def test_success_returns_console_and_tests(self, mock_run: MagicMock) -> None:
        """Successful run surfaces test_results and console_logs."""
        folder = LocalScriptService.create_folder("AgentScripts")
        created = LocalScriptService.create_script(
            int(folder.id),
            "ping.js",
            language="javascript",
            content="console.log('hi'); pm.test('ok', () => {});",
        )
        mock_run.return_value = {
            "test_results": [{"name": "ok", "passed": True}],
            "console_logs": [{"level": "log", "message": "hi"}],
            "elapsed_ms": 12.5,
            "error": None,
        }
        result = run_agent_local_script(local_script_id=int(created.id))
        assert result["ok"] is True
        assert result["test_results"] == [{"name": "ok", "passed": True}]
        assert result["console_logs"] == [{"level": "log", "message": "hi"}]
        assert (result.get("ids") or {}).get("local_script_id") == int(created.id)
        mock_run.assert_called_once()

    def test_empty_script_ok_without_run(self) -> None:
        """Blank content short-circuits without calling Deno."""
        folder = LocalScriptService.create_folder("EmptyScripts")
        created = LocalScriptService.create_script(
            int(folder.id),
            "empty.js",
            language="javascript",
            content="   ",
        )
        with patch("services.scripting.local_scripts_project.runner.run_local_entry") as mock_run:
            result = run_agent_local_script(local_script_id=int(created.id))
        assert result["ok"] is True
        assert mock_run.called is False


class TestWorkspaceExecuteLocalScript:
    """Execute tool dispatches run_local_script."""

    def test_run_local_script_mocked(self, monkeypatch: Any) -> None:
        """run_local_script operation calls run_agent_local_script."""
        called: dict[str, Any] = {}

        def _fake_local(**kwargs: Any) -> dict[str, Any]:
            called.update(kwargs)
            return {
                "ok": True,
                "summary": "Ran local script",
                "test_results": [],
                "console_logs": [{"level": "log", "message": "x"}],
                "ids": {"local_script_id": kwargs["local_script_id"]},
            }

        monkeypatch.setattr(
            "services.ai.chat.execution.agent_local_script.run_agent_local_script",
            _fake_local,
        )
        obs = _execute(
            WorkspaceExecuteAction(
                operation="run_local_script",
                local_script_id=55,
            )
        )
        text = str(obs.text)
        assert "ok: true" in text
        assert called["local_script_id"] == 55
        assert "console_logs" in text


class TestLocalMutateKinds:
    """Auto-approve kind mapping for local script entities."""

    def test_local_script_create_kind(self) -> None:
        """Local script create maps to mutate:create:local_script."""
        event = type(
            "Evt",
            (),
            {
                "tool_name": "postmark_workspace_mutate",
                "action": type(
                    "Act",
                    (),
                    {
                        "action": "create",
                        "entity": "local_script",
                        "operation": None,
                        "fields": {"name": "util.js"},
                    },
                )(),
            },
        )()
        assert kind_from_action_event(event) == "mutate:create:local_script"
        assert add_rule("mutate:create:local_script")


class TestSecretsAutoApproveRejection:
    """Auth and secret env kinds are never always-allowed."""

    def test_auth_kind_not_in_catalog(self) -> None:
        """mutate:update:auth is derived but not whitelisted."""
        event = type(
            "Evt",
            (),
            {
                "tool_name": "postmark_workspace_mutate",
                "action": type(
                    "Act",
                    (),
                    {
                        "action": "update",
                        "entity": "request",
                        "operation": None,
                        "fields": {
                            "auth": {"type": "bearer", "token": "{{api_token}}"},
                        },
                    },
                )(),
            },
        )()
        assert kind_from_action_event(event) == "mutate:update:auth"
        assert add_rule("mutate:update:auth") is False

    def test_secret_env_write_kind_rejected(self) -> None:
        """Raw secret env values map to environment_secret (not catalogued)."""
        event = type(
            "Evt",
            (),
            {
                "tool_name": "postmark_workspace_mutate",
                "action": type(
                    "Act",
                    (),
                    {
                        "action": "update",
                        "entity": "environment",
                        "operation": None,
                        "fields": {
                            "values": [
                                {"key": "api_key", "value": "super-secret", "enabled": True},
                            ],
                        },
                    },
                )(),
            },
        )()
        assert kind_from_action_event(event) == "mutate:update:environment_secret"
        assert add_rule("mutate:update:environment_secret") is False
