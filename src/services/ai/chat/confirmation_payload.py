"""Pending-action payload helpers for AI chat confirmation chrome."""

from __future__ import annotations

from typing import Any

from services.ai.chat.mutation.auto_approve import kind_from_action_event, kind_label

_DESTRUCTIVE_KIND_PREFIXES = ("mutate:delete:",)


def pending_actions_payload(conversation: object) -> dict[str, Any]:
    """Build the GUI payload listing every unmatched pending action.

    Display fields for Approve cards:
    - ``title`` — catalog kind label (e.g. Create collection)
    - ``detail`` — human one-liner (name, URL, …)
    - ``url`` — redacted send destination when applicable
    - ``risk`` — ``destructive`` for delete kinds

    ``tool_name`` is retained for debugging only and is not rendered.
    """
    from openhands.sdk.conversation.state import ConversationState

    events = getattr(getattr(conversation, "state", None), "events", None) or []
    pending = ConversationState.get_unmatched_actions(events)
    actions: list[dict[str, Any]] = []
    for event in pending:
        tool_name = str(getattr(event, "tool_name", "") or "")
        kind = kind_from_action_event(event)
        title = kind_label(kind) if kind else (tool_name or "Action")
        detail = ""
        url: str | None = None
        action_obj = getattr(event, "action", None)
        if action_obj is not None:
            preview = getattr(action_obj, "preview_url", None)
            if callable(preview):
                try:
                    raw_url = preview()
                    url = str(raw_url) if raw_url else None
                except Exception:
                    url = None
            human = getattr(action_obj, "human_preview", None)
            if callable(human):
                try:
                    detail = str(human() or "").strip()
                except Exception:
                    detail = ""
            if not detail:
                summary_attr = str(getattr(action_obj, "summary", "") or "").strip()
                detail = summary_attr
        if not detail and url:
            detail = url
        if not detail:
            detail = title
        risk = "destructive" if _is_destructive_kind(kind) else "normal"
        tool_call_id = str(getattr(event, "tool_call_id", "") or "").strip()
        row: dict[str, Any] = {
            "tool_name": tool_name,
            "kind": kind,
            "kind_label": title,
            "title": title,
            "detail": detail,
            "summary": detail,
            "visualize": detail,
            "risk": risk,
        }
        if tool_call_id:
            row["tool_call_id"] = tool_call_id
        if url:
            row["url"] = url
        actions.append(row)
    return {"actions": actions}


def is_waiting_for_confirmation(conversation: object) -> bool:
    """Return True when the conversation is paused for user confirmation."""
    from openhands.sdk import ConversationExecutionStatus

    state = getattr(conversation, "state", None)
    status = getattr(state, "execution_status", None)
    return status == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION


def _is_destructive_kind(kind: str | None) -> bool:
    if not kind:
        return False
    return any(kind.startswith(prefix) for prefix in _DESTRUCTIVE_KIND_PREFIXES)


__all__ = ["is_waiting_for_confirmation", "pending_actions_payload"]
