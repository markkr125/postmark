"""Per-session in-memory state for incrementally built collection drafts.

The agent adds bounded batches instead of emitting a whole collection in one
tool argument or replaying a document chunk once per endpoint, so the
accumulating structure lives here rather than in the model's context.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

MAX_REQUESTS_PER_DRAFT = 400
MAX_FOLDER_DEPTH = 5


@dataclass
class DraftRequest:
    """One HTTP request queued for the draft."""

    name: str
    method: str
    url: str
    folder_path: tuple[str, ...] = ()
    headers: list[dict[str, Any]] = field(default_factory=list)
    body: str = ""
    description: str = ""


@dataclass
class CollectionDraft:
    """An in-progress collection assembled across several tool calls."""

    name: str
    source: str = ""
    description: str = ""
    variables: list[dict[str, Any]] = field(default_factory=list)
    folders: list[tuple[str, ...]] = field(default_factory=list)
    requests: list[DraftRequest] = field(default_factory=list)

    def folder_exists(self, path: tuple[str, ...]) -> bool:
        """Return True when *path* was already declared or is the root."""
        return not path or path in self.folders


_lock = threading.Lock()
_drafts: dict[str, CollectionDraft] = {}


def start_draft(session_id: str, draft: CollectionDraft) -> None:
    """Replace any existing draft for *session_id*."""
    with _lock:
        _drafts[session_id] = draft


def get_draft(session_id: str) -> CollectionDraft | None:
    """Return the active draft for *session_id*, if any."""
    with _lock:
        return _drafts.get(session_id)


def clear_draft(session_id: str) -> None:
    """Drop the active draft for *session_id*."""
    with _lock:
        _drafts.pop(session_id, None)


__all__ = [
    "MAX_FOLDER_DEPTH",
    "MAX_REQUESTS_PER_DRAFT",
    "CollectionDraft",
    "DraftRequest",
    "clear_draft",
    "get_draft",
    "start_draft",
]
