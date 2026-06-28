"""Background worker for AI chat conversation runs."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Slot

from services.ai.ai_config import AiModelEntry
from services.ai.chat.response_text import (
    chunk_parts_from_stream,
    merge_stream_text,
    resolve_assistant_parts,
)
from services.ai.chat.compaction import (
    CHAT_CONDENSER_DIAGNOSTIC_USAGE_FRACTION,
    log_compaction_diagnostics,
)
from services.ai.chat.context_usage import (
    ContextUsageService,
    metrics_from_conversation,
)
from services.ai.chat.session_service import AiChatSessionService, ComposerRunContext
from services.ai.chat.subagent_events import SubagentEventTracker
from services.ai.provider_catalog import effective_run_context_tokens

if TYPE_CHECKING:
    from openhands.sdk import BaseConversation
    from openhands.sdk.event.base import Event
    from openhands.sdk.llm.streaming import LLMStreamChunk

logger = logging.getLogger(__name__)

_STOPPED_MESSAGE = "Stopped"
_SUMMARIZING_STATUS = "Summarizing earlier messages…"
_COMPACTION_EVENT_NAMES = frozenset(
    {"Condensation", "CondensationRequest", "CondensationSummaryEvent"}
)

try:
    from openhands.sdk.event.condenser import Condensation as _SdkCondensation
    from openhands.sdk.event.condenser import CondensationRequest as _SdkCondensationRequest
except ImportError:
    _SdkCondensation = None  # type: ignore[misc, assignment]
    _SdkCondensationRequest = None  # type: ignore[misc, assignment]


def _is_compaction_event(event: object) -> bool:
    """Return whether *event* is an OpenHands condensation lifecycle event."""
    if _SdkCondensation is not None and isinstance(event, _SdkCondensation):
        return True
    if _SdkCondensationRequest is not None and isinstance(event, _SdkCondensationRequest):
        return True
    return type(event).__name__ in _COMPACTION_EVENT_NAMES


def _is_compaction_request_event(event: object) -> bool:
    """Return whether *event* is the pre-condensation request signal."""
    if _SdkCondensationRequest is not None and isinstance(event, _SdkCondensationRequest):
        return True
    return type(event).__name__ == "CondensationRequest"


def _safe_close(conv: BaseConversation | None) -> None:
    """Close an OpenHands conversation without raising."""
    if conv is None:
        return
    try:
        conv.close()
    except Exception:
        logger.exception("AI chat conversation close failed")


class AiChatWorker(QObject):
    """Run one AI chat turn on a background thread.

    Configure via setters before ``moveToThread`` / ``QThread.start``.
    Uses ``Conversation.arun()`` so :meth:`cancel` can interrupt in-flight LLM
    calls without deadlocking the GUI on the conversation state lock.
    """

    chunk_received = Signal(str, str)
    assistant_finished = Signal(str, str)
    failed = Signal(str, str, str)
    status_changed = Signal(str)
    context_compacted = Signal()
    usage_updated = Signal(object)
    subagent_updated = Signal(object)

    def __init__(self) -> None:
        """Initialise with empty run parameters."""
        super().__init__()
        self._session_id: str = ""
        self._entry: AiModelEntry | None = None
        self._agent_id: str = ""
        self._text: str = ""
        self._composer: ComposerRunContext | None = None
        self._conv: BaseConversation | None = None
        self._stop_requested = False
        self._thinking_buffer = ""
        self._content_buffer = ""
        self._compaction_status_emitted = False
        self._subagent_tracker = SubagentEventTracker()

    def set_run(
        self,
        *,
        session_id: str,
        entry: AiModelEntry,
        agent_id: str,
        text: str,
        composer: ComposerRunContext | None = None,
    ) -> None:
        """Configure the next run (call before starting the thread)."""
        self._session_id = session_id
        self._entry = entry
        self._agent_id = agent_id
        self._text = text
        self._composer = composer
        self._conv = None
        self._stop_requested = False
        self._thinking_buffer = ""
        self._content_buffer = ""
        self._compaction_status_emitted = False
        self._subagent_tracker = SubagentEventTracker()

    def cancel(self) -> None:
        """Request interruption of the in-flight conversation run.

        Safe to call from the GUI thread while ``arun()`` is active.
        """
        self._stop_requested = True
        conv = self._conv
        if conv is None:
            return
        try:
            conv.interrupt()
        except Exception:
            logger.exception("AI chat interrupt failed")

    def _emit_failure(
        self,
        conv: BaseConversation | None,
        message: str,
    ) -> None:
        """Close *conv* and emit ``failed`` with any assistant text collected."""
        parts = resolve_assistant_parts(conv, self._thinking_buffer, self._content_buffer)
        failed_records = self._subagent_tracker.fail_inflight()
        if failed_records:
            self.subagent_updated.emit(self._subagent_tracker.records())
        _safe_close(conv)
        self._conv = None
        self.failed.emit(message, parts.thinking, parts.content)

    @Slot()
    def run(self) -> None:
        """Execute ``send_message`` + ``arun`` and stream tokens back."""
        conv = None
        try:
            entry = self._entry
            if entry is None or not self._session_id or not self._text:
                self.failed.emit("AI chat worker not configured", "", "")
                return

            if self._stop_requested:
                self._emit_failure(None, _STOPPED_MESSAGE)
                return

            def token_cb(chunk: LLMStreamChunk) -> None:
                parts = chunk_parts_from_stream(chunk)
                new_thinking = merge_stream_text(self._thinking_buffer, parts.thinking)
                new_content = merge_stream_text(self._content_buffer, parts.content)
                thinking_delta = new_thinking[len(self._thinking_buffer) :]
                content_delta = new_content[len(self._content_buffer) :]
                self._thinking_buffer = new_thinking
                self._content_buffer = new_content
                if thinking_delta or content_delta:
                    self.chunk_received.emit(thinking_delta, content_delta)

            def event_cb(event: Event) -> None:
                if _is_compaction_request_event(event):
                    if not self._compaction_status_emitted:
                        self.status_changed.emit(_SUMMARIZING_STATUS)
                        self._compaction_status_emitted = True
                    return
                if _is_compaction_event(event):
                    if not self._compaction_status_emitted:
                        self.status_changed.emit(_SUMMARIZING_STATUS)
                    self._compaction_status_emitted = True
                    self.context_compacted.emit()
                    return
                changed = self._subagent_tracker.ingest(event)
                if changed:
                    self.subagent_updated.emit(self._subagent_tracker.records())
                status = getattr(event, "status", None)
                if status is not None:
                    text = str(status)
                    if "summariz" in text.lower():
                        self.status_changed.emit(_SUMMARIZING_STATUS)
                    else:
                        self.status_changed.emit(text)

            conv = AiChatSessionService.build_conversation(
                self._session_id,
                entry,
                self._agent_id,
                callbacks=[event_cb],
                token_callbacks=[token_cb],
                composer=self._composer,
            )
            self._conv = conv
            if self._stop_requested:
                self._emit_failure(conv, _STOPPED_MESSAGE)
                return

            run_context = int(
                (self._composer or {}).get("run_context_tokens")
                or effective_run_context_tokens(entry)
                or 0
            )
            messages = AiChatSessionService.get_messages(self._session_id)
            agent = getattr(conv, "agent", None)
            diagnostics = ContextUsageService.collect_compaction_diagnostics(
                session_id=self._session_id,
                messages=messages,
                entry=entry,
                agent_id=self._agent_id,
                condenser=getattr(agent, "condenser", None),
                agent_llm=getattr(agent, "llm", None),
                run_context_tokens=run_context,
            )
            ring_total = int(diagnostics.get("ring_total_tokens", 0) or 0)
            ring_used = int(diagnostics.get("ring_used_tokens", 0) or 0)
            if (
                ring_total > 0
                and ring_used / ring_total >= CHAT_CONDENSER_DIAGNOSTIC_USAGE_FRACTION
            ):
                log_compaction_diagnostics(
                    session_id=self._session_id,
                    diagnostics=diagnostics,
                )

            conv.send_message(self._text)
            if self._stop_requested:
                self._emit_failure(conv, _STOPPED_MESSAGE)
                return

            baseline_cost = 0.0
            try:
                usage_id = f"postmark-chat-{self._session_id}"
                baseline_cost = float(
                    conv.conversation_stats.get_metrics_for_usage(usage_id).accumulated_cost or 0.0
                )
            except Exception:
                baseline_cost = 0.0

            asyncio.run(conv.arun())

            if self._stop_requested:
                self._emit_failure(conv, _STOPPED_MESSAGE)
                return

            final = resolve_assistant_parts(conv, self._thinking_buffer, self._content_buffer)
            think_tail = final.thinking[len(self._thinking_buffer) :]
            content_tail = final.content[len(self._content_buffer) :]
            if think_tail or content_tail:
                self.chunk_received.emit(think_tail, content_tail)
            self._thinking_buffer = final.thinking
            self._content_buffer = final.content
            sdk_metrics = metrics_from_conversation(
                conv,
                self._session_id,
                baseline_accumulated_cost=baseline_cost,
            )
            if sdk_metrics is not None:
                self.usage_updated.emit(sdk_metrics)
            if (
                ring_total > 0
                and ring_used / ring_total >= CHAT_CONDENSER_DIAGNOSTIC_USAGE_FRACTION
            ):
                log_compaction_diagnostics(
                    session_id=self._session_id,
                    diagnostics=diagnostics,
                    condensation_occurred=self._compaction_status_emitted,
                )
            _safe_close(conv)
            conv = None
            self._conv = None
            if not final.thinking.strip() and not final.content.strip():
                self.failed.emit("No response from model", "", "")
                return
            self.assistant_finished.emit(final.thinking, final.content)
        except Exception as exc:
            logger.exception("AI chat run failed")
            if self._stop_requested:
                self._emit_failure(conv, _STOPPED_MESSAGE)
            else:
                self._emit_failure(conv, str(exc))
