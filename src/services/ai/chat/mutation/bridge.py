"""Thread-safe GUI bridge for workspace mutation/execute side effects."""

from __future__ import annotations

import threading
from typing import Any, Literal, NotRequired, TypedDict

_lock = threading.Lock()
_queue: list[MutationBridgeEvent] = []


class OpenTargetDict(TypedDict):
    """Programmatic open target (distinct from clickable postmark:// links)."""

    kind: Literal["request", "collection", "local_script"]
    id: int
    focus: NotRequired[str | None]


class MutationBridgeEvent(TypedDict):
    """One GUI-facing event produced by a mutate/execute tool."""

    type: str
    session_id: NotRequired[str | None]
    entity: NotRequired[str | None]
    action: NotRequired[str | None]
    ids: NotRequired[dict[str, int]]
    open_target: NotRequired[OpenTargetDict | None]
    warnings: NotRequired[list[str]]
    payload: NotRequired[dict[str, Any]]


def enqueue_mutation_event(event: MutationBridgeEvent) -> None:
    """Append a bridge event for the GUI thread to drain."""
    with _lock:
        _queue.append(event)


def drain_mutation_events() -> list[MutationBridgeEvent]:
    """Return and clear all pending bridge events (call on the GUI thread)."""
    with _lock:
        events = list(_queue)
        _queue.clear()
        return events


def clear_mutation_events() -> None:
    """Drop all pending bridge events (tests / abandon)."""
    with _lock:
        _queue.clear()


__all__ = [
    "MutationBridgeEvent",
    "OpenTargetDict",
    "clear_mutation_events",
    "drain_mutation_events",
    "enqueue_mutation_event",
]
