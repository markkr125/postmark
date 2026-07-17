"""Tests for active env, history delete, version restore, folder events."""

from __future__ import annotations

from types import SimpleNamespace

from services.ai.chat.mutation.auto_approve import CATALOG, kind_from_tool_args
from services.ai.chat.mutation.bridge import (
    clear_mutation_events,
    drain_mutation_events,
    enqueue_mutation_event,
)
from services.ai.chat.tools.workspace_mutate.tool import (
    WorkspaceMutateAction,
    _apply_mutation,
)
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.local_script_service import LocalScriptService
from services.request_history_service import RequestHistoryService, SendIdentityDict
from services.script_version_service import ScriptVersionService
from ui.main_window.mutation_drain.drain import drain_mutation_bridge
from ui.styling.history_settings_manager import HistorySettingsManager


def _obs_ok(obs: object) -> bool:
    """Return True when an observation text reports success."""
    return "ok: true" in str(getattr(obs, "text", obs))


def _obs_text(obs: object) -> str:
    """Return observation text."""
    return str(getattr(obs, "text", obs))


class TestActiveEnvironmentMutate:
    """Bridge-only active environment set/clear."""

    def setup_method(self) -> None:
        """Clear bridge queue before each case."""
        clear_mutation_events()

    def teardown_method(self) -> None:
        """Clear bridge queue after each case."""
        clear_mutation_events()

    def test_set_and_clear_active_environment(self) -> None:
        """Set then clear enqueue mutated events without DB writes."""
        env = EnvironmentService.create_environment("AgentEnv")
        set_obs = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="active_environment",
                fields={"environment_id": int(env.id)},
                open_after=False,
            )
        )
        assert _obs_ok(set_obs)
        events = drain_mutation_events()
        mutated = next(e for e in events if e.get("type") == "mutated")
        assert mutated["entity"] == "active_environment"
        assert mutated["action"] == "set"
        assert mutated["ids"]["environment_id"] == int(env.id)
        assert (
            WorkspaceMutateAction(
                action="update",
                entity="active_environment",
                fields={"environment_id": int(env.id)},
            ).human_preview()
            == "Activate AgentEnv"
        )

        clear_obs = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="active_environment",
                fields={"environment_id": None},
                open_after=False,
            )
        )
        assert _obs_ok(clear_obs)
        assert (
            "Clear active environment"
            in WorkspaceMutateAction(
                action="update",
                entity="active_environment",
                fields={"environment_id": None},
            ).human_preview()
        )
        events = drain_mutation_events()
        mutated = next(e for e in events if e.get("type") == "mutated")
        assert mutated["action"] == "clear"
        assert mutated.get("ids") == {}

    def test_active_environment_missing(self) -> None:
        """Unknown environment id fails."""
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="active_environment",
                fields={"environment_id": 999999},
                open_after=False,
            )
        )
        assert not _obs_ok(obs)
        assert "environment_not_found" in _obs_text(obs)

    def test_drain_calls_set_active_on_env_selector(self) -> None:
        """Drain uses ``_env_selector.set_active_environment``."""
        calls: list[int | None] = []

        class _Env:
            def set_active_environment(self, env_id: int | None) -> None:
                calls.append(env_id)

            def refresh(self) -> None:
                pass

        host = SimpleNamespace(
            _env_selector=_Env(),
            _right_sidebar=SimpleNamespace(ai_chat_panel=SimpleNamespace()),
            _tabs={},
            _tab_bar=None,
        )
        enqueue_mutation_event(
            {
                "type": "mutated",
                "entity": "active_environment",
                "action": "set",
                "ids": {"environment_id": 42},
                "warnings": [],
            }
        )
        drain_mutation_bridge(host)
        assert calls == [42]

        enqueue_mutation_event(
            {
                "type": "mutated",
                "entity": "active_environment",
                "action": "clear",
                "ids": {},
                "warnings": [],
            }
        )
        drain_mutation_bridge(host)
        assert calls == [42, None]

    def test_catalog_kind(self) -> None:
        """Auto-approve catalog includes active environment."""
        assert "mutate:update:active_environment" in CATALOG
        assert (
            kind_from_tool_args(
                "postmark_workspace_mutate",
                action="update",
                entity="active_environment",
            )
            == "mutate:update:active_environment"
        )


class TestFolderEventsMutate:
    """Collection ``events`` (folder scripts) updates."""

    def setup_method(self) -> None:
        """Clear bridge queue before each case."""
        clear_mutation_events()

    def teardown_method(self) -> None:
        """Clear bridge queue after each case."""
        clear_mutation_events()

    def test_update_collection_events_and_focus(self) -> None:
        """Allow events field and open_target focus=test."""
        coll = CollectionService.create_collection("ScriptsFolder")
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="collection",
                target_id=int(coll.id),
                fields={
                    "events": {
                        "pre_request": "// pre",
                        "test": "pm.test('ok', () => {});",
                        "test_language": "javascript",
                    }
                },
                open_after=True,
            )
        )
        assert _obs_ok(obs)
        loaded = CollectionService.get_collection(int(coll.id))
        assert loaded is not None
        assert "pm.test" in str((loaded.events or {}).get("test") or "")
        events = drain_mutation_events()
        open_ev = next(e for e in events if e.get("type") == "open_target")
        target = open_ev.get("open_target")
        assert isinstance(target, dict)
        assert target.get("focus") == "test"

    def test_events_rejected_when_scripts_disallowed(self) -> None:
        """Events requires allow_scripts gate."""
        from services.ai.chat.tools.workspace_mutate.tool import _filter_fields

        coll = CollectionService.create_collection("NoScripts")
        fields, err = _filter_fields(
            "collection",
            "update",
            {"events": {"test": "x"}},
            allow_scripts=False,
        )
        assert fields is None
        assert err is not None
        assert "unsupported_field" in _obs_text(err)
        del coll


