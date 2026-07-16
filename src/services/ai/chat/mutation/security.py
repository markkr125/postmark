"""OpenHands security analyzer for Postmark workspace mutate/execute tools."""

from __future__ import annotations

from openhands.sdk.event.llm_convertible import ActionEvent
from openhands.sdk.security import ConfirmRisky, NeverConfirm, SecurityRisk
from openhands.sdk.security.analyzer import SecurityAnalyzerBase

from services.ai.chat.mutation.auto_approve import (
    is_auto_approved,
    is_mutate_or_execute_tool,
    kind_from_action_event,
)

_READ_ONLY_HINT_TOOLS = frozenset(
    {
        "postmark_wiki_query",
        "postmark_workspace_query",
        "postmark_datetime",
        "delegate",
        "task",
        "task_tracker",
        "ThinkTool",
        "FinishTool",
        "think",
        "finish",
    }
)


class PostmarkWorkspaceSecurityAnalyzer(SecurityAnalyzerBase):
    """Mark mutate/execute HIGH unless the kind is on the auto-approve whitelist."""

    def security_risk(self, action: ActionEvent) -> SecurityRisk:
        """Return LOW for read tools / auto-approved kinds; else HIGH for mutate."""
        tool_name = str(action.tool_name or "")
        if tool_name in _READ_ONLY_HINT_TOOLS:
            return SecurityRisk.LOW
        if is_mutate_or_execute_tool(tool_name):
            kind = kind_from_action_event(action)
            if is_auto_approved(kind):
                return SecurityRisk.LOW
            return SecurityRisk.HIGH
        # Unknown tools: require confirmation.
        return SecurityRisk.HIGH


def apply_confirmation_policy(
    conversation: object,
    *,
    send_mode: str | None,
) -> None:
    """Attach ConfirmRisky + analyzer in Agent mode; NeverConfirm for Ask/Plan."""
    mode = (send_mode or "ask").strip().lower()
    set_policy = getattr(conversation, "set_confirmation_policy", None)
    set_analyzer = getattr(conversation, "set_security_analyzer", None)
    if not callable(set_policy) or not callable(set_analyzer):
        return
    if mode == "agent":
        set_analyzer(PostmarkWorkspaceSecurityAnalyzer())
        set_policy(ConfirmRisky(threshold=SecurityRisk.HIGH, confirm_unknown=True))
    else:
        set_analyzer(None)
        set_policy(NeverConfirm())


__all__ = [
    "PostmarkWorkspaceSecurityAnalyzer",
    "apply_confirmation_policy",
]
