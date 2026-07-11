"""Parse OpenHands SDK events into subagent run records for the chat UI."""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Literal, NotRequired, TypedDict

from services.ai.chat.subagent_disk_registry import (
    next_unassigned_subagent_disk_path,
    resolve_subagent_disk_path,
)

SubagentKind = Literal["task", "delegate", "wiki"]
SubagentStatus = Literal["warming", "running", "completed", "error"]

_SUBAGENT_DISPLAY_NAMES: dict[str, str] = {
    "wiki-researcher": "Wiki researcher",
    "workspace-researcher": "Workspace researcher",
    "general-purpose": "General purpose",
}


class SubagentActivityStep(TypedDict):
    """One visible activity line inside a subagent card body."""

    id: str
    summary: str
    icon: NotRequired[str]
    detail: NotRequired[str]


class SubagentRunRecord(TypedDict):
    """One subagent delegation row shown in the assistant transcript."""

    id: str
    kind: SubagentKind
    label: str
    subagent_type: str
    status: SubagentStatus
    task_prompt: NotRequired[str]
    result_preview: NotRequired[str]
    result_markdown: NotRequired[str]
    disk_path: NotRequired[str]
    tool_call_id: NotRequired[str]
    started_at: NotRequired[float]
    steps: NotRequired[list[SubagentActivityStep]]


def subagent_type_display(subagent_type: str) -> str:
    """Return a human label for a registered subagent type."""
    return _SUBAGENT_DISPLAY_NAMES.get(subagent_type, subagent_type.replace("-", " ").title())


def enrich_subagent_records(
    records: list[SubagentRunRecord],
    *,
    session_id: str | None = None,
) -> list[SubagentRunRecord]:
    """Attach live activity steps and disk paths before rendering cards."""
    from services.ai.chat.subagent_transcript import steps_for_subagent_record

    assigned: set[str] = set()
    enriched: list[SubagentRunRecord] = []
    turn_started_at = min(
        (float(r.get("started_at", time.time() - 300.0)) for r in records),
        default=time.time() - 300.0,
    )
    for record in records:
        copy = SubagentRunRecord(**record)
        existing = copy.get("disk_path")
        if existing:
            assigned.add(existing)
        if not copy.get("disk_path") and session_id:
            started = float(copy.get("started_at", turn_started_at))
            path = resolve_subagent_disk_path(
                session_id,
                copy,
                turn_started_at=started,
                assigned=assigned,
            )
            if path is not None:
                copy["disk_path"] = path
                assigned.add(path)
        if not copy.get("steps"):
            copy["steps"] = steps_for_subagent_record(copy)
        enriched.append(copy)
    return enriched


_TASK_TOOL_NAMES = frozenset({"task", "task_tool_set"})
_DELEGATE_TOOL_NAMES = frozenset({"delegate", "postmark_delegate"})
_WIKI_TOOL_NAMES = frozenset({"postmark_wiki_query"})


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


