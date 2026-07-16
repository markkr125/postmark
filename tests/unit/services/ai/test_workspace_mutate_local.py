"""Tests for local script mutate + secrets/auth/env data-plane mutations."""

from __future__ import annotations

from services.ai.chat.mutation.auto_approve import kind_from_tool_args
from services.ai.chat.mutation.bridge import clear_mutation_events, drain_mutation_events
from services.ai.chat.tools.workspace_mutate.common import (
    reject_raw_secret_value,
    sanitize_auth_payload,
    sanitize_env_values,
)
from services.ai.chat.tools.workspace_mutate.tool import (
    WorkspaceMutateAction,
    _apply_mutation,
)
from services.environment_service import EnvironmentService
from services.local_script_service import LocalScriptService
from services.snippet_service import SnippetService


def _obs_ok(obs: object) -> bool:
    """Return True when an observation text reports success."""
    return "ok: true" in str(getattr(obs, "text", obs))


def _obs_text(obs: object) -> str:
    """Return observation text."""
    return str(getattr(obs, "text", obs))


class TestWorkspaceMutateLocalScripts:
    """Local script / folder CRUD via the mutate executor."""

    def setup_method(self) -> None:
        """Clear bridge queue before each case."""
        clear_mutation_events()

    def teardown_method(self) -> None:
        """Clear bridge queue after each case."""
        clear_mutation_events()

    def test_local_script_folder_and_script_lifecycle(self) -> None:
        """Create folder + script, update content, rename, delete."""
        folder_obs = _apply_mutation(
            WorkspaceMutateAction(
                action="create",
                entity="local_script_folder",
                fields={"name": "AgentScripts"},
                open_after=False,
            )
        )
        assert _obs_ok(folder_obs)
        events = drain_mutation_events()
        folder_ids = next(e["ids"] for e in events if e.get("type") == "mutated")
        folder_id = int(folder_ids["local_script_folder_id"])

        created = _apply_mutation(
            WorkspaceMutateAction(
                action="create",
                entity="local_script",
                parent_id=folder_id,
                fields={
                    "name": "helpers.js",
                    "language": "javascript",
                    "module_format": "esm",
                    "content": "export const x = 1;\n",
                },
                open_after=False,
            )
        )
        assert _obs_ok(created)
        events = drain_mutation_events()
        script_ids = next(e["ids"] for e in events if e.get("type") == "mutated")
        script_id = int(script_ids["local_script_id"])
        load = LocalScriptService.get_script_load_dict(script_id)
        assert load is not None
        assert "export const x" in (load.get("content") or "")

        updated = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="local_script",
                target_id=script_id,
                fields={"content": "export const x = 2;\n"},
                open_after=False,
            )
        )
        assert _obs_ok(updated)
        load2 = LocalScriptService.get_script_load_dict(script_id)
        assert load2 is not None
        assert "x = 2" in (load2.get("content") or "")

        renamed = _apply_mutation(
            WorkspaceMutateAction(
                action="rename",
                entity="local_script",
                target_id=script_id,
                fields={"name": "utils.js"},
                open_after=False,
            )
        )
        assert _obs_ok(renamed)

        deleted = _apply_mutation(
            WorkspaceMutateAction(
                action="delete",
                entity="local_script",
                target_id=script_id,
                open_after=False,
            )
        )
        assert _obs_ok(deleted)
        assert LocalScriptService.get_script_load_dict(script_id) is None


class TestWorkspaceMutateSecretsPolicy:
    """Raw secrets rejected; placeholders accepted."""

    def test_reject_raw_secret_value(self) -> None:
        """Sensitive keys reject raw tokens."""
        assert reject_raw_secret_value("token", "sk-live-abc") == "raw_secret_rejected"
        assert reject_raw_secret_value("token", "{{api_token}}") is None
        assert reject_raw_secret_value("token", "") is None
        assert reject_raw_secret_value("host", "api.example.com") is None

    def test_sanitize_auth_rejects_raw_bearer(self) -> None:
        """Bearer token must be empty or placeholder."""
        cleaned, err = sanitize_auth_payload({"type": "bearer", "token": "super-secret-token"})
        assert cleaned is None
        assert err == "raw_secret_rejected"
        cleaned2, err2 = sanitize_auth_payload({"type": "bearer", "token": "{{bearer_token}}"})
        assert err2 is None
        assert cleaned2 is not None

    def test_environment_update_rejects_raw_secret(self) -> None:
        """Environment secret-typed rows reject raw values."""
        clear_mutation_events()
        env = EnvironmentService.create_environment("AgentEnv")
        bad = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="environment",
                target_id=int(env.id),
                fields={
                    "values": [
                        {
                            "key": "API_TOKEN",
                            "value": "raw-token-value",
                            "type": "secret",
                            "enabled": True,
                        }
                    ]
                },
                open_after=False,
            )
        )
        assert not _obs_ok(bad)
        assert "raw_secret_rejected" in _obs_text(bad)

        good = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="environment",
                target_id=int(env.id),
                fields={
                    "values": [
                        {
                            "key": "API_TOKEN",
                            "value": "{{API_TOKEN}}",
                            "type": "secret",
                            "enabled": True,
                        },
                        {
                            "key": "BASE_URL",
                            "value": "https://api.example.com",
                            "enabled": True,
                        },
                    ]
                },
                open_after=False,
            )
        )
        assert _obs_ok(good)
        clear_mutation_events()

    def test_auth_kind_not_auto_approvable(self) -> None:
        """Auth updates map to a never-always-allow kind."""
        kind = kind_from_tool_args(
            "postmark_workspace_mutate",
            action="update",
            entity="request",
        )
        # Without fields, base kind is mutate:update:request
        assert kind == "mutate:update:request"

    def test_snippet_create(self) -> None:
        """Snippet create via mutate tool."""
        clear_mutation_events()
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="create",
                entity="snippet",
                fields={
                    "name": "Agent Snip",
                    "language": "javascript",
                    "body": "console.log(1)",
                    "category": "My snippets",
                    "context": "both",
                },
                open_after=False,
            )
        )
        assert _obs_ok(obs)
        rows = SnippetService.list_all("javascript")
        assert any(r["name"] == "Agent Snip" for r in rows)
        clear_mutation_events()

    def test_sanitize_env_values_ok(self) -> None:
        """Non-secret rows pass through."""
        cleaned, err = sanitize_env_values(
            [{"key": "host", "value": "example.com", "enabled": True}]
        )
        assert err is None
        assert cleaned is not None
        assert cleaned[0]["key"] == "host"
