"""Tests for postmark_workspace_mutate collection/request CRUD + assertion_set."""

from __future__ import annotations

from services.ai.chat.mutation.bridge import clear_mutation_events, drain_mutation_events
from services.ai.chat.tools.workspace_mutate.tool import (
    WorkspaceMutateAction,
    _apply_mutation,
    _filter_fields,
)
from services.assertion_service import AssertionService
from services.collection_service import CollectionService


def _obs_ok(obs: object) -> bool:
    """Return True when an observation text reports success."""
    return "ok: true" in str(getattr(obs, "text", obs))


class TestWorkspaceMutateCollections:
    """CRUD paths for collections and requests via the mutate executor."""

    def setup_method(self) -> None:
        """Clear bridge queue before each case."""
        clear_mutation_events()

    def teardown_method(self) -> None:
        """Clear bridge queue after each case."""
        clear_mutation_events()

    def test_collection_create_rename_update_move_delete(self) -> None:
        """Full collection lifecycle."""
        created = _apply_mutation(
            WorkspaceMutateAction(
                action="create",
                entity="collection",
                fields={"name": "Alpha"},
                open_after=False,
            )
        )
        assert _obs_ok(created)
        roots = CollectionService.fetch_all()
        alpha = next(c for c in roots.values() if c.get("name") == "Alpha")
        alpha_id = int(alpha["id"])

        renamed = _apply_mutation(
            WorkspaceMutateAction(
                action="rename",
                entity="collection",
                target_id=alpha_id,
                fields={"name": "Beta"},
                open_after=False,
            )
        )
        assert _obs_ok(renamed)
        beta = CollectionService.get_collection(alpha_id)
        assert beta is not None
        assert beta.name == "Beta"

        updated = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="collection",
                target_id=alpha_id,
                fields={"description": "desc"},
                open_after=False,
            )
        )
        assert _obs_ok(updated)

        parent = CollectionService.create_collection("Parent")
        moved = _apply_mutation(
            WorkspaceMutateAction(
                action="move",
                entity="collection",
                target_id=alpha_id,
                parent_id=int(parent.id),
                open_after=False,
            )
        )
        assert _obs_ok(moved)

        deleted = _apply_mutation(
            WorkspaceMutateAction(
                action="delete",
                entity="collection",
                target_id=alpha_id,
                open_after=False,
            )
        )
        assert _obs_ok(deleted)
        assert CollectionService.get_collection(alpha_id) is None

    def test_request_crud_duplicate_and_description(self) -> None:
        """Request create (with description via update), update, rename, move, duplicate, delete."""
        col = CollectionService.create_collection("ReqCol")
        other = CollectionService.create_collection("Other")
        created = _apply_mutation(
            WorkspaceMutateAction(
                action="create",
                entity="request",
                collection_id=int(col.id),
                fields={
                    "name": "Get Users",
                    "method": "GET",
                    "url": "https://example.com/users",
                    "description": "list users",
                    "body_mode": "raw",
                },
                open_after=True,
            )
        )
        assert _obs_ok(created)
        events = drain_mutation_events()
        assert any(e.get("type") == "open_target" for e in events)
        req_id = next(
            e["ids"]["request_id"]
            for e in events
            if e.get("type") == "mutated" and "request_id" in (e.get("ids") or {})
        )
        loaded = CollectionService.get_request(req_id)
        assert loaded is not None
        assert loaded.description == "list users"
        assert loaded.body_mode == "raw"

        updated = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="request",
                target_id=req_id,
                fields={"url": "https://example.com/v2/users", "method": "POST"},
                open_after=False,
            )
        )
        assert _obs_ok(updated)
        loaded = CollectionService.get_request(req_id)
        assert loaded is not None
        assert loaded.url == "https://example.com/v2/users"
        assert loaded.method == "POST"

        renamed = _apply_mutation(
            WorkspaceMutateAction(
                action="rename",
                entity="request",
                target_id=req_id,
                fields={"name": "Create User"},
                open_after=False,
            )
        )
        assert _obs_ok(renamed)

        moved = _apply_mutation(
            WorkspaceMutateAction(
                action="move",
                entity="request",
                target_id=req_id,
                collection_id=int(other.id),
                open_after=False,
            )
        )
        assert _obs_ok(moved)

        dup = _apply_mutation(
            WorkspaceMutateAction(
                action="duplicate",
                entity="request",
                target_id=req_id,
                open_after=False,
            )
        )
        assert _obs_ok(dup)

        deleted = _apply_mutation(
            WorkspaceMutateAction(
                action="delete",
                entity="request",
                target_id=req_id,
                open_after=False,
            )
        )
        assert _obs_ok(deleted)
        assert CollectionService.get_request(req_id) is None

    def test_reject_collection_duplicate(self) -> None:
        """Duplicate is request-only."""
        col = CollectionService.create_collection("NoDup")
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="duplicate",
                entity="collection",
                target_id=int(col.id),
                open_after=False,
            )
        )
        text = str(obs.text)
        assert "ok: false" in text
        assert "collection_duplicate_not_supported" in text

    def test_filter_rejects_scripts_when_disallowed(self) -> None:
        """Scripts require allow_scripts; auth is allowlisted with secrets policy."""
        cleaned, err = _filter_fields(
            "request",
            "update",
            {"auth": {"type": "bearer", "token": "{{api_token}}"}},
            allow_scripts=True,
        )
        assert err is None
        assert cleaned is not None
        assert "auth" in cleaned

        cleaned2, err2 = _filter_fields(
            "request",
            "update",
            {"scripts": {"test": "pm.test('x', () => {})"}},
            allow_scripts=False,
        )
        assert cleaned2 is None
        assert err2 is not None
        assert "unsupported_field" in str(err2.text)

        cleaned3, err3 = _filter_fields(
            "request",
            "update",
            {"scripts": {"test": "pm.test('x', () => {})"}},
            allow_scripts=True,
        )
        assert err3 is None
        assert cleaned3 is not None
        assert "scripts" in cleaned3

    def test_assertion_set_replace(self) -> None:
        """entity=assertion_set replaces declarative assertion rows."""
        col = CollectionService.create_collection("AssertCol")
        req = CollectionService.create_request(
            int(col.id),
            "GET",
            "https://example.com",
            "Assert Me",
        )
        AssertionService.save_for_request(
            int(req.id),
            [
                {
                    "subject": "status",
                    "operator": "eq",
                    "expected": "200",
                    "enabled": True,
                    "order_index": 0,
                }
            ],
        )
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="assertion_set",
                target_id=int(req.id),
                fields={
                    "assertions": [
                        {
                            "subject": "status",
                            "operator": "eq",
                            "expected": "201",
                            "enabled": True,
                            "order_index": 0,
                        },
                        {
                            "subject": "body",
                            "operator": "contains",
                            "expected": "ok",
                            "enabled": True,
                            "order_index": 1,
                        },
                    ]
                },
                open_after=False,
            )
        )
        assert _obs_ok(obs)
        rows = AssertionService.fetch_for_request(int(req.id))
        assert len(rows) == 2
        assert rows[0]["expected"] == "201"
        assert rows[1]["subject"] == "body"

    def test_collection_update_name_renames(self) -> None:
        """Collection update with fields.name routes through rename_collection."""
        col = CollectionService.create_collection("Hotel Booking API")
        cid = int(col.id)
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="collection",
                target_id=cid,
                fields={"name": "Hotel Booking API 2"},
                open_after=False,
            )
        )
        assert _obs_ok(obs)
        assert "Hotel Booking API 2" in str(obs.text)
        updated = CollectionService.get_collection(cid)
        assert updated is not None
        assert updated.name == "Hotel Booking API 2"

    def test_collection_update_name_and_description(self) -> None:
        """Update may rename and patch description in one mutate call."""
        col = CollectionService.create_collection("Combo")
        cid = int(col.id)
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="collection",
                target_id=cid,
                fields={"name": "Combo 2", "description": "renamed folder"},
                open_after=False,
            )
        )
        assert _obs_ok(obs)
        assert "Combo 2" in str(obs.text)
        updated = CollectionService.get_collection(cid)
        assert updated is not None
        assert updated.name == "Combo 2"
        assert updated.description == "renamed folder"

    def test_collection_update_name_and_auth_mentions_rename(self) -> None:
        """Name plus auth uses rename then auth update; summary mentions rename."""
        col = CollectionService.create_collection("AuthRename")
        cid = int(col.id)
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="collection",
                target_id=cid,
                fields={
                    "name": "AuthRename 2",
                    "auth": {"type": "bearer", "token": "{{api_token}}"},
                },
                open_after=False,
            )
        )
        assert _obs_ok(obs)
        text = str(obs.text)
        assert "AuthRename 2" in text
        updated = CollectionService.get_collection(cid)
        assert updated is not None
        assert updated.name == "AuthRename 2"

    def test_collection_update_name_and_variables_mentions_rename(self) -> None:
        """Name plus variables uses rename then variables update; summary mentions rename."""
        col = CollectionService.create_collection("VarRename")
        cid = int(col.id)
        obs = _apply_mutation(
            WorkspaceMutateAction(
                action="update",
                entity="collection",
                target_id=cid,
                fields={
                    "name": "VarRename 2",
                    "variables": [{"key": "base", "value": "https://example.com"}],
                },
                open_after=False,
            )
        )
        assert _obs_ok(obs)
        text = str(obs.text)
        assert "VarRename 2" in text
        updated = CollectionService.get_collection(cid)
        assert updated is not None
        assert updated.name == "VarRename 2"
