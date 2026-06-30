"""Load read-only preview text and activity steps from a subagent conversation."""

from __future__ import annotations

import logging
from pathlib import Path
from collections.abc import Sequence
from typing import TypedDict

from services.ai.chat.subagent_events import SubagentActivityStep, SubagentRunRecord

logger = logging.getLogger(__name__)


class SubagentTranscriptView(TypedDict):
    """Task prompt and assistant markdown extracted from a subagent EventLog."""

    task_prompt: str
    answer_markdown: str
    thinking_markdown: str
    event_count: int


class SubagentDiskSnapshot(TypedDict):
    """Transcript view and activity steps from one EventLog read."""

    view: SubagentTranscriptView
    steps: list[SubagentActivityStep]


def _fallback_steps_for_record(record: SubagentRunRecord) -> list[SubagentActivityStep]:
    """Build activity steps from record metadata when disk is missing or empty."""
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


def steps_for_subagent_record(record: SubagentRunRecord) -> list[SubagentActivityStep]:
    """Build Cursor-style activity steps for one subagent card."""
    disk = record.get("disk_path")
    if disk:
        disk_steps = load_subagent_activity_steps(disk)
        if disk_steps:
            return disk_steps

    return _fallback_steps_for_record(record)


def load_subagent_transcript_view(
    disk_path: str,
    *,
    fallback_task_prompt: str = "",
) -> SubagentTranscriptView:
    """Return the delegated task prompt and assistant markdown from disk events."""
    events = _read_subagent_events(disk_path)
    if events is None:
        return SubagentTranscriptView(
            task_prompt=fallback_task_prompt,
            answer_markdown="",
            thinking_markdown="",
            event_count=0,
        )
    return parse_subagent_transcript_events(
        events,
        fallback_task_prompt=fallback_task_prompt,
    )


def load_subagent_disk_snapshot(
    disk_path: str,
    *,
    fallback_task_prompt: str = "",
    step_limit: int = 16,
) -> SubagentDiskSnapshot:
    """Return transcript view and activity steps from a single EventLog read."""
    events = _read_subagent_events(disk_path)
    if events is None:
        empty = SubagentTranscriptView(
            task_prompt=fallback_task_prompt,
            answer_markdown="",
            thinking_markdown="",
            event_count=0,
        )
        return SubagentDiskSnapshot(view=empty, steps=[])
    return SubagentDiskSnapshot(
        view=parse_subagent_transcript_events(
            events,
            fallback_task_prompt=fallback_task_prompt,
        ),
        steps=parse_subagent_activity_steps(events, limit=step_limit),
    )


def _read_subagent_events(disk_path: str) -> list[object] | None:
    """Load all SDK events from a subagent conversation directory."""
    root = Path(disk_path)
    if not root.is_dir():
        return None
    try:
        from openhands.sdk.conversation.event_store import EventLog
        from openhands.sdk.io.local import LocalFileStore
    except ImportError:
        return None

    try:
        store = LocalFileStore(root=str(root))
        log = EventLog(store)
        return [log[index] for index in range(len(log))]
    except Exception:
        logger.debug("Failed to read subagent events from %s", disk_path, exc_info=True)
        return None


def parse_subagent_transcript_events(
    events: Sequence[object],
    *,
    fallback_task_prompt: str = "",
) -> SubagentTranscriptView:
    """Parse SDK events into task prompt and assistant markdown (testable without disk)."""
    task_prompt = fallback_task_prompt.strip()
    assistant_parts: list[str] = []
    thinking_parts: list[str] = []

    for event in events:
        name = type(event).__name__
        if name != "MessageEvent":
            continue
        message = getattr(event, "llm_message", None)
        role = getattr(message, "role", None)
        thinking = getattr(event, "reasoning_content", None)
        if isinstance(thinking, str) and thinking.strip():
            thinking_parts.append(thinking.strip())
        text = _message_text(message)
        if not text:
            continue
        if role == "user" and not task_prompt:
            task_prompt = text
        elif role == "assistant":
            assistant_parts.append(text)

    answer = assistant_parts[-1] if assistant_parts else ""
    if not answer and len(assistant_parts) > 1:
        answer = "\n\n".join(assistant_parts)

    return SubagentTranscriptView(
        task_prompt=task_prompt,
        answer_markdown=answer.strip(),
        thinking_markdown="\n\n".join(thinking_parts).strip(),
        event_count=len(events),
    )


def load_subagent_activity_steps(disk_path: str, *, limit: int = 16) -> list[SubagentActivityStep]:
    """Return Cursor-style step rows parsed from subagent SDK events on disk."""
    events = _read_subagent_events(disk_path)
    if events is None:
        return []
    return parse_subagent_activity_steps(events, limit=limit)


def parse_subagent_activity_steps(
    events: Sequence[object],
    *,
    limit: int = 16,
) -> list[SubagentActivityStep]:
    """Parse SDK events into Cursor-style activity rows (testable without disk)."""
    steps: list[SubagentActivityStep] = []
    search_count = 0
    for index, event in enumerate(events):
        if len(steps) >= limit:
            break
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
                        "detail": _clip(thinking.strip(), 1200),
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


def load_subagent_transcript_preview(disk_path: str, *, limit: int = 4000) -> str:
    """Return a plain-text preview from subagent SDK events on disk."""
    view = load_subagent_transcript_view(disk_path)
    body = view["answer_markdown"]
    if len(body) > limit:
        return body[: limit - 1].rstrip() + "…"
    return body


def _message_text(message: object | None) -> str:
    """Extract plaintext from an SDK llm message object."""
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        if parts:
            return "\n".join(parts)
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
    "SubagentDiskSnapshot",
    "SubagentTranscriptView",
    "load_subagent_activity_steps",
    "load_subagent_disk_snapshot",
    "load_subagent_transcript_preview",
    "load_subagent_transcript_view",
    "parse_subagent_activity_steps",
    "parse_subagent_transcript_events",
    "steps_for_subagent_record",
]
