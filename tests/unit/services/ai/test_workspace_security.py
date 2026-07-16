"""Tests for PostmarkWorkspaceSecurityAnalyzer + confirmation policy."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from openhands.sdk.security import ConfirmRisky, NeverConfirm, SecurityRisk

from services.ai.chat.mutation.auto_approve import add_rule, clear_rules
from services.ai.chat.mutation.security import (
    PostmarkWorkspaceSecurityAnalyzer,
    apply_confirmation_policy,
)


@pytest.fixture(autouse=True)
def _clear_whitelist(qapp: Any) -> Iterator[None]:
    """Start each case with an empty auto-approve whitelist."""
    del qapp
    clear_rules()
    yield
    clear_rules()


def _event(
    tool_name: str,
    *,
    action: str | None = None,
    entity: str | None = None,
    operation: str | None = None,
) -> Any:
    """Build a duck-typed ActionEvent for the analyzer."""
    action_obj = None
    if action is not None or entity is not None or operation is not None:
        action_obj = SimpleNamespace(action=action, entity=entity, operation=operation)
    return SimpleNamespace(tool_name=tool_name, action=action_obj)


class TestWorkspaceSecurityAnalyzer:
    """HIGH for mutate/execute unless auto-approved; LOW for wiki/read tools."""

    def test_empty_whitelist_mutate_is_high(self) -> None:
        """Mutate kinds require confirmation when the whitelist is empty."""
        analyzer = PostmarkWorkspaceSecurityAnalyzer()
        risk = analyzer.security_risk(
            _event("postmark_workspace_mutate", action="create", entity="collection")
        )
        assert risk == SecurityRisk.HIGH

    def test_wiki_query_is_low(self) -> None:
        """Read-only wiki tool is always LOW."""
        analyzer = PostmarkWorkspaceSecurityAnalyzer()
        assert analyzer.security_risk(_event("postmark_wiki_query")) == SecurityRisk.LOW

    def test_workspace_query_is_low(self) -> None:
        """Read-only workspace query is always LOW."""
        analyzer = PostmarkWorkspaceSecurityAnalyzer()
        assert analyzer.security_risk(_event("postmark_workspace_query")) == SecurityRisk.LOW

    def test_auto_approve_lowers_risk(self) -> None:
        """Whitelisted kind becomes LOW (skips ConfirmRisky pause)."""
        assert add_rule("mutate:create:collection")
        analyzer = PostmarkWorkspaceSecurityAnalyzer()
        risk = analyzer.security_risk(
            _event("postmark_workspace_mutate", action="create", entity="collection")
        )
        assert risk == SecurityRisk.LOW

    def test_mixed_batch_concept(self) -> None:
        """Only auto-approved kinds drop to LOW; others stay HIGH."""
        assert add_rule("execute:send_request")
        analyzer = PostmarkWorkspaceSecurityAnalyzer()
        send_risk = analyzer.security_risk(
            _event("postmark_workspace_execute", operation="send_request")
        )
        delete_risk = analyzer.security_risk(
            _event("postmark_workspace_mutate", action="delete", entity="request")
        )
        assert send_risk == SecurityRisk.LOW
        assert delete_risk == SecurityRisk.HIGH

    def test_unknown_tool_is_high(self) -> None:
        """Unknown tools require confirmation."""
        analyzer = PostmarkWorkspaceSecurityAnalyzer()
        assert analyzer.security_risk(_event("some_unknown_tool")) == SecurityRisk.HIGH


class TestApplyConfirmationPolicy:
    """Agent+mutations attaches ConfirmRisky; otherwise NeverConfirm."""

    def test_agent_mutations_uses_confirm_risky(self) -> None:
        """Agent mode attaches analyzer + ConfirmRisky."""

        class _Conv:
            """Minimal conversation stub for policy attachment."""

            def __init__(self) -> None:
                self.policy: object | None = None
                self.analyzer: object | None = None

            def set_confirmation_policy(self, policy: object) -> None:
                self.policy = policy

            def set_security_analyzer(self, analyzer: object) -> None:
                self.analyzer = analyzer

        conv = _Conv()
        apply_confirmation_policy(conv, send_mode="agent")
        assert isinstance(conv.policy, ConfirmRisky)
        assert isinstance(conv.analyzer, PostmarkWorkspaceSecurityAnalyzer)

    def test_ask_uses_never_confirm(self) -> None:
        """Ask mode clears analyzer and uses NeverConfirm."""

        class _Conv:
            """Minimal conversation stub for policy attachment."""

            def __init__(self) -> None:
                self.policy: object | None = None
                self.analyzer: object | None = "sentinel"

            def set_confirmation_policy(self, policy: object) -> None:
                self.policy = policy

            def set_security_analyzer(self, analyzer: object) -> None:
                self.analyzer = analyzer

        conv = _Conv()
        apply_confirmation_policy(conv, send_mode="ask")
        assert isinstance(conv.policy, NeverConfirm)
        assert conv.analyzer is None
