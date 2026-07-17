"""Parse OpenHands SDK events into main-agent tool activity rows for the chat UI."""

from __future__ import annotations

import time
from typing import Any, Literal, NotRequired, TypedDict

from services.ai.chat.mutation.auto_approve import (
    is_auto_approved,
    is_mutate_or_execute_tool,
    kind_from_action_event,
    kind_label,
)
from services.ai.chat.mutation.claim_guard import observation_indicates_write

ToolActivityStatus = Literal[
    "pending_confirm",
    "running",
    "completed",
    "error",
    "rejected",
    "suppressed",
]

_TOOL_ACTIVITY_NAMES = frozenset(
    {
        "postmark_workspace_query",
        "postmark_datetime",
        "postmark_import",
        "postmark_workspace_mutate",
        "postmark_workspace_execute",
    }
)

_EXECUTE_TOOL = "postmark_workspace_execute"
_MIN_VISIBLE_SECONDS = 0.4


class ToolActivityRecord(TypedDict):
    """One main-agent tool row shown in the assistant transcript."""

    id: str
    tool_name: str
    title: str
    detail: str
    status: ToolActivityStatus
    started_at: NotRequired[float]
    completed_at: NotRequired[float]


def _is_action_event(event: object) -> bool:
    """Return whether *event* is an OpenHands tool action event."""
    if type(event).__name__ == "ActionEvent":
        return True
    try:
        from openhands.sdk.event.llm_convertible.action import ActionEvent

        return isinstance(event, ActionEvent)
    except ImportError:
        return False


def _is_observation_event(event: object) -> bool:
    """Return whether *event* is an OpenHands tool observation event."""
    if type(event).__name__ == "ObservationEvent":
        return True
    try:
        from openhands.sdk.event.llm_convertible.observation import ObservationEvent

        return isinstance(event, ObservationEvent)
    except ImportError:
        return False


def _observation_text(observation: object | None) -> str:
    """Return observation body text for outcome parsing."""
    if observation is None:
        return ""
    text = getattr(observation, "text", None)
    if isinstance(text, str):
        return text
    content = getattr(observation, "content", None)
    if isinstance(content, str):
        return content
    return str(observation)


def _observation_is_error(observation: object | None) -> bool:
    """Return True when the SDK marks the observation as an error."""
    if observation is None:
        return False
    return bool(getattr(observation, "is_error", False))


def _title_detail_for_action(tool_name: str, action_event: object) -> tuple[str, str]:
    """Build human title and detail from a tool action event."""
    action = getattr(action_event, "action", action_event)
    human = getattr(action, "human_preview", None)
    detail = ""
    if callable(human):
        try:
            detail = str(human() or "").strip()
        except Exception:
            detail = ""
    if tool_name == "postmark_workspace_query":
        scope = str(getattr(action, "scope", "") or "workspace").strip()
        goals = getattr(action, "goals", None)
        title = "Query workspace"
        if not detail:
            detail = f"{len(goals)} goals" if goals else scope
        return title, detail
    if tool_name == "postmark_datetime":
        operation = str(getattr(action, "operation", "") or "now").strip()
        title = "Date & time"
        if not detail:
            detail = operation
        return title, detail
    kind = kind_from_action_event(action_event)
    title = (
        kind_label(kind) if kind else tool_name.removeprefix("postmark_").replace("_", " ").title()
    )
    if not detail:
        summary = str(getattr(action, "summary", "") or "").strip()
        detail = summary or title
    return title, detail


def _needs_confirmation(tool_name: str, action_event: object) -> bool:
    """Return True when this action pauses for Approve before execution."""
    if not is_mutate_or_execute_tool(tool_name):
        return False
    kind = kind_from_action_event(action_event)
    if kind in {"mutate:update:auth", "mutate:update:environment_secret"}:
        return True
    return not is_auto_approved(kind)


def _write_outcome_status(text: str) -> ToolActivityStatus:
    """Map a write-tool observation to completed vs error."""
    if observation_indicates_write(text):
        return "completed"
    return "error"


def _visible_records(records: dict[str, ToolActivityRecord]) -> list[ToolActivityRecord]:
    """Return transcript-visible rows in stable order."""
    out: list[ToolActivityRecord] = []
    for record in records.values():
        status = record["status"]
        if status in {"pending_confirm", "suppressed"}:
            continue
        out.append(record)
    return out


