"""Background worker for AI chat conversation runs."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QEventLoop, QObject, Signal, Slot

from services.ai.ai_config import AiModelEntry
from services.ai.chat.compaction import (
    CHAT_CONDENSER_DIAGNOSTIC_USAGE_FRACTION,
    log_compaction_diagnostics,
)
from services.ai.chat.provider_errors import summarize_provider_error
from services.ai.chat.confirmation_payload import (
    is_max_iterations_reached,
    is_waiting_for_confirmation,
)
from services.ai.chat.context_usage import (
    ContextUsageService,
    metrics_from_conversation,
)
from services.ai.chat.mutation.auto_approve import is_mutate_or_execute_tool
from services.ai.chat.mutation.claim_guard import (
    collection_ids_in_observation,
    observation_records_write,
)
from services.ai.chat.mutation.write_ledger import (
    clear_workspace_writes,
    record_collection_ids,
    record_workspace_write,
)
from services.ai.chat.response_text import (
    chunk_parts_from_stream,
    merge_stream_text,
    resolve_assistant_parts,
)
from services.ai.chat.session_service import AiChatSessionService, ComposerRunContext
from services.ai.chat.subagent_events import SubagentEventTracker
from services.ai.chat.tool_activity_events import ToolActivityTracker
from services.ai.chat.attachments.screenshots import set_session_vision
from services.ai.chat.tools.workspace_import.turn_guard import clear_import_turn
from services.ai.provider_catalog import effective_run_context_tokens
from ui.sidebar.ai.workers.chat_worker_confirm import (
    _STOPPED_MESSAGE,
    _ChatWorkerConfirmMixin,
)

if TYPE_CHECKING:
    from openhands.sdk import BaseConversation
    from openhands.sdk.event.base import Event
    from openhands.sdk.llm.streaming import LLMStreamChunk

logger = logging.getLogger(__name__)

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


def _is_mutate_or_execute_observation(event: object) -> bool:
    """Return True for ObservationEvents from mutate/execute/draft/import tools."""
    name = type(event).__name__
    if name != "ObservationEvent":
        try:
            from openhands.sdk.event.llm_convertible.observation import ObservationEvent

            if not isinstance(event, ObservationEvent):
                return False
        except Exception:
            return False
    tool_name = str(getattr(event, "tool_name", "") or "")
    return is_mutate_or_execute_tool(tool_name)


def _observation_text(event: object) -> str:
    """Return the observation payload text carried by *event*."""
    observation = getattr(event, "observation", None)
    if observation is None:
        return ""
    text = getattr(observation, "text", None)
    if isinstance(text, str):
        return text
    content = getattr(observation, "content", None)
    if isinstance(content, str):
        return content
    return str(observation)


class AiChatWorker(_ChatWorkerConfirmMixin, QObject):
    """Run one AI chat turn on a background thread.

    Configure via setters before ``moveToThread`` / ``QThread.start``.
    Uses ``Conversation.arun()`` so :meth:`cancel` can interrupt in-flight LLM
    calls. When the SDK pauses for confirmation, the worker keeps the
    Conversation alive and parks on a nested ``QEventLoop`` until Approve,
    Reject, or Stop. Max-iterations pauses reuse the same chrome as Continue /
    Stop so long document builds can keep going without a hard failure.
    """

    chunk_received = Signal(str, str)
    assistant_finished = Signal(str, str)
    failed = Signal(str, str, str)
    status_changed = Signal(str)
    context_compacted = Signal()
    usage_updated = Signal(object)
    subagent_updated = Signal(object)
    tool_activity_updated = Signal(object)
    confirmation_needed = Signal(str, object)
    confirmation_cleared = Signal(str)
    mutation_bridge_ready = Signal(str)

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
        self._tool_activity_tracker = ToolActivityTracker()
        self._confirmation_decision: str | None = None
        self._reject_reason: str = ""
        self._pending_confirmation: object | None = None
        self._confirm_loop: QEventLoop | None = None
        self._waiting_for_confirmation = False

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
        clear_workspace_writes(session_id)
        clear_import_turn(session_id)
        # Document screenshots are attached per chunk only for a model that can
        # read them, so the tool needs the active model's capability.
        set_session_vision(session_id, bool(entry.get("vision")))
        self._subagent_tracker = SubagentEventTracker(session_id=session_id)
        self._tool_activity_tracker = ToolActivityTracker()
        self._confirmation_decision = None
        self._reject_reason = ""
        self._pending_confirmation = None
        self._confirm_loop = None
        self._waiting_for_confirmation = False

    def cancel(self) -> None:
        """Request interruption of the in-flight conversation run.

        Safe to call from the GUI thread. While waiting for Approve, only set
        stop flags and quit the nested confirm loop — ``reject_pending_actions``
        runs on the worker thread after the loop exits (never mutate SDK state
        from the GUI thread).
        """
        self._stop_requested = True
        if self._waiting_for_confirmation:
            self._confirmation_decision = "stop"
            loop = self._confirm_loop
            if loop is not None and loop.isRunning():
                loop.quit()
            return
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
        if self._tool_activity_tracker.fail_inflight():
            self.tool_activity_updated.emit(self._tool_activity_tracker.records())
        self.notify_mutation_bridge_ready()
        _safe_close(conv)
        self._conv = None
        self.failed.emit(message, parts.thinking, parts.content)

    def _finish_success(
        self,
        conv: BaseConversation,
        *,
        baseline_cost: float,
        ring_total: int,
        ring_used: int,
        diagnostics: object,
    ) -> None:
        """Emit usage + assistant_finished and close the conversation."""
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
        if ring_total > 0 and ring_used / ring_total >= CHAT_CONDENSER_DIAGNOSTIC_USAGE_FRACTION:
            log_compaction_diagnostics(
                session_id=self._session_id,
                diagnostics=diagnostics,  # type: ignore[arg-type]
                condensation_occurred=self._compaction_status_emitted,
            )
        self.notify_mutation_bridge_ready()
        _safe_close(conv)
        self._conv = None
        if not final.thinking.strip() and not final.content.strip():
            self.failed.emit("No response from model", "", "")
            return
        self.assistant_finished.emit(final.thinking, final.content)

    @Slot()
    def run(self) -> None:
        """Execute ``send_message`` + ``arun``, pausing for confirmation as needed."""
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
                if self._tool_activity_tracker.ingest(event):
                    self.tool_activity_updated.emit(self._tool_activity_tracker.records())
                if _is_mutate_or_execute_observation(event):
                    # Mid-turn drain so Allow UI / tree / Output update promptly.
                    observation_text = _observation_text(event)
                    tool_name = str(getattr(event, "tool_name", "") or "")
                    if observation_records_write(tool_name, observation_text):
                        record_workspace_write(self._session_id)
                        record_collection_ids(
                            self._session_id,
                            collection_ids_in_observation(observation_text),
                        )
                    self.notify_mutation_bridge_ready()
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

            # Confirmation loop: arun may return WAITING or max-iterations multiple
            # times per turn. Each arun() resets the SDK iteration counter, so
            # Continue grants another full budget without raising the permanent cap.
            while True:
                asyncio.run(conv.arun())
                if self._stop_requested:
                    self._emit_failure(conv, _STOPPED_MESSAGE)
                    return
                if is_waiting_for_confirmation(conv):
                    decision = self._wait_for_confirmation_decision(conv)
                    if decision == "stop" or self._stop_requested:
                        self._emit_failure(conv, _STOPPED_MESSAGE)
                        return
                    if decision == "reject":
                        # Rejection already applied in reject_confirmation; resume
                        # so the agent can continue with UserRejectObservation.
                        continue
                    # approve → second arun implicitly confirms pending actions
                    continue
                if is_max_iterations_reached(conv):
                    decision = self._wait_for_continue_decision(conv)
                    if decision == "stop" or self._stop_requested:
                        self._emit_failure(conv, _STOPPED_MESSAGE)
                        return
                    if decision == "approve":
                        continue
                    # reject = user chose Stop on the continue prompt
                    self._finish_at_iteration_limit(
                        conv,
                        baseline_cost=baseline_cost,
                        ring_total=ring_total,
                        ring_used=ring_used,
                        diagnostics=diagnostics,
                        safe_close=_safe_close,
                    )
                    conv = None
                    return
                break

            self._finish_success(
                conv,
                baseline_cost=baseline_cost,
                ring_total=ring_total,
                ring_used=ring_used,
                diagnostics=diagnostics,
            )
            conv = None
        except Exception as exc:
            summary = summarize_provider_error(str(exc))
            logger.warning("AI chat run failed: %s", summary)
            logger.debug("Full AI chat failure", exc_info=True)
            if self._stop_requested:
                self._emit_failure(conv, _STOPPED_MESSAGE)
            else:
                self._emit_failure(conv, str(exc))
