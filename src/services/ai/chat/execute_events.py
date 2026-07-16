"""Parse workspace-execute tool events into clickable chat execute cards."""

from __future__ import annotations

import ast
import re
from typing import Any, Literal, TypedDict

from services.ai.chat.mutation.bridge import MutationBridgeEvent

ExecuteOperation = Literal[
    "send_request",
    "send_draft",
    "replay_history",
    "run_scripts",
    "run_local_script",
    "run_collection",
    "run_iterations",
    "unknown",
]
ExecuteStatus = Literal["completed", "error"]

_EXECUTE_TOOL_NAMES = frozenset({"postmark_workspace_execute"})
_KV_RE = re.compile(r"^([a-z_]+):\s*(.*)$")
_HISTORY_ID_RE = re.compile(r"postmark://history/(\d+)")


class ExecuteRunRecord(TypedDict):
    """One agent execute result shown as a clickable transcript card."""

    id: str
    operation: ExecuteOperation
    label: str
    status: ExecuteStatus
    status_code: int | None
    url: str
    history_entry_id: int | None
    request_id: int | None
    local_script_id: int | None
    collection_id: int | None
    script_phase: str | None


def record_from_bridge_event(event: MutationBridgeEvent) -> ExecuteRunRecord | None:
    """Build a card record from a drained ``executed`` bridge event."""
    if event.get("type") != "executed":
        return None
    ids = event.get("ids") or {}
    payload = event.get("payload") or {}
    operation = str(event.get("action") or "unknown")
    execution_id = str(payload.get("execution_id") or "")
    if not execution_id:
        hist = ids.get("history_entry_id")
        execution_id = f"hist-{hist}" if isinstance(hist, int) else "executed"
    ok = payload.get("ok", True) is not False
    status_raw = payload.get("status_code")
    status_code = int(status_raw) if isinstance(status_raw, int) else None
    summary = str(payload.get("summary") or "").strip()
    url = str(payload.get("url") or "").strip()
    hist_id = ids.get("history_entry_id")
    req_id = ids.get("request_id")
    script_id = ids.get("local_script_id")
    coll_id = ids.get("collection_id")
    script_phase = payload.get("script_phase")
    return ExecuteRunRecord(
        id=execution_id,
        operation=_normalize_operation(operation),
        label=summary or _default_label(operation, url),
        status="completed" if ok else "error",
        status_code=status_code,
        url=url,
        history_entry_id=int(hist_id) if isinstance(hist_id, int) else None,
        request_id=int(req_id) if isinstance(req_id, int) else None,
        local_script_id=int(script_id) if isinstance(script_id, int) else None,
        collection_id=int(coll_id) if isinstance(coll_id, int) else None,
        script_phase=str(script_phase) if script_phase is not None else None,
    )


def records_from_observation_text(
    text: str,
    *,
    tool_call_id: str = "",
) -> ExecuteRunRecord | None:
    """Parse one execute observation body into a card record."""
    fields = _parse_kv_lines(text)
    ok = str(fields.get("ok", "")).strip().lower() == "true"
    operation = _normalize_operation(str(fields.get("operation") or "unknown"))
    execution_id = str(fields.get("execution_id") or tool_call_id or "execute").strip()
    summary = str(fields.get("summary") or "").strip()
    url = str(fields.get("url") or "").strip()
    status_code = _parse_optional_int(fields.get("status_code"))
    history_entry_id = _parse_optional_int(fields.get("history_entry_id"))
    request_id: int | None = None
    local_script_id: int | None = None
    collection_id: int | None = None
    script_phase: str | None = None
    ids_raw = fields.get("ids")
    if ids_raw:
        parsed_ids = _parse_ids_blob(ids_raw)
        if history_entry_id is None:
            history_entry_id = parsed_ids.get("history_entry_id")
        request_id = parsed_ids.get("request_id")
        local_script_id = parsed_ids.get("local_script_id")
        collection_id = parsed_ids.get("collection_id")
    phase_raw = fields.get("script_phase")
    if phase_raw:
        script_phase = str(phase_raw).strip() or None
    if history_entry_id is None:
        for link in _parse_list_blob(fields.get("deep_links", "")):
            match = _HISTORY_ID_RE.search(link)
            if match:
                history_entry_id = int(match.group(1))
                break
    return ExecuteRunRecord(
        id=execution_id or tool_call_id or "execute",
        operation=operation,
        label=summary or _default_label(operation, url),
        status="completed" if ok else "error",
        status_code=status_code,
        url=url,
        history_entry_id=history_entry_id,
        request_id=request_id,
        local_script_id=local_script_id,
        collection_id=collection_id,
        script_phase=script_phase,
    )


def records_for_turn_events(events: list[Any]) -> list[ExecuteRunRecord]:
    """Rebuild execute cards from OpenHands EventLog events for one user turn."""
    records: list[ExecuteRunRecord] = []
    seen: set[str] = set()
    for event in events:
        if not _is_observation_event(event):
            continue
        tool_name = str(getattr(event, "tool_name", "") or "")
        if tool_name not in _EXECUTE_TOOL_NAMES:
            continue
        observation = getattr(event, "observation", None)
        text = _observation_text(observation)
        if not text.strip():
            continue
        tool_call_id = str(getattr(event, "tool_call_id", "") or "")
        record = records_from_observation_text(text, tool_call_id=tool_call_id)
        if record is None or record["id"] in seen:
            continue
        seen.add(record["id"])
        records.append(record)
    return records


def records_for_assistant_turn(
    session_id: str,
    messages: list[Any],
    msg_index: int,
    *,
    events: list[Any] | None = None,
) -> list[ExecuteRunRecord]:
    """Rebuild execute cards for one persisted assistant message."""
    from services.ai.chat.context_usage import iter_session_events

    loaded = events if events is not None else iter_session_events(session_id)
    if not loaded:
        return []
    turn_index = _turn_index_for_message(messages, msg_index)
    slice_events = _slice_events_for_turn(loaded, turn_index)
    return records_for_turn_events(slice_events)


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


def _normalize_operation(value: str) -> ExecuteOperation:
    if value in {
        "send_request",
        "send_draft",
        "replay_history",
        "run_scripts",
        "run_local_script",
        "run_collection",
        "run_iterations",
    }:
        return value  # type: ignore[return-value]
    return "unknown"


def _default_label(operation: str, url: str) -> str:
    if url:
        return f"{operation}: {url}"
    return operation.replace("_", " ").title() or "Execute"


def _parse_optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _parse_kv_lines(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = _KV_RE.match(line.strip())
        if match:
            fields[match.group(1)] = match.group(2).strip()
    return fields


def _parse_ids_blob(raw: str) -> dict[str, int]:
    try:
        parsed = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in parsed.items():
        if isinstance(value, int):
            out[str(key)] = value
    return out


def _parse_list_blob(raw: str) -> list[str]:
    try:
        parsed = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _is_observation_event(event: object) -> bool:
    if type(event).__name__ == "ObservationEvent":
        return True
    try:
        from openhands.sdk.event.llm_convertible.observation import ObservationEvent

        return isinstance(event, ObservationEvent)
    except Exception:
        return False


def _observation_text(observation: object) -> str:
    if observation is None:
        return ""
    text = getattr(observation, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    content = getattr(observation, "content", None)
    if isinstance(content, str):
        return content
    return str(observation or "")


__all__ = [
    "ExecuteOperation",
    "ExecuteRunRecord",
    "ExecuteStatus",
    "record_from_bridge_event",
    "records_for_assistant_turn",
    "records_for_turn_events",
    "records_from_observation_text",
]
