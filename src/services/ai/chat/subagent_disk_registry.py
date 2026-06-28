"""Maps delegate spawn ids to OpenHands subagent persistence directories."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from pathlib import Path

from database.data_paths import session_disk_dir

_lock = threading.Lock()
_by_session: dict[str, dict[str, str]] = {}


def register_subagent_disk_path(session_id: str, agent_id: str, disk_path: str) -> None:
    """Remember *disk_path* for a delegate spawn id within *session_id*."""
    if not session_id or not agent_id or not disk_path:
        return
    with _lock:
        _by_session.setdefault(session_id, {})[agent_id] = disk_path


def lookup_subagent_disk_path(session_id: str, agent_id: str) -> str | None:
    """Return a registered disk path for *agent_id*, or ``None``."""
    with _lock:
        path = _by_session.get(session_id, {}).get(agent_id)
    if path and Path(path).is_dir():
        return path
    return None


def clear_subagent_disk_registry(session_id: str | None = None) -> None:
    """Drop registry entries for one session or all sessions (tests)."""
    with _lock:
        if session_id is None:
            _by_session.clear()
        else:
            _by_session.pop(session_id, None)


def session_subagents_root(session_id: str) -> Path:
    """Return ``<session_disk>/subagents`` where OpenHands stores delegate runs."""
    return session_disk_dir(session_id) / "subagents"


def _normalize_task(text: str) -> str:
    return " ".join(text.split())


def next_unassigned_subagent_disk_path(
    session_id: str,
    *,
    turn_started_at: float,
    assigned: set[str],
) -> str | None:
    """Return the oldest unassigned subagent folder for *session_id* in this turn."""
    root = session_subagents_root(session_id)
    if not root.is_dir():
        return None
    candidates = sorted(
        (
            p
            for p in root.iterdir()
            if p.is_dir() and str(p) not in assigned and p.stat().st_mtime >= turn_started_at - 1.0
        ),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        return None
    return str(candidates[0])


def match_disk_path_by_task_prompt(
    session_id: str,
    task_prompt: str,
    *,
    turn_started_at: float,
    assigned: set[str],
) -> str | None:
    """Match an unassigned subagent folder by its first user message text."""
    cleaned = task_prompt.strip()
    if not cleaned:
        return None
    target = _normalize_task(cleaned)
    root = session_subagents_root(session_id)
    if not root.is_dir():
        return None

    from services.ai.chat.subagent_transcript import load_subagent_transcript_view

    candidates = sorted(
        (
            p
            for p in root.iterdir()
            if p.is_dir() and str(p) not in assigned and p.stat().st_mtime >= turn_started_at - 1.0
        ),
        key=lambda p: p.stat().st_mtime,
    )
    for path in candidates:
        view = load_subagent_transcript_view(str(path), fallback_task_prompt="")
        prompt = view.get("task_prompt", "")
        if prompt and _normalize_task(prompt) == target:
            return str(path)
    return None


def resolve_subagent_disk_path(
    session_id: str,
    record: Mapping[str, object],
    *,
    turn_started_at: float,
    assigned: set[str],
) -> str | None:
    """Resolve a subagent folder: registry, task match, then mtime fallback."""
    if not session_id:
        return None

    agent_id = str(record["id"])
    registered = lookup_subagent_disk_path(session_id, agent_id)
    if registered and str(registered) not in assigned:
        return registered

    task_prompt = record.get("task_prompt", "")
    if isinstance(task_prompt, str) and task_prompt:
        matched = match_disk_path_by_task_prompt(
            session_id,
            task_prompt,
            turn_started_at=turn_started_at,
            assigned=assigned,
        )
        if matched:
            return matched

    return next_unassigned_subagent_disk_path(
        session_id,
        turn_started_at=turn_started_at,
        assigned=assigned,
    )


__all__ = [
    "clear_subagent_disk_registry",
    "lookup_subagent_disk_path",
    "match_disk_path_by_task_prompt",
    "next_unassigned_subagent_disk_path",
    "register_subagent_disk_path",
    "resolve_subagent_disk_path",
    "session_subagents_root",
]
