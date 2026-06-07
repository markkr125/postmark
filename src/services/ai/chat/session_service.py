"""AI chat session service — SQLite index + OpenHands Conversation bridge."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict, cast

from database.data_paths import session_disk_dir, user_ai_conversations_root
from database.models.ai_chat.ai_chat_query_repository import (
    get_session_by_id,
    list_sessions as repo_list_sessions,
    search_messages as repo_search_messages,
)
from database.models.ai_chat.ai_chat_repository import (
    DEFAULT_AGENT_ID,
    append_message,
    archive_session,
    create_session,
    delete_session,
    list_messages,
    rename_session,
    touch_session,
)
from services.ai.ai_config import AiConfig, AiModelEntry
from services.ai.chat.agent_registry import (
    DEFAULT_MAX_ITERATIONS,
    get_agent_def,
)
from services.ai.chat.response_text import extract_final_text as _extract_final_text
from services.ai.chat.tool_registry import resolve_tools
from services.ai.ai_logging import log as ai_log
from services.ai.llm_service import AiLlmService, resolve_llm_base_url
from services.ai.reasoning_effort import _is_ollama_model

if TYPE_CHECKING:
    from openhands.sdk import BaseConversation
    from openhands.sdk.event.base import Event
    from openhands.sdk.llm.streaming import LLMStreamChunk

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
    created_at: str


class ComposerRunContext(TypedDict, total=False):
    """Per-send composer settings passed from the UI."""

    run_context_tokens: int | None
    thinking_enabled: str | None
    reasoning_effort: str | None


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
    def record_user_message(session_id: str, content: str) -> AiChatMessageDict:
        """Persist a user message and touch the session preview."""
        preview = content.strip().replace("\n", " ")[:_TITLE_PREVIEW_LEN]
        touch_session(session_id, last_preview=preview)
        row = append_message(session_id=session_id, role="user", content=content)
        return AiChatSessionService._cast_message(row)

    @staticmethod
    def record_assistant_message(
        session_id: str,
        content: str,
        *,
        thinking: str = "",
        thinking_duration_seconds: int | None = None,
    ) -> AiChatMessageDict:
        """Persist an assistant message and touch the session preview."""
        preview = (content or thinking).strip().replace("\n", " ")[:_TITLE_PREVIEW_LEN]
        touch_session(session_id, last_preview=preview)
        row = append_message(
            session_id=session_id,
            role="assistant",
            content=content,
            thinking=thinking,
            thinking_duration_seconds=thinking_duration_seconds,
        )
        return AiChatSessionService._cast_message(row)

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
        from openhands.sdk.workspace import LocalWorkspace

        def_ = get_agent_def(agent_id)
        disk = session_disk_dir(session_id)
        disk.mkdir(parents=True, exist_ok=True)

        reasoning_effort = composer.get("reasoning_effort") if composer else None
        thinking_enabled = composer.get("thinking_enabled") if composer else None
        run_context_tokens = composer.get("run_context_tokens") if composer else None
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

        agent = Agent(
            llm=llm,
            tools=resolve_tools(def_.tool_names),
            system_prompt=def_.system_prompt,
            include_default_tools=list(def_.include_default_tools),
        )
        workspace = LocalWorkspace(working_dir=str(disk))
        max_iter = def_.max_iteration_per_run or DEFAULT_MAX_ITERATIONS

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
            created_at=row["created_at"],
        )


__all__ = [
    "AiChatMessageDict",
    "AiChatSessionDict",
    "AiChatSessionService",
    "ComposerRunContext",
]