class TestHistoryEntryDelete:
    """Delete request history via mutate."""

    def setup_method(self) -> None:
        """Clear bridge queue before each case."""
        clear_mutation_events()

    def teardown_method(self) -> None:
        """Clear bridge queue after each case."""
        clear_mutation_events()

    def test_delete_history_entry(self, tmp_path, monkeypatch, qapp) -> None:
        """Delete removes the entry and enqueues refresh."""
        monkeypatch.setattr(
            "database.data_paths.postmark_user_data_dir",
            lambda: tmp_path / "postmark",
        )
        settings = HistorySettingsManager()
        identity: SendIdentityDict = {
            "request_id": None,
            "request_name": "",
            "method": "GET",
            "url": "http://example.com/agent-hist",
        }
        entry_id = RequestHistoryService.record_send(
            identity=identity,
            response={"status_code": 200, "elapsed_ms": 1.0, "headers": [], "body": "ok"},
            original_request={"method": "GET", "url": "http://example.com/agent-hist"},
            settings=settings,
        )
        assert entry_id is not None
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="delete",
                entity="history_entry",
                target_id=int(entry_id),
                open_after=False,
            )
        )
        assert _obs_ok(obs)
        assert RequestHistoryService.get_entry(int(entry_id)) is None
        events = drain_mutation_events()
        mutated = next(e for e in events if e.get("type") == "mutated")
        assert mutated["entity"] == "history_entry"
        assert mutated["ids"]["history_entry_id"] == int(entry_id)
        assert "mutate:delete:history_entry" in CATALOG

    def test_delete_missing_history_entry(self) -> None:
        """Missing entry returns not found."""
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="delete",
                entity="history_entry",
                target_id=999999,
                open_after=False,
            )
        )
        assert not _obs_ok(obs)
        assert "history_entry_not_found" in _obs_text(obs)

    def test_drain_refreshes_history_panels(self) -> None:
        """History delete drain refreshes both panels."""
        calls: list[str] = []

        class _Panel:
            def refresh(self) -> None:
                calls.append("request")

        host = SimpleNamespace(
            _env_selector=None,
            _right_sidebar=SimpleNamespace(ai_chat_panel=SimpleNamespace()),
            _tabs={},
            _tab_bar=None,
            _request_history_panel=_Panel(),
            _refresh_global_history_panel=lambda: calls.append("global"),
        )
        enqueue_mutation_event(
            {
                "type": "mutated",
                "entity": "history_entry",
                "action": "delete",
                "ids": {"history_entry_id": 1},
                "warnings": [],
            }
        )
        drain_mutation_bridge(host)
        assert "global" in calls
        assert "request" in calls


class TestScriptVersionRestore:
    """Merge-safe script version restore."""

    def setup_method(self) -> None:
        """Clear bridge queue before each case."""
        clear_mutation_events()

    def teardown_method(self) -> None:
        """Clear bridge queue after each case."""
        clear_mutation_events()

    def test_restore_request_test_preserves_pre_request(self) -> None:
        """Restoring test does not wipe pre_request."""
        coll = CollectionService.create_collection("VerColl")
        req = CollectionService.create_request(
            int(coll.id),
            "GET",
            "https://example.com",
            "VerReq",
            scripts={
                "pre_request": "// keep me",
                "test": "// old test",
                "pre_language": "javascript",
                "test_language": "javascript",
            },
        )
        version = ScriptVersionService.capture(
            request_id=int(req.id),
            script_type="test",
            content="// restored test",
            language="javascript",
        )
        assert version is not None
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="restore",
                entity="script_version",
                target_id=int(version["id"]),
                open_after=False,
            )
        )
        assert _obs_ok(obs)
        loaded = CollectionService.get_request(int(req.id))
        assert loaded is not None
        scripts = loaded.scripts or {}
        assert scripts.get("pre_request") == "// keep me"
        assert scripts.get("test") == "// restored test"
        assert "mutate:restore:script_version" in CATALOG

    def test_restore_local_script(self) -> None:
        """Restore local script content from version."""
        folder = LocalScriptService.create_folder("VerScripts")
        script = LocalScriptService.create_script(
            folder_id=int(folder.id),
            name="v.js",
            language="javascript",
            content="export const a = 1;\n",
        )
        LocalScriptService.save_script_content(int(script.id), "export const a = 2;\n")
        version = ScriptVersionService.capture(
            local_script_id=int(script.id),
            script_type="local",
            content="export const a = 1;\n",
            language="javascript",
        )
        assert version is not None
        LocalScriptService.save_script_content(int(script.id), "export const a = 9;\n")
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="restore",
                entity="script_version",
                target_id=int(version["id"]),
                open_after=False,
            )
        )
        assert _obs_ok(obs)
        load = LocalScriptService.get_script_load_dict(int(script.id))
        assert load is not None
        assert "a = 1" in (load.get("content") or "")

    def test_restore_missing_version(self) -> None:
        """Missing version id fails."""
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="restore",
                entity="script_version",
                target_id=999999,
                open_after=False,
            )
        )
        assert not _obs_ok(obs)
        assert "script_version_not_found" in _obs_text(obs)
