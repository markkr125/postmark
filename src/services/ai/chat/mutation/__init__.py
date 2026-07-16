"""Workspace mutation confirmation, bridge, and audit helpers."""

from __future__ import annotations

from services.ai.chat.mutation.audit import append_mutation_audit
from services.ai.chat.mutation.auto_approve import (
    CATALOG,
    add_rule,
    clear_rules,
    is_auto_approved,
    kind_from_action_event,
    kind_label,
    list_rules,
    remove_rule,
)
from services.ai.chat.mutation.bridge import (
    MutationBridgeEvent,
    OpenTargetDict,
    drain_mutation_events,
    enqueue_mutation_event,
)
from services.ai.chat.mutation.security import (
    PostmarkWorkspaceSecurityAnalyzer,
    apply_confirmation_policy,
)

__all__ = [
    "CATALOG",
    "MutationBridgeEvent",
    "OpenTargetDict",
    "PostmarkWorkspaceSecurityAnalyzer",
    "add_rule",
    "append_mutation_audit",
    "apply_confirmation_policy",
    "clear_rules",
    "drain_mutation_events",
    "enqueue_mutation_event",
    "is_auto_approved",
    "kind_from_action_event",
    "kind_label",
    "list_rules",
    "remove_rule",
]
