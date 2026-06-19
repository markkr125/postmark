"""AI chat session service — SQLite index + OpenHands Conversation bridge."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict, cast

from database.data_paths import session_disk_dir, user_ai_conversations_root
from database.models.ai_chat.ai_chat_query_repository import (
    allocate_fork_session_title,
    get_session_by_id,
)
from database.models.ai_chat.ai_chat_query_repository import (
    get_session_with_messages as repo_get_session_with_messages,
)
from database.models.ai_chat.ai_chat_query_repository import (
    list_messages_after as repo_list_messages_after,
)
from database.models.ai_chat.ai_chat_query_repository import (
    list_messages_before as repo_list_messages_before,
)
from database.models.ai_chat.ai_chat_query_repository import (
    list_messages_tail as repo_list_messages_tail,
)
from database.models.ai_chat.ai_chat_query_repository import list_sessions as repo_list_sessions
from database.models.ai_chat.ai_chat_query_repository import search_messages as repo_search_messages
from database.models.ai_chat.ai_chat_repository import (
    DEFAULT_AGENT_ID,
    append_message,
    archive_session,
    bulk_append_messages,
    count_messages_after as repo_count_messages_after,
    create_session,
    delete_message as repo_delete_message,
    delete_messages_after as repo_delete_messages_after,
    delete_session,
    delete_session_index,
    get_last_assistant_usage_cumulative,
    list_messages,
    list_messages_up_to,
    rename_session,
    touch_session,
    update_session_composer_settings,
    update_user_message as repo_update_user_message,
)
from services.ai.ai_config import AiConfig, AiModelEntry
from services.ai.ai_logging import log as ai_log
from services.ai.chat.agent_registry import DEFAULT_MAX_ITERATIONS, get_agent_def
from services.ai.chat.compaction import (
    CHAT_CONDENSER_MAX_EVENTS,
    CHAT_CONDENSER_MINIMUM_PROGRESS,
    condenser_max_tokens,
)
from services.ai.chat.response_text import extract_final_text as _extract_final_text
from services.ai.chat.tool_registry import resolve_tools
from services.ai.chat.transcript_window import (
    INITIAL_TAIL_TURNS,
    NEWER_PAGE_TURNS,
    OLDER_PAGE_TURNS,
    message_limit_for_turns,
)
from services.ai.llm_service import AiLlmService, resolve_llm_base_url
from services.ai.provider_catalog import effective_run_context_tokens
from services.ai.reasoning_effort import _is_ollama_model

if TYPE_CHECKING:
    from openhands.sdk import BaseConversation
    from openhands.sdk.event.base import Event
    from openhands.sdk.llm.streaming import LLMStreamChunk
    from services.ai.chat.context_usage import ContextUsageSdkMetrics
    from services.ai.chat.message_usage import SessionSpendBreakdown

# Attachments are explicitly deferred for v1.
_ATTACHMENTS_DEFERRED = True

_TITLE_PREVIEW_LEN = 48


class AiChatSessionDict(TypedDict):
    """Serializable AI chat session row."""

    id: str
    title: str
    model_id: str | None
    mode: str
    agent_id: str
    created_at: str
    updated_at: str
    last_preview: str | None
    archived: bool


class AiChatMessageDict(TypedDict):
    """Serializable AI chat message row."""

    id: int
    session_id: str
    role: str
    content: str
    thinking: NotRequired[str]
    thinking_duration_seconds: NotRequired[int | None]
    model_id: NotRequired[str | None]
    model_label: NotRequired[str | None]
    prompt_tokens: NotRequired[int | None]
    completion_tokens: NotRequired[int | None]
    reasoning_tokens: NotRequired[int | None]
    cost_usd: NotRequired[float | None]
    send_model_id: NotRequired[str | None]
    send_mode: NotRequired[str | None]
    send_agent_id: NotRequired[str | None]
    send_reasoning_effort: NotRequired[str | None]
    send_thinking_enabled: NotRequired[str | None]
    send_run_context_tokens: NotRequired[int | None]
    created_at: str


class UserMessageSendSnapshot(TypedDict, total=False):
    """Per-send composer settings stored on user message rows."""

    send_model_id: str | None
    send_mode: str
    send_agent_id: str
    send_reasoning_effort: str | None
    send_thinking_enabled: str | None
    send_run_context_tokens: int | None


class ComposerRunContext(TypedDict, total=False):
    """Per-send composer settings passed from the UI."""

    run_context_tokens: int | None
    thinking_enabled: str | None
    reasoning_effort: str | None


class AiChatUserForkResult(TypedDict):
    """Fork from a user message: new session plus composer draft text."""

    session: AiChatSessionDict
    composer_draft: str


class AiChatSessionLoadDict(TypedDict):
    """Session row plus transcript messages from a single read."""

    session: AiChatSessionDict
    messages: list[AiChatMessageDict]


class AiChatTranscriptPageDict(TypedDict):
    """One virtualized transcript page of messages."""

    messages: list[AiChatMessageDict]
    has_older: bool
    has_newer: bool
    oldest_id: int | None
    newest_id: int | None


class AiChatSessionTailLoadDict(TypedDict):
    """Session metadata plus the initial tail transcript page."""

    session: AiChatSessionDict
    page: AiChatTranscriptPageDict


@contextmanager
def _allow_short_context_when_needed(entry: AiModelEntry):
    """Enable short context windows for small local models during chat runs."""
    key = "ALLOW_SHORT_CONTEXT_WINDOWS"
    prev = os.environ.get(key)
    context = entry.get("context")
    if _is_ollama_model(entry) or (context is not None and context < 16_000):
        os.environ[key] = "true"
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev


def _fallback_title(text: str) -> str:
    """Truncate the first user message for a session title."""
    stripped = text.strip().replace("\n", " ")
    if len(stripped) <= _TITLE_PREVIEW_LEN:
        return stripped or "New chat"
    return stripped[: _TITLE_PREVIEW_LEN - 1] + "…"


class AiChatSessionService:
    """Bridge between the UI, SQLite index, and OpenHands Conversation."""

    @staticmethod
    def new_session(
        entry: AiModelEntry,
        mode: str,
        *,
        first_message: str | None = None,
        agent_id: str = DEFAULT_AGENT_ID,
    ) -> AiChatSessionDict:
        """Create a new session row (SDK conversation is lazy)."""
        session_id = str(uuid.uuid4())
        title = _fallback_title(first_message) if first_message else "New chat"
        row = create_session(
            session_id=session_id,
            title=title,
            model_id=entry["id"],
            mode=mode,
            agent_id=agent_id,
        )
        return AiChatSessionService._cast_session(row)

    @staticmethod
    def list_sessions(search: str | None = None) -> list[AiChatSessionDict]:
        """List sessions, optionally filtered by title substring."""
        rows = repo_list_sessions(search=search, include_archived=False)
        return [AiChatSessionService._cast_session(r) for r in rows]

    @staticmethod
    def search_sessions(query: str) -> list[AiChatSessionDict]:
        """Search sessions by title or message content."""
        rows = repo_search_messages(query)
        return [AiChatSessionService._cast_session(r) for r in rows]

    @staticmethod
    def get_session(session_id: str) -> AiChatSessionDict | None:
        """Return one session or ``None``."""
        row = get_session_by_id(session_id)
        if row is None:
            return None
        return AiChatSessionService._cast_session(row)

    @staticmethod
    def get_messages(session_id: str) -> list[AiChatMessageDict]:
        """Return transcript messages for repaint."""
        return [AiChatSessionService._cast_message(m) for m in list_messages(session_id)]

    @staticmethod
    def session_spend_breakdown(
        session_id: str,
        *,
        models: list[AiModelEntry] | None = None,
    ) -> SessionSpendBreakdown:
        """Return per-provider session spend rollup from stored assistant turns."""
        from services.ai.chat.message_usage import session_spend_breakdown

        session_row = AiChatSessionService.get_session(session_id)
        session_model_id = session_row.get("model_id") if session_row is not None else None
        messages = AiChatSessionService.get_messages(session_id)
        return session_spend_breakdown(
            messages,
            session_model_id=session_model_id,
            models=models,
        )

    @staticmethod
    def get_session_with_messages(session_id: str) -> AiChatSessionLoadDict | None:
        """Return session metadata and messages from one indexed read."""
        session_row, message_rows = repo_get_session_with_messages(session_id)
        if session_row is None:
            return None
        return AiChatSessionLoadDict(
            session=AiChatSessionService._cast_session(session_row),
            messages=[AiChatSessionService._cast_message(m) for m in message_rows],
        )

    @staticmethod
    def _page_from_messages(
        messages: list[AiChatMessageDict],
        *,
        has_older: bool,
        has_newer: bool,
    ) -> AiChatTranscriptPageDict:
        """Build a transcript page dict from ordered message rows."""
        oldest_id = messages[0]["id"] if messages else None
        newest_id = messages[-1]["id"] if messages else None
        return AiChatTranscriptPageDict(
            messages=messages,
            has_older=has_older,
            has_newer=has_newer,
            oldest_id=oldest_id,
            newest_id=newest_id,
        )

    @staticmethod
    def _tail_turn_slice(
        raw_messages: list[dict[str, Any]],
        *,
        tail_turns: int,
        has_older_db: bool,
    ) -> tuple[list[AiChatMessageDict], bool]:
        """Trim a raw tail fetch to complete trailing user turns."""
        if not raw_messages:
            return [], False
        cast_messages = [AiChatSessionService._cast_message(m) for m in raw_messages]
        user_indices = [
            index for index, message in enumerate(cast_messages) if message["role"] == "user"
        ]
        if len(user_indices) <= tail_turns:
            return cast_messages, has_older_db
        start_index = user_indices[-tail_turns]
        return cast_messages[start_index:], True

    @staticmethod
    def _older_turn_slice(
        raw_messages: list[dict[str, Any]],
        *,
        page_turns: int,
        has_older_db: bool,
    ) -> tuple[list[AiChatMessageDict], bool]:
        """Trim a before-page fetch to the newest complete turns in the batch."""
        if not raw_messages:
            return [], False
        cast_messages = [AiChatSessionService._cast_message(m) for m in raw_messages]
        user_indices = [
            index for index, message in enumerate(cast_messages) if message["role"] == "user"
        ]
        if len(user_indices) <= page_turns:
            return cast_messages, has_older_db
        start_index = user_indices[-page_turns]
        return cast_messages[start_index:], True

    @staticmethod
    def _newer_turn_slice(
        raw_messages: list[dict[str, Any]],
        *,
        page_turns: int,
        has_newer_db: bool,
    ) -> tuple[list[AiChatMessageDict], bool]:
        """Trim an after-page fetch to the oldest complete turns in the batch."""
        if not raw_messages:
            return [], False
        cast_messages = [AiChatSessionService._cast_message(m) for m in raw_messages]
        user_indices = [
            index for index, message in enumerate(cast_messages) if message["role"] == "user"
        ]
        if len(user_indices) <= page_turns:
            has_newer = has_newer_db
            return cast_messages, has_newer
        next_start = user_indices[page_turns]
        return cast_messages[:next_start], True

    @staticmethod
    def get_session_tail(
        session_id: str,
        *,
        tail_turns: int = INITIAL_TAIL_TURNS,
    ) -> AiChatSessionTailLoadDict | None:
        """Return session metadata and the latest *tail_turns* user turns."""
        session_row = get_session_by_id(session_id)
        if session_row is None:
            return None
        raw_limit = message_limit_for_turns(tail_turns + 1)
        raw_messages, has_older_db = repo_list_messages_tail(session_id, limit=raw_limit)
        messages, has_older = AiChatSessionService._tail_turn_slice(
            raw_messages,
            tail_turns=tail_turns,
            has_older_db=has_older_db,
        )
        page = AiChatSessionService._page_from_messages(
            messages,
            has_older=has_older,
            has_newer=False,
        )
        return AiChatSessionTailLoadDict(
            session=AiChatSessionService._cast_session(session_row),
            page=page,
        )

    @staticmethod
    def load_older_messages(
        session_id: str,
        *,
        before_id: int,
        page_turns: int = OLDER_PAGE_TURNS,
    ) -> AiChatTranscriptPageDict:
        """Fetch the preceding *page_turns* user turns before *before_id*."""
        raw_limit = message_limit_for_turns(page_turns + 1)
        raw_messages, has_older_db = repo_list_messages_before(
            session_id,
            before_id=before_id,
            limit=raw_limit,
        )
        messages, has_older = AiChatSessionService._older_turn_slice(
            raw_messages,
            page_turns=page_turns,
            has_older_db=has_older_db,
        )
        return AiChatSessionService._page_from_messages(
            messages,
            has_older=has_older,
            has_newer=True,
        )

    @staticmethod
    def load_newer_messages(
        session_id: str,
        *,
        after_id: int,
        page_turns: int = NEWER_PAGE_TURNS,
    ) -> AiChatTranscriptPageDict:
        """Fetch the next *page_turns* user turns after *after_id*."""
        raw_limit = message_limit_for_turns(page_turns + 1)
        raw_messages, has_newer_db = repo_list_messages_after(
            session_id,
            after_id=after_id,
            limit=raw_limit,
        )
        messages, has_newer = AiChatSessionService._newer_turn_slice(
            raw_messages,
            page_turns=page_turns,
            has_newer_db=has_newer_db,
        )
        return AiChatSessionService._page_from_messages(
            messages,
            has_older=True,
            has_newer=has_newer,
        )

    @staticmethod
    def resolve_restore_session_id() -> str | None:
        """Return the session id to load on startup, or ``None`` for an empty panel.

        Uses the persisted active session when it still exists. When that row was
        deleted, falls back to the most recently updated session. An empty stored
        id (e.g. after **New chat**) leaves the panel empty.
        """
        stored = AiConfig.get_chat_session_id()
        if not stored:
            return None
        session = AiChatSessionService.get_session(stored)
        if session is not None and not session.get("archived"):
            return stored
        sessions = AiChatSessionService.list_sessions()
        return sessions[0]["id"] if sessions else None

    @staticmethod
    def rename_session(session_id: str, title: str) -> AiChatSessionDict | None:
        """Rename a session."""
        row = rename_session(session_id, title)
        if row is None:
            return None
        return AiChatSessionService._cast_session(row)

    @staticmethod
    def delete_session(session_id: str) -> bool:
        """Delete session rows and SDK disk state."""
        return delete_session(session_id)

    @staticmethod
    def archive_session(session_id: str, *, archived: bool = True) -> AiChatSessionDict | None:
        """Archive or unarchive a session."""
        row = archive_session(session_id, archived=archived)
        if row is None:
            return None
        return AiChatSessionService._cast_session(row)

    @staticmethod
    def count_messages_after(session_id: str, message_id: int) -> int:
        """Return how many transcript rows exist after *message_id*."""
        return repo_count_messages_after(session_id, message_id)

    @staticmethod
    def infer_send_snapshot_fallback(
        session_id: str,
        user_message_id: int,
        *,
        extra_entries: list[AiModelEntry] | None = None,
    ) -> UserMessageSendSnapshot:
        """Build a send snapshot for legacy user rows missing per-send columns."""
        messages = list_messages(session_id)
        user_row = next((m for m in messages if m["id"] == user_message_id), None)
        if user_row is not None:
            stored = AiChatSessionService.send_snapshot_from_message(
                AiChatSessionService._cast_message(user_row)
            )
            if stored.get("send_model_id") or stored.get("send_mode"):
                return stored
        session_row = get_session_by_id(session_id)
        send_model_id: str | None = None
        for msg in messages:
            if msg["id"] > user_message_id and msg.get("role") == "assistant":
                mid = msg.get("model_id")
                if isinstance(mid, str) and mid:
                    send_model_id = mid
                break
        if not send_model_id and session_row is not None:
            mid = session_row.get("model_id")
            if isinstance(mid, str) and mid:
                send_model_id = mid
        mode = "agent"
        agent_id = DEFAULT_AGENT_ID
        if session_row is not None:
            mode = str(session_row.get("mode") or "agent")
            agent_id = str(session_row.get("agent_id") or DEFAULT_AGENT_ID)
        thinking: str | None = None
        models = extra_entries if extra_entries is not None else AiConfig.get_models()
        if send_model_id:
            for entry in models:
                if entry["id"] == send_model_id and entry.get("thinking"):
                    stored_thinking = entry.get("thinking_enabled")
                    if isinstance(stored_thinking, str) and stored_thinking.strip().lower() in (
                        "on",
                        "off",
                    ):
                        thinking = stored_thinking.strip().lower()
                    else:
                        thinking = "on"
                    break
        return UserMessageSendSnapshot(
            send_model_id=send_model_id,
            send_mode=mode,
            send_agent_id=agent_id,
            send_reasoning_effort=None,
            send_thinking_enabled=thinking,
            send_run_context_tokens=None,
        )

    @staticmethod
    def send_snapshot_from_message(row: AiChatMessageDict) -> UserMessageSendSnapshot:
        """Return stored send snapshot from a user message dict."""
        if row.get("send_model_id") or row.get("send_mode"):
            return UserMessageSendSnapshot(
                send_model_id=row.get("send_model_id"),
                send_mode=str(row.get("send_mode") or "agent"),
                send_agent_id=str(row.get("send_agent_id") or DEFAULT_AGENT_ID),
                send_reasoning_effort=row.get("send_reasoning_effort"),
                send_thinking_enabled=row.get("send_thinking_enabled"),
                send_run_context_tokens=row.get("send_run_context_tokens"),
            )
        return UserMessageSendSnapshot()

    @staticmethod
    def record_user_message(
        session_id: str,
        content: str,
        *,
        send_snapshot: UserMessageSendSnapshot | None = None,
    ) -> AiChatMessageDict:
        """Persist a user message and touch the session preview."""
        preview = content.strip().replace("\n", " ")[:_TITLE_PREVIEW_LEN]
        touch_session(session_id, last_preview=preview)
        snap = send_snapshot or {}
        row = append_message(
            session_id=session_id,
            role="user",
            content=content,
            send_model_id=snap.get("send_model_id"),
            send_mode=snap.get("send_mode"),
            send_agent_id=snap.get("send_agent_id"),
            send_reasoning_effort=snap.get("send_reasoning_effort"),
            send_thinking_enabled=snap.get("send_thinking_enabled"),
            send_run_context_tokens=snap.get("send_run_context_tokens"),
        )
        return AiChatSessionService._cast_message(row)

    @staticmethod
    def _rewind_session_disk(source_session_id: str, prefix_last_message_id: int | None) -> None:
        """Replace SDK disk state with the prefix through *prefix_last_message_id*."""
        target_disk = session_disk_dir(source_session_id)
        if prefix_last_message_id is None:
            if target_disk.is_dir():
                shutil.rmtree(target_disk)
            return
        forked = AiChatSessionService.fork_session_at_message(
            source_session_id,
            prefix_last_message_id,
        )
        if forked is None:
            return
        forked_id = forked["id"]
        forked_disk = session_disk_dir(forked_id)
        if target_disk.is_dir():
            shutil.rmtree(target_disk)
        if forked_disk.is_dir():
            shutil.copytree(forked_disk, target_disk)
            AiChatSessionService._rewrite_forked_disk_conversation_id(source_session_id)
        delete_session_index(forked_id)
        if forked_disk.is_dir():
            shutil.rmtree(forked_disk, ignore_errors=True)

    @staticmethod
    def edit_user_message_and_rewind(
        session_id: str,
        user_message_id: int,
        new_content: str,
        send_snapshot: UserMessageSendSnapshot,
    ) -> bool:
        """Update a user row, truncate later messages, and rewind SDK disk."""
        messages = list_messages(session_id)
        user_row = next((m for m in messages if m["id"] == user_message_id), None)
        if user_row is None or user_row.get("role") != "user":
            return False
        prior = [m for m in messages if m["id"] < user_message_id]
        prefix_last_id = prior[-1]["id"] if prior else None
        updated = repo_update_user_message(
            user_message_id,
            content=new_content,
            send_model_id=send_snapshot.get("send_model_id"),
            send_mode=send_snapshot.get("send_mode"),
            send_agent_id=send_snapshot.get("send_agent_id"),
            send_reasoning_effort=send_snapshot.get("send_reasoning_effort"),
            send_thinking_enabled=send_snapshot.get("send_thinking_enabled"),
            send_run_context_tokens=send_snapshot.get("send_run_context_tokens"),
        )
        if updated is None:
            return False
        repo_delete_messages_after(session_id, user_message_id)
        AiChatSessionService._rewind_session_disk(session_id, prefix_last_id)
        preview = new_content.strip().replace("\n", " ")[:_TITLE_PREVIEW_LEN]
        touch_session(session_id, last_preview=preview or None)
        update_session_composer_settings(
            session_id,
            model_id=send_snapshot.get("send_model_id"),
            mode=send_snapshot.get("send_mode"),
            agent_id=send_snapshot.get("send_agent_id"),
        )
        return True

    @staticmethod
    def delete_message(session_id: str, message_id: int) -> bool:
        """Delete one message row and refresh the session preview from remaining rows."""
        deleted_session_id = repo_delete_message(message_id)
        if deleted_session_id is None or deleted_session_id != session_id:
            return False
        remaining = list_messages(session_id)
        if remaining:
            last = remaining[-1]
            preview = (last.get("content") or last.get("thinking") or "").strip()
            preview = preview.replace("\n", " ")[:_TITLE_PREVIEW_LEN]
            touch_session(session_id, last_preview=preview or None)
        else:
            touch_session(session_id, last_preview="")
        return True

    @staticmethod
    def record_assistant_message(
        session_id: str,
        content: str,
        *,
        thinking: str = "",
        thinking_duration_seconds: int | None = None,
        model_id: str | None = None,
        model_label: str | None = None,
        usage: ContextUsageSdkMetrics | None = None,
    ) -> AiChatMessageDict:
        """Persist an assistant message and touch the session preview."""
        from services.ai.chat.message_usage import (
            entry_for_model_id,
            model_display_name_from_entry,
            turn_usage_delta,
        )

        if model_label is None and model_id is not None:
            model_label = model_display_name_from_entry(entry_for_model_id(model_id))

        preview = (content or thinking).strip().replace("\n", " ")[:_TITLE_PREVIEW_LEN]
        touch_session(session_id, last_preview=preview)
        turn_usage = None
        cost_usd: float | None = None
        if usage is not None:
            previous = get_last_assistant_usage_cumulative(session_id)
            turn_usage = turn_usage_delta(usage, previous)
            raw_turn_cost = usage.get("turn_cost_usd")
            if isinstance(raw_turn_cost, int | float) and float(raw_turn_cost) >= 0:
                cost_usd = float(raw_turn_cost)
        row = append_message(
            session_id=session_id,
            role="assistant",
            content=content,
            thinking=thinking,
            thinking_duration_seconds=thinking_duration_seconds,
            model_id=model_id,
            model_label=model_label,
            prompt_tokens=turn_usage.get("prompt_tokens") if turn_usage else None,
            completion_tokens=turn_usage.get("completion_tokens") if turn_usage else None,
            reasoning_tokens=turn_usage.get("reasoning_tokens") if turn_usage else None,
            cost_usd=cost_usd,
        )
        return AiChatSessionService._cast_message(row)

    @staticmethod
    def _rewrite_forked_disk_conversation_id(session_id: str) -> None:
        """Point copied OpenHands ``base_state.json`` at the forked session id."""
        disk = session_disk_dir(session_id)
        base_path = disk / "base_state.json"
        if not base_path.is_file():
            return
        try:
            data = json.loads(base_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        data["id"] = str(uuid.UUID(session_id))
        data["persistence_dir"] = str(disk)
        base_path.write_text(json.dumps(data), encoding="utf-8")

    @staticmethod
    def _fork_session_without_messages(source: dict[str, Any]) -> AiChatSessionDict:
        """Create a forked session row with no transcript rows and no SDK disk copy."""
        source_session_id = str(source["id"])
        new_session_id = str(uuid.uuid4())
        source_title = str(source.get("title") or "Chat").strip() or "Chat"
        fork_title = allocate_fork_session_title(source_session_id, source_title)
        row = create_session(
            session_id=new_session_id,
            title=fork_title,
            model_id=source.get("model_id"),
            mode=str(source.get("mode") or "agent"),
            agent_id=str(source.get("agent_id") or DEFAULT_AGENT_ID),
        )
        return AiChatSessionService._cast_session(row)

    @staticmethod
    def fork_session_at_message(
        source_session_id: str, message_id: int
    ) -> AiChatSessionDict | None:
        """Create a new session with messages up to *message_id* and copied SDK disk state."""
        source = get_session_by_id(source_session_id)
        if source is None:
            return None
        prefix = list_messages_up_to(source_session_id, message_id)
        if not prefix:
            return None
        if prefix[-1]["id"] != message_id:
            return None
        new_session_id = str(uuid.uuid4())
        source_title = str(source.get("title") or "Chat").strip() or "Chat"
        fork_title = allocate_fork_session_title(source_session_id, source_title)
        row = create_session(
            session_id=new_session_id,
            title=fork_title,
            model_id=source.get("model_id"),
            mode=str(source.get("mode") or "agent"),
            agent_id=str(source.get("agent_id") or DEFAULT_AGENT_ID),
        )
        bulk_append_messages(new_session_id, prefix)
        source_disk = session_disk_dir(source_session_id)
        target_disk = session_disk_dir(new_session_id)
        if source_disk.is_dir():
            shutil.copytree(source_disk, target_disk)
            AiChatSessionService._rewrite_forked_disk_conversation_id(new_session_id)
        last = prefix[-1]
        preview = (last.get("content") or last.get("thinking") or "").strip()
        preview = preview.replace("\n", " ")[:_TITLE_PREVIEW_LEN]
        touch_session(new_session_id, last_preview=preview or None)
        return AiChatSessionService._cast_session(row)

    @staticmethod
    def fork_session_at_user_message(
        source_session_id: str, user_message_id: int
    ) -> AiChatUserForkResult | None:
        """Fork before *user_message_id*; return the new session and composer draft text."""
        source = get_session_by_id(source_session_id)
        if source is None:
            return None
        prefix_inclusive = list_messages_up_to(source_session_id, user_message_id)
        if not prefix_inclusive or prefix_inclusive[-1]["id"] != user_message_id:
            return None
        user_row = prefix_inclusive[-1]
        if user_row.get("role") != "user":
            return None
        draft = str(user_row.get("content") or "")
        prior = prefix_inclusive[:-1]
        if prior:
            forked = AiChatSessionService.fork_session_at_message(
                source_session_id,
                prior[-1]["id"],
            )
            if forked is None:
                return None
            return {"session": forked, "composer_draft": draft}
        forked = AiChatSessionService._fork_session_without_messages(source)
        return {"session": forked, "composer_draft": draft}

    @staticmethod
    def extract_final_text(conversation: BaseConversation) -> str:
        """Return the latest agent message text from conversation events."""
        return _extract_final_text(conversation)

    @staticmethod
    def build_conversation(
        session_id: str,
        entry: AiModelEntry,
        agent_id: str,
        *,
        callbacks: list[Callable[[Event], None]] | None = None,
        token_callbacks: list[Callable[[LLMStreamChunk], None]] | None = None,
        composer: ComposerRunContext | None = None,
        stream: bool = True,
    ) -> BaseConversation:
        """Construct an OpenHands Conversation (worker thread only).

        Secrets are resolved inside ``AiLlmService.build_llm`` on the worker
        thread (same pattern as HTTP workers). Attachments are deferred for v1.
        """
        if _ATTACHMENTS_DEFERRED:
            pass

        from openhands.sdk import Agent, Conversation
        from openhands.sdk.context.condenser import LLMSummarizingCondenser
        from openhands.sdk.workspace import LocalWorkspace

        def_ = get_agent_def(agent_id)
        disk = session_disk_dir(session_id)
        disk.mkdir(parents=True, exist_ok=True)

        reasoning_effort = composer.get("reasoning_effort") if composer else None
        thinking_enabled = composer.get("thinking_enabled") if composer else None
        run_context_tokens = composer.get("run_context_tokens") if composer else None
        if run_context_tokens is None:
            run_context_tokens = effective_run_context_tokens(entry)
        base = resolve_llm_base_url(entry) or "(default)"
        usage_id = f"postmark-chat-{session_id}"
        with _allow_short_context_when_needed(entry):
            llm = AiLlmService.build_llm(
                entry,
                usage_id=usage_id,
                stream=stream,
                reasoning_effort=reasoning_effort,
                run_context_tokens=run_context_tokens,
                thinking_enabled=thinking_enabled,
            )
        ai_log(
            f"Chat run: {llm.model} @ {base} stream={stream} "
            f"reasoning_effort={llm.reasoning_effort!r} "
            f"extra_body={llm.litellm_extra_body!r} num_retries={llm.num_retries}"
        )

        # Separate condenser LLM — OpenHands persists summaries in the SDK event log.
        # UI transcript virtualization is display-only; condensation shrinks LLM context.
        # Condenser summaries use non-streaming completion(); stream=True crashes
        # without an on_token callback (OpenHands SDK ValueError).
        condenser_llm = llm.model_copy(
            update={"usage_id": f"condenser-{session_id}", "stream": False},
        )
        condenser_llm.reset_metrics()
        max_tokens = condenser_max_tokens(int(run_context_tokens or 0))
        condenser = LLMSummarizingCondenser(
            llm=condenser_llm,
            max_size=CHAT_CONDENSER_MAX_EVENTS,
            max_tokens=max_tokens,
            minimum_progress=CHAT_CONDENSER_MINIMUM_PROGRESS,
        )

        agent = Agent(
            llm=llm,
            tools=resolve_tools(def_.tool_names),
            system_prompt=def_.system_prompt,
            include_default_tools=list(def_.include_default_tools),
            condenser=condenser,
        )
        workspace = LocalWorkspace(working_dir=str(disk))
        max_iter = max(def_.max_iteration_per_run or DEFAULT_MAX_ITERATIONS, 3)

        return cast(
            "BaseConversation",
            Conversation(
                agent=agent,
                workspace=workspace,
                persistence_dir=str(user_ai_conversations_root()),
                conversation_id=uuid.UUID(session_id),
                callbacks=callbacks or [],
                token_callbacks=token_callbacks or [],
                max_iteration_per_run=max_iter,
                delete_on_close=False,
            ),
        )

    @staticmethod
    def _cast_session(row: dict[str, Any]) -> AiChatSessionDict:
        """Cast a repository dict to ``AiChatSessionDict``."""
        return AiChatSessionDict(
            id=row["id"],
            title=row["title"],
            model_id=row.get("model_id"),
            mode=row["mode"],
            agent_id=row.get("agent_id", DEFAULT_AGENT_ID),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_preview=row.get("last_preview"),
            archived=bool(row.get("archived", False)),
        )

    @staticmethod
    def _cast_message(row: dict[str, Any]) -> AiChatMessageDict:
        """Cast a repository dict to ``AiChatMessageDict``."""
        return AiChatMessageDict(
            id=int(row["id"]),
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            thinking=str(row.get("thinking") or ""),
            thinking_duration_seconds=row.get("thinking_duration_seconds"),
            model_id=row.get("model_id"),
            model_label=row.get("model_label"),
            prompt_tokens=row.get("prompt_tokens"),
            completion_tokens=row.get("completion_tokens"),
            reasoning_tokens=row.get("reasoning_tokens"),
            cost_usd=row.get("cost_usd"),
            send_model_id=row.get("send_model_id"),
            send_mode=row.get("send_mode"),
            send_agent_id=row.get("send_agent_id"),
            send_reasoning_effort=row.get("send_reasoning_effort"),
            send_thinking_enabled=row.get("send_thinking_enabled"),
            send_run_context_tokens=row.get("send_run_context_tokens"),
            created_at=row["created_at"],
        )


__all__ = [
    "AiChatMessageDict",
    "AiChatSessionDict",
    "AiChatSessionLoadDict",
    "AiChatSessionService",
    "ComposerRunContext",
    "UserMessageSendSnapshot",
]
