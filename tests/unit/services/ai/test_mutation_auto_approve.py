"""Tests for Agent auto-approve whitelist rules."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from services.ai.chat.mutation.auto_approve import (
    CATALOG,
    add_rule,
    clear_rules,
    is_auto_approved,
    kind_from_tool_args,
    kind_label,
    list_rules,
    remove_rule,
)


@pytest.fixture(autouse=True)
def _reset_rules(qapp: Any) -> Iterator[None]:
    """Clear whitelist around each test."""
    del qapp
    clear_rules()
    yield
    clear_rules()


class TestMutationAutoApprove:
    """Catalog-validated add/remove/clear and Phase 2 kinds."""

    def test_add_remove_and_list(self) -> None:
        """Valid kinds round-trip through list_rules."""
        assert add_rule("mutate:create:collection")
        assert add_rule("execute:send_request")
        assert set(list_rules()) == {
            "execute:send_request",
            "mutate:create:collection",
        }
        assert is_auto_approved("mutate:create:collection")
        remove_rule("mutate:create:collection")
        assert list_rules() == ["execute:send_request"]
        assert not is_auto_approved("mutate:create:collection")

    def test_invalid_kind_rejected(self) -> None:
        """Unknown kinds are not persisted."""
        assert add_rule("mutate:hack:everything") is False
        assert list_rules() == []

    def test_clear_rules(self) -> None:
        """clear_rules empties the whitelist."""
        assert add_rule("mutate:delete:request")
        clear_rules()
        assert list_rules() == []

    def test_phase2_kinds_in_catalog(self) -> None:
        """Phase 2 assertion_set + run_scripts kinds are catalogued."""
        assert "mutate:update:assertion_set" in CATALOG
        assert "execute:run_scripts" in CATALOG
        assert "execute:run_local_script" in CATALOG
        assert "mutate:create:local_script" in CATALOG
        assert add_rule("mutate:update:assertion_set")
        assert add_rule("execute:run_scripts")
        assert add_rule("execute:run_local_script")
        assert is_auto_approved("mutate:update:assertion_set")
        assert kind_label("mutate:update:assertion_set") == "Replace assertions"

    def test_never_always_allow_kinds_rejected(self) -> None:
        """Auth, secret-env, and OAuth Get Token cannot be Always-allowed."""
        assert add_rule("mutate:update:auth") is False
        assert add_rule("mutate:update:environment_secret") is False
        assert add_rule("execute:oauth_get_token") is False
        assert list_rules() == []

    def test_kind_from_tool_args(self) -> None:
        """Tool name + action fields map to catalog kinds."""
        assert (
            kind_from_tool_args(
                "postmark_workspace_mutate",
                action="create",
                entity="request",
            )
            == "mutate:create:request"
        )
        assert (
            kind_from_tool_args(
                "postmark_workspace_execute",
                operation="run_scripts",
            )
            == "execute:run_scripts"
        )
        assert (
            kind_from_tool_args(
                "postmark_workspace_execute",
                operation="run_local_script",
            )
            == "execute:run_local_script"
        )
        assert kind_from_tool_args("postmark_import") == "mutate:create:import"
        assert kind_from_tool_args("postmark_wiki_query") is None
