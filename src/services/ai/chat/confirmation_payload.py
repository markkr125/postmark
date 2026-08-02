"""Pending-action payload helpers for AI chat confirmation chrome."""

from __future__ import annotations

from typing import Any

from services.ai.chat.mutation.auto_approve import kind_from_action_event, kind_label

_DESTRUCTIVE_KIND_PREFIXES = ("mutate:delete:",)
CONTINUE_ITERATIONS_KIND = "continue_iterations"
_MAX_ITERATIONS_CODE = "MaxIterationsReached"


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


def continue_iterations_payload(*, tool_calls: int, limit: int) -> dict[str, Any]:
    """Build Approve-chrome payload asking whether to run another iteration round.

    Reuses the pending-tool card UI with Continue / Stop labels (no Always allow).
    """
    n = max(0, int(tool_calls))
    cap = max(1, int(limit))
    calls = "tool call" if n == 1 else "tool calls"
    detail = (
        f"Used {n} {calls} and hit the step limit ({cap}). "
        "Continue for another round, or stop here?"
    )
    return {
        "prompt": CONTINUE_ITERATIONS_KIND,
        "actions": [
            {
                "kind": CONTINUE_ITERATIONS_KIND,
                "kind_label": "Continue working?",
                "title": "Continue working?",
                "detail": detail,
                "summary": detail,
                "visualize": detail,
                "risk": "normal",
            }
        ],
    }


def is_continue_iterations_payload(payload: object) -> bool:
    """Return whether *payload* is a max-iterations Continue / Stop prompt."""
    if not isinstance(payload, dict):
        return False
    if str(payload.get("prompt") or "") == CONTINUE_ITERATIONS_KIND:
        return True
    actions = payload.get("actions")
    if not isinstance(actions, list) or not actions:
        return False
    first = actions[0]
    return isinstance(first, dict) and str(first.get("kind") or "") == CONTINUE_ITERATIONS_KIND


def is_waiting_for_confirmation(conversation: object) -> bool:
    """Return True when the conversation is paused for user confirmation."""
    from openhands.sdk import ConversationExecutionStatus

    state = getattr(conversation, "state", None)
    status = getattr(state, "execution_status", None)
    return status == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION


def is_max_iterations_reached(conversation: object) -> bool:
    """Return True when the last run stopped on ``MaxIterationsReached``.

    OpenHands sets ``execution_status`` to ERROR and emits a conversation error
    event with that code. Other ERROR shapes must not offer Continue.
    """
    from openhands.sdk import ConversationExecutionStatus

    state = getattr(conversation, "state", None)
    status = getattr(state, "execution_status", None)
    if status != ConversationExecutionStatus.ERROR:
        return False
    events = getattr(state, "events", None) or []
    for event in reversed(list(events)[-40:]):
        code = str(getattr(event, "code", "") or "")
        if code == _MAX_ITERATIONS_CODE:
            return True
        detail = str(getattr(event, "detail", "") or "")
        if (
            type(event).__name__ in {"ConversationErrorEvent", "AgentErrorEvent"}
            and "maximum iterations limit" in detail.lower()
        ):
            return True
    return False


def _is_destructive_kind(kind: str | None) -> bool:
    if not kind:
        return False
    return any(kind.startswith(prefix) for prefix in _DESTRUCTIVE_KIND_PREFIXES)


__all__ = [
    "CONTINUE_ITERATIONS_KIND",
    "continue_iterations_payload",
    "is_continue_iterations_payload",
    "is_max_iterations_reached",
    "is_waiting_for_confirmation",
    "pending_actions_payload",
]
