"""Load read-only preview text and activity steps from a subagent conversation."""

from __future__ import annotations

import logging
from pathlib import Path

from services.ai.chat.subagent_events import SubagentActivityStep, SubagentRunRecord

logger = logging.getLogger(__name__)


def steps_for_subagent_record(record: SubagentRunRecord) -> list[SubagentActivityStep]:
    """Build Cursor-style activity steps for one subagent card."""
    disk = record.get("disk_path")
    if disk:
        disk_steps = load_subagent_activity_steps(disk)
        if disk_steps:
            return disk_steps

    preview = record.get("result_preview", "")
    status = record["status"]
    kind = record["kind"]

    if kind == "wiki":
        steps: list[SubagentActivityStep] = [
            {
                "id": f"{record['id']}:search",
                "icon": "magnifying-glass",
                "summary": record["label"],
            }
        ]
        if preview and status in ("completed", "error"):
            steps.append(
                {
                    "id": f"{record['id']}:result",
                    "icon": "article",
                    "summary": "Read tool output",
                    "detail": preview,
                }
            )
        return steps

    if status == "warming":
        return [{"id": f"{record['id']}:warm", "icon": "circle-notch", "summary": "Starting…"}]
    if status == "running":
        return [{"id": f"{record['id']}:run", "icon": "circle-notch", "summary": "Working…"}]
    if preview:
        return [
            {
                "id": f"{record['id']}:result",
                "icon": "article",
                "summary": "Read tool output",
                "detail": preview,
            }
        ]
    return [{"id": f"{record['id']}:done", "icon": "check", "summary": "Completed"}]


def load_subagent_activity_steps(disk_path: str, *, limit: int = 16) -> list[SubagentActivityStep]:
    """Return Cursor-style step rows parsed from subagent SDK events on disk."""
    root = Path(disk_path)
    if not root.is_dir():
        return []
    try:
        from openhands.sdk.conversation.event_store import EventLog
        from openhands.sdk.io.local import LocalFileStore
    except ImportError:
        return []

    try:
        store = LocalFileStore(root=str(root))
        log = EventLog(store)
        steps: list[SubagentActivityStep] = []
        search_count = 0
        for index in range(len(log)):
            if len(steps) >= limit:
                break
            event = log[index]
            name = type(event).__name__
            if name == "MessageEvent":
                message = getattr(event, "llm_message", None)
                role = getattr(message, "role", None)
                content = getattr(message, "content", None)
                thinking = getattr(event, "reasoning_content", None)
                if isinstance(thinking, str) and thinking.strip():
                    steps.append(
                        {
                            "id": f"thought:{index}",
                            "icon": "lightbulb",
                            "summary": "Thought briefly",
                        }
                    )
                    continue
                if role == "assistant" and isinstance(content, list):
                    text_parts = [
                        getattr(block, "text", "")
                        for block in content
                        if isinstance(getattr(block, "text", None), str)
                    ]
                    joined = "\n".join(part.strip() for part in text_parts if part.strip())
                    if joined:
                        steps.append(
                            {
                                "id": f"assistant:{index}",
                                "icon": "chat-circle",
                                "summary": "Responded",
                                "detail": _clip(joined, 1200),
                            }
                        )
            elif name == "ActionEvent":
                tool_name = str(getattr(event, "tool_name", "") or "")
                action = getattr(event, "action", None)
                if tool_name == "postmark_wiki_query" and action is not None:
                    query = str(getattr(action, "query", "") or "").strip()
                    search_count += 1
                    steps.append(
                        {
                            "id": f"search:{index}",
                            "icon": "magnifying-glass",
                            "summary": f'Searched wiki for "{_clip(query, 80)}"',
                        }
                    )
            elif name == "ObservationEvent":
                observation = getattr(event, "observation", None)
                text = _observation_text(observation)
                if text:
                    steps.append(
                        {
                            "id": f"obs:{index}",
                            "icon": "article",
                            "summary": "Read tool output",
                            "detail": _clip(text, 1600),
                        }
                    )
        if search_count > 1:
            steps = _collapse_search_steps(steps, search_count)
        return steps
    except Exception:
        logger.debug("Failed to load subagent steps from %s", disk_path, exc_info=True)
        return []


def load_subagent_transcript_preview(disk_path: str, *, limit: int = 4000) -> str:
    """Return a plain-text preview from subagent SDK events on disk."""
    root = Path(disk_path)
    if not root.is_dir():
        return ""
    try:
        from openhands.sdk.conversation.event_store import EventLog
        from openhands.sdk.io.local import LocalFileStore
    except ImportError:
        return ""

    try:
        store = LocalFileStore(root=str(root))
        log = EventLog(store)
        parts: list[str] = []
        for index in range(len(log)):
            event = log[index]
            name = type(event).__name__
            if name == "MessageEvent":
                role = getattr(getattr(event, "llm_message", None), "role", None)
                content = getattr(getattr(event, "llm_message", None), "content", None)
                if isinstance(content, list):
                    for block in content:
                        text = getattr(block, "text", None)
                        if isinstance(text, str) and text.strip():
                            parts.append(f"{role or 'message'}: {text.strip()}")
            elif name == "ObservationEvent":
                observation = getattr(event, "observation", None)
                text = _observation_text(observation)
                if text:
                    parts.append(text.strip())
        body = "\n\n".join(parts).strip()
        if len(body) > limit:
            return body[: limit - 1].rstrip() + "…"
        return body
    except Exception:
        logger.debug("Failed to load subagent transcript from %s", disk_path, exc_info=True)
        return ""


def _observation_text(observation: object | None) -> str:
    if observation is None:
        return ""
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


def _clip(text: str, limit: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _collapse_search_steps(
    steps: list[SubagentActivityStep], search_count: int
) -> list[SubagentActivityStep]:
    """Replace individual search rows with one aggregate line when possible."""
    if search_count < 2:
        return steps
    collapsed: list[SubagentActivityStep] = []
    search_inserted = False
    for step in steps:
        if step.get("icon") == "magnifying-glass" and not search_inserted:
            collapsed.append(
                {
                    "id": "search:aggregate",
                    "icon": "magnifying-glass",
                    "summary": f"Explored {search_count} searches",
                }
            )
            search_inserted = True
            continue
        if step.get("icon") == "magnifying-glass":
            continue
        collapsed.append(step)
    return collapsed


__all__ = [
    "load_subagent_activity_steps",
    "load_subagent_transcript_preview",
    "steps_for_subagent_record",
]