class ToolActivityTracker:
    """Track main-agent tool calls for in-flight activity cards."""

    def __init__(self) -> None:
        """Start with an empty turn."""
        self._records: dict[str, ToolActivityRecord] = {}
        self._last_reject_ids: list[str] = []

    def records(self) -> list[ToolActivityRecord]:
        """Return visible activity records for the current turn."""
        return _visible_records(self._records)

    def ingest(self, event: object) -> list[ToolActivityRecord]:
        """Update state from one SDK event; return records that changed."""
        if _is_action_event(event):
            return self._ingest_action(event)
        if _is_observation_event(event):
            return self._ingest_observation(event)
        return []

    def on_confirmation_approved(self, tool_call_ids: list[str]) -> list[ToolActivityRecord]:
        """Start running cards for confirm-gated tools the user allowed."""
        changed: list[ToolActivityRecord] = []
        now = time.time()
        for call_id in tool_call_ids:
            record = self._records.get(call_id)
            if record is None or record["status"] != "pending_confirm":
                continue
            record["status"] = "running"
            record["started_at"] = now
            changed.append(record)
        return changed

    def on_confirmation_rejected(self, tool_call_ids: list[str]) -> list[ToolActivityRecord]:
        """Finalize confirm-gated tools the user rejected."""
        changed: list[ToolActivityRecord] = []
        now = time.time()
        for call_id in tool_call_ids:
            record = self._records.get(call_id)
            if record is None or record["status"] != "pending_confirm":
                continue
            record["status"] = "rejected"
            record["completed_at"] = now
            changed.append(record)
        self._last_reject_ids = list(tool_call_ids)
        return changed

    def fail_inflight(self) -> list[ToolActivityRecord]:
        """Mark running tools as errored when the turn aborts."""
        changed: list[ToolActivityRecord] = []
        now = time.time()
        for record in self._records.values():
            if record["status"] not in {"running", "pending_confirm"}:
                continue
            record["status"] = "error"
            record["completed_at"] = now
            changed.append(record)
        return changed

    def _ingest_action(self, event: object) -> list[ToolActivityRecord]:
        tool_name = str(getattr(event, "tool_name", "") or "")
        if tool_name not in _TOOL_ACTIVITY_NAMES:
            return []
        action = getattr(event, "action", None)
        if action is None:
            return []
        tool_call_id = str(getattr(event, "tool_call_id", "") or "").strip()
        record_id = tool_call_id or f"{tool_name}:{len(self._records)}"
        title, detail = _title_detail_for_action(tool_name, event)
        now = time.time()
        if _needs_confirmation(tool_name, event):
            record: ToolActivityRecord = {
                "id": record_id,
                "tool_name": tool_name,
                "title": title,
                "detail": detail,
                "status": "pending_confirm",
                "started_at": now,
            }
        else:
            record = {
                "id": record_id,
                "tool_name": tool_name,
                "title": title,
                "detail": detail,
                "status": "running",
                "started_at": now,
            }
        self._records[record_id] = record
        if record["status"] == "pending_confirm":
            return []
        return [record]

    def _ingest_observation(self, event: object) -> list[ToolActivityRecord]:
        tool_name = str(getattr(event, "tool_name", "") or "")
        if tool_name not in _TOOL_ACTIVITY_NAMES:
            return []
        tool_call_id = str(getattr(event, "tool_call_id", "") or "").strip()
        record_id = tool_call_id or ""
        record = self._records.get(record_id)
        if record is None:
            for candidate in self._records.values():
                if candidate["tool_name"] == tool_name and candidate["status"] == "running":
                    record = candidate
                    record_id = candidate["id"]
                    break
        if record is None:
            return []

        observation = getattr(event, "observation", None)
        text = _observation_text(observation)
        now = time.time()
        started = float(record.get("started_at", now))
        duration = now - started

        if tool_name == _EXECUTE_TOOL:
            record["status"] = "suppressed"
            record["completed_at"] = now
            return [record]

        if _observation_is_error(observation):
            record["status"] = "error"
        elif is_mutate_or_execute_tool(tool_name):
            record["status"] = _write_outcome_status(text)
        else:
            record["status"] = "completed"

        record["completed_at"] = now

        if (
            record["status"] == "completed"
            and duration < _MIN_VISIBLE_SECONDS
            and tool_name == "postmark_datetime"
        ):
            record["status"] = "suppressed"

        if record["status"] == "suppressed":
            return [record]
        return [record]


def records_for_turn_events(events: list[Any]) -> list[ToolActivityRecord]:
    """Rebuild tool activity cards from OpenHands EventLog events for one user turn."""
    tracker = ToolActivityTracker()
    for event in events:
        if _is_action_event(event) or _is_observation_event(event):
            tracker.ingest(event)
    return tracker.records()


def records_for_assistant_turn(
    session_id: str,
    messages: list[Any],
    msg_index: int,
    *,
    events: list[Any] | None = None,
) -> list[ToolActivityRecord]:
    """Rebuild tool activity cards for one persisted assistant message."""
    from services.ai.chat.context_usage import iter_session_events
    from services.ai.chat.subagent_events import (
        _slice_events_for_turn,
        _turn_index_for_message,
    )

    loaded = events if events is not None else iter_session_events(session_id)
    if not loaded:
        return []
    turn_index = _turn_index_for_message(messages, msg_index)
    slice_events = _slice_events_for_turn(loaded, turn_index)
    return records_for_turn_events(slice_events)


def tool_call_ids_from_confirmation_payload(payload: object) -> list[str]:
    """Extract tool_call_id values from a pending confirmation payload."""
    if not isinstance(payload, dict):
        return []
    actions = payload.get("actions")
    if not isinstance(actions, list):
        return []
    ids: list[str] = []
    for row in actions:
        if not isinstance(row, dict):
            continue
        call_id = str(row.get("tool_call_id") or "").strip()
        if call_id:
            ids.append(call_id)
    return ids


__all__ = [
    "ToolActivityRecord",
    "ToolActivityStatus",
    "ToolActivityTracker",
    "records_for_assistant_turn",
    "records_for_turn_events",
    "tool_call_ids_from_confirmation_payload",
]