def _observation_text(observation: object) -> str:
    text = getattr(observation, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    content = getattr(observation, "content", None)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            raw = getattr(block, "text", None)
            if isinstance(raw, str) and raw.strip():
                parts.append(raw.strip())
        if parts:
            return "\n".join(parts)
    return ""


def _preview(text: str, *, limit: int = 240) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _set_result_text(record: SubagentRunRecord, text: str) -> None:
    """Store full reply markdown plus a short card/activity preview."""
    cleaned = text.strip()
    if not cleaned:
        return
    record["result_markdown"] = cleaned
    record["result_preview"] = _preview(cleaned)


def record_result_markdown(record: SubagentRunRecord) -> str:
    """Return the full reply text for the detail dialog (fallback to preview)."""
    full = record.get("result_markdown", "")
    if isinstance(full, str) and full.strip():
        return full.strip()
    preview = record.get("result_preview", "")
    if isinstance(preview, str) and preview.strip():
        return preview.strip()
    return ""


_DELEGATE_AGENT_RESULT_RE = re.compile(
    r"^\d+\.\s*Agent\s+(?P<id>[^:]+):\s*(?P<body>.*?)(?=^\d+\.\s*Agent\s+|\Z)",
    re.MULTILINE | re.DOTALL,
)


def delegate_agent_results_from_observation(text: str) -> dict[str, str]:
    """Parse per-agent reply bodies from a parent ``DelegateObservation`` text blob."""
    results: dict[str, str] = {}
    for match in _DELEGATE_AGENT_RESULT_RE.finditer(text):
        agent_id = match.group("id").strip()
        body = match.group("body").strip()
        if agent_id and body:
            results[agent_id] = body
    return results


def delegate_agent_result_from_observation(text: str, agent_id: str) -> str:
    """Return the full markdown reply for one spawned id from delegate observation text."""
    return delegate_agent_results_from_observation(text).get(agent_id, "")


class SubagentEventTracker:
    """Stateful parser for task/delegate tool events in one assistant turn."""

    def __init__(
        self,
        *,
        session_id: str = "",
        turn_started_at: float | None = None,
    ) -> None:
        """Start tracking with an empty record list.

        ``turn_started_at`` overrides the wall-clock turn start. Pass the real
        turn time when rebuilding from persisted events so disk-path resolution
        does not reject the (older) subagent folders on a post-restart replay.
        """
        self._session_id = session_id
        self._records: dict[str, SubagentRunRecord] = {}
        self._turn_started_at = time.time() if turn_started_at is None else turn_started_at
        self._pending_delegate_ids: list[str] = []
        self._disk_paths_assigned: set[str] = set()

    def records(self) -> list[SubagentRunRecord]:
        """Return records in stable display order."""
        return list(self._records.values())

    def fail_inflight(self) -> list[SubagentRunRecord]:
        """Mark warming/running cards failed when the parent turn aborts."""
        changed: list[SubagentRunRecord] = []
        for record in self._records.values():
            if record["status"] not in ("warming", "running"):
                continue
            record["status"] = "error"
            if not record.get("result_preview"):
                record["result_preview"] = "Turn failed before completion"
            changed.append(self._store_record(record))
        return changed

    def _store_record(self, record: SubagentRunRecord) -> SubagentRunRecord:
        """Persist one record and stamp turn start time."""
        if "started_at" not in record:
            record["started_at"] = self._turn_started_at
        self._records[record["id"]] = record
        return record

    def ingest(self, event: object) -> list[SubagentRunRecord]:
        """Update state from one SDK event; return records that changed."""
        if _is_action_event(event):
            return self._ingest_action(event)
        if _is_observation_event(event):
            return self._ingest_observation(event)
        return []

    def _ingest_action(self, event: object) -> list[SubagentRunRecord]:
        tool_name = str(getattr(event, "tool_name", "") or "")
        action = getattr(event, "action", None)
        tool_call_id = str(getattr(event, "tool_call_id", "") or "")
        if action is None:
            return []

        if tool_name in _TASK_TOOL_NAMES:
            return self._ingest_task_action(action, tool_call_id=tool_call_id)
        if tool_name in _DELEGATE_TOOL_NAMES:
            return self._ingest_delegate_action(action, tool_call_id=tool_call_id)
        if tool_name in _WIKI_TOOL_NAMES:
            return self._ingest_wiki_action(action, tool_call_id=tool_call_id)
        return []

    def _ingest_task_action(self, action: object, *, tool_call_id: str) -> list[SubagentRunRecord]:
        action_type = type(action).__name__
        if action_type != "TaskAction":
            return []
        description = getattr(action, "description", None)
        prompt = getattr(action, "prompt", None)
        subagent_type = str(getattr(action, "subagent_type", "") or "general-purpose")
        label = (
            str(description).strip()
            if description
            else (_preview(str(prompt), limit=80) if prompt else subagent_type)
        )
        record_id = tool_call_id or f"task:{subagent_type}:{len(self._records)}"
        record: SubagentRunRecord = {
            "id": record_id,
            "kind": "task",
            "label": label,
            "subagent_type": subagent_type,
            "status": "running",
        }
        if prompt:
            record["task_prompt"] = str(prompt).strip()
        if tool_call_id:
            record["tool_call_id"] = tool_call_id
        return [self._store_record(record)]

    def _ingest_spawn_ids(
        self,
        ids: list[str],
        *,
        agent_types: list[str],
        tool_call_id: str,
    ) -> list[SubagentRunRecord]:
        """Create warming cards for spawned subagent ids."""
        self._pending_delegate_ids = list(ids)
        changed: list[SubagentRunRecord] = []
        for index, agent_id in enumerate(self._pending_delegate_ids):
            agent_type = (
                str(agent_types[index]).strip()
                if index < len(agent_types) and agent_types[index]
                else "general-purpose"
            )
            record: SubagentRunRecord = {
                "id": agent_id,
                "kind": "delegate",
                "label": agent_id,
                "subagent_type": agent_type,
                "status": "warming",
            }
            if tool_call_id:
                record["tool_call_id"] = tool_call_id
            changed.append(self._store_record(record))
        return changed

    def _delegate_tasks_in_order(self, tasks: dict[object, object]) -> list[tuple[str, object]]:
        """Return delegate task entries in spawn order when available."""
        task_map = {str(key): value for key, value in tasks.items()}
        ordered: list[str] = []
        for agent_id in self._pending_delegate_ids:
            if agent_id in task_map:
                ordered.append(agent_id)
        for agent_id in task_map:
            if agent_id not in ordered:
                ordered.append(agent_id)
        return [(agent_id, task_map[agent_id]) for agent_id in ordered]

    def _ingest_delegate_task_map(
        self,
        tasks: dict[object, object],
        *,
        tool_call_id: str,
    ) -> list[SubagentRunRecord]:
        """Mark spawned subagents running from a tasks map."""
        changed: list[SubagentRunRecord] = []
        for agent_id, task_text in self._delegate_tasks_in_order(tasks):
            key = agent_id
            existing = self._records.get(key)
            agent_type = existing["subagent_type"] if existing else "general-purpose"
            task_full = str(task_text).strip()
            label = _preview(task_full, limit=80) or key
            record = SubagentRunRecord(
                id=key,
                kind="delegate",
                label=label,
                subagent_type=agent_type,
                status="running",
            )
            if task_full:
                record["task_prompt"] = task_full
            if tool_call_id:
                record["tool_call_id"] = tool_call_id
            if existing:
                if existing.get("disk_path"):
                    record["disk_path"] = existing["disk_path"]
                    self._disk_paths_assigned.add(existing["disk_path"])
                if existing.get("started_at"):
                    record["started_at"] = existing["started_at"]
            self._assign_disk_path(record)
            changed.append(self._store_record(record))
        return changed

    def _ingest_delegate_action(
        self, action: object, *, tool_call_id: str
    ) -> list[SubagentRunRecord]:
        action_type = type(action).__name__
        if action_type != "DelegateAction":
            return []
        command = str(getattr(action, "command", "") or "")
        if command == "spawn":
            ids = getattr(action, "ids", None) or []
            agent_types = getattr(action, "agent_types", None) or []
            return self._ingest_spawn_ids(
                [str(i) for i in ids],
                agent_types=[str(t) for t in agent_types],
                tool_call_id=tool_call_id,
            )
        if command != "delegate":
            return []
        tasks = getattr(action, "tasks", None) or {}
        return self._ingest_delegate_task_map(tasks, tool_call_id=tool_call_id)

    def _ingest_wiki_action(self, action: object, *, tool_call_id: str) -> list[SubagentRunRecord]:
        """Parent inline wiki lookup — show as a wiki-researcher card."""
        if type(action).__name__ != "WikiQueryAction":
            return []
        query = str(getattr(action, "query", "") or "").strip()
        label = _preview(query, limit=80) or "Searching wiki"
        record_id = tool_call_id or f"wiki:{len(self._records)}"
        record: SubagentRunRecord = {
            "id": record_id,
            "kind": "wiki",
            "label": label,
            "subagent_type": "wiki-researcher",
            "status": "running",
        }
        if query:
            record["task_prompt"] = query
        if tool_call_id:
            record["tool_call_id"] = tool_call_id
        return [self._store_record(record)]

    def _ingest_observation(self, event: object) -> list[SubagentRunRecord]:
        tool_name = str(getattr(event, "tool_name", "") or "")
        observation = getattr(event, "observation", None)
        tool_call_id = str(getattr(event, "tool_call_id", "") or "")
        if observation is None:
            return []

        if tool_name in _TASK_TOOL_NAMES:
            return self._ingest_task_observation(observation, tool_call_id=tool_call_id)
        if tool_name in _DELEGATE_TOOL_NAMES:
            return self._ingest_delegate_observation(observation)
        if tool_name in _WIKI_TOOL_NAMES:
            return self._ingest_wiki_observation(observation, tool_call_id=tool_call_id)
        return []

    def _ingest_wiki_observation(
        self, observation: object, *, tool_call_id: str
    ) -> list[SubagentRunRecord]:
        """Complete a parent wiki lookup card."""
        if type(observation).__name__ != "WikiQueryObservation":
            return []
        record = self._find_running_record(tool_call_id, kinds=("wiki", "task"))
        if record is None:
            record_id = tool_call_id or f"wiki:{len(self._records)}"
            record = SubagentRunRecord(
                id=record_id,
                kind="wiki",
                label="Searching wiki",
                subagent_type="wiki-researcher",
                status="running",
            )
            self._store_record(record)
        text = _observation_text(observation)
        is_error = bool(getattr(observation, "is_error", False))
        record["status"] = "error" if is_error else "completed"
        if text:
            _set_result_text(record, text)
        return [self._store_record(record)]

    def _find_running_record(
        self,
        tool_call_id: str,
        *,
        kinds: tuple[SubagentKind, ...],
    ) -> SubagentRunRecord | None:
        """Match an in-flight record by tool call id or last running row."""
        if tool_call_id and tool_call_id in self._records:
            return self._records[tool_call_id]
        for candidate in reversed(self.records()):
            if candidate["kind"] in kinds and candidate["status"] == "running":
                return candidate
        return None

    def _assign_disk_path(self, record: SubagentRunRecord) -> None:
        if record.get("disk_path"):
            return
        if not self._session_id:
            return
        path = resolve_subagent_disk_path(
            self._session_id,
            record,
            turn_started_at=self._turn_started_at,
            assigned=self._disk_paths_assigned,
        )
        if path is None:
            return
        record["disk_path"] = path
        self._disk_paths_assigned.add(path)

    def _ingest_task_observation(
        self, observation: object, *, tool_call_id: str
    ) -> list[SubagentRunRecord]:
        if type(observation).__name__ != "TaskObservation":
            return []
        task_id = str(getattr(observation, "task_id", "") or "")
        record_id = tool_call_id or task_id
        record = self._records.get(record_id)
        if record is None and task_id:
            for candidate in self._records.values():
                if candidate["kind"] == "task" and candidate["status"] == "running":
                    record = candidate
                    break
        if record is None:
            subagent_type = str(getattr(observation, "subagent", "") or "general-purpose")
            record = SubagentRunRecord(
                id=task_id or record_id or f"task:{len(self._records)}",
                kind="task",
                label=task_id or subagent_type,
                subagent_type=subagent_type,
                status="running",
            )
            self._store_record(record)

        text = _observation_text(observation)
        is_error = bool(getattr(observation, "is_error", False))
        status = str(getattr(observation, "status", "") or "")
        record["status"] = "error" if is_error or status == "error" else "completed"
        if text:
            _set_result_text(record, text)
        if task_id:
            old_id = record["id"]
            record["id"] = task_id
            record["label"] = record.get("label") or task_id
            if old_id != task_id and old_id in self._records:
                del self._records[old_id]
        self._assign_disk_path(record)
        return [self._store_record(record)]

    def _ingest_delegate_observation(self, observation: object) -> list[SubagentRunRecord]:
        if type(observation).__name__ != "DelegateObservation":
            return []
        command = str(getattr(observation, "command", "") or "")
        text = _observation_text(observation)
        is_error = bool(getattr(observation, "is_error", False))
        changed: list[SubagentRunRecord] = []

        if command == "spawn":
            for record in self._records.values():
                if record["kind"] != "delegate" or record.get("disk_path"):
                    continue
                self._assign_disk_path(record)
                changed.append(self._store_record(record))
            return changed

        running = [
            r
            for r in self._records.values()
            if r["kind"] == "delegate" and r["status"] == "running"
        ]
        if not running:
            running = [
                r
                for r in self._records.values()
                if r["kind"] == "delegate" and r["status"] in ("warming", "running")
            ]
        final_status: SubagentStatus = "error" if is_error else "completed"
        per_agent = delegate_agent_results_from_observation(text)
        for record in running:
            record["status"] = final_status
            agent_result = per_agent.get(record["id"], "")
            if agent_result and not record.get("result_markdown"):
                _set_result_text(record, agent_result)
            elif text and not record.get("result_markdown"):
                _set_result_text(record, text)
            self._assign_disk_path(record)
            changed.append(self._store_record(record))
        return changed


def _earliest_event_epoch(events: list[Any]) -> float | None:
    """Return the earliest event wall-clock epoch from ISO ``timestamp`` fields."""
    earliest: float | None = None
    for event in events:
        raw = getattr(event, "timestamp", None)
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        epoch = parsed.timestamp()
        if earliest is None or epoch < earliest:
            earliest = epoch
    return earliest


def records_for_turn_events(
    events: list[Any],
    *,
    session_id: str = "",
) -> list[SubagentRunRecord]:
    """Rebuild subagent cards from a slice of parent session SDK events.

    The turn start is taken from the events' own timestamps (not the current
    clock) so a post-restart replay resolves the subagent disk folders by mtime.
    """
    tracker = SubagentEventTracker(
        session_id=session_id,
        turn_started_at=_earliest_event_epoch(events),
    )
    for event in events:
        tracker.ingest(event)
    return tracker.records()


def _turn_index_for_message(messages: list[Any], msg_index: int) -> int:
    """Return 0-based user-turn index for the assistant at *msg_index*."""
    if msg_index < 0 or msg_index >= len(messages):
        return 0
    user_count = sum(1 for index in range(msg_index) if messages[index].get("role") == "user")
    if messages[msg_index].get("role") == "assistant":
        return max(0, user_count - 1)
    return user_count


def _slice_events_for_turn(events: list[Any], turn_index: int) -> list[Any]:
    """Return SDK events from user turn *turn_index* until the next user message."""
    user_seen = -1
    start: int | None = None
    end = len(events)
    for index, event in enumerate(events):
        if type(event).__name__ != "MessageEvent":
            continue
        message = getattr(event, "llm_message", None)
        if getattr(message, "role", None) != "user":
            continue
        user_seen += 1
        if user_seen == turn_index:
            start = index
        elif user_seen == turn_index + 1:
            end = index
            break
    if start is None:
        return []
    return events[start:end]


def records_for_assistant_turn(
    session_id: str,
    messages: list[Any],
    msg_index: int,
) -> list[SubagentRunRecord]:
    """Rebuild subagent cards for one persisted assistant message."""
    from services.ai.chat.context_usage import iter_session_events

    events = iter_session_events(session_id)
    if not events:
        return []
    turn_index = _turn_index_for_message(messages, msg_index)
    slice_events = _slice_events_for_turn(events, turn_index)
    return records_for_turn_events(slice_events, session_id=session_id)


__all__ = [
    "SubagentActivityStep",
    "SubagentEventTracker",
    "SubagentKind",
    "SubagentRunRecord",
    "SubagentStatus",
    "delegate_agent_result_from_observation",
    "delegate_agent_results_from_observation",
    "enrich_subagent_records",
    "next_unassigned_subagent_disk_path",
    "record_result_markdown",
    "records_for_assistant_turn",
    "records_for_turn_events",
    "subagent_type_display",
]
