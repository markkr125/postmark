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
from services.ai.chat.confirmation_payload import (
    is_waiting_for_confirmation,
    pending_actions_payload,
)
from services.ai.chat.context_usage import (
    ContextUsageService,
    metrics_from_conversation,
)
from services.ai.chat.mutation.claim_guard import observation_indicates_write
from services.ai.chat.mutation.write_ledger import (
    clear_workspace_writes,
    record_workspace_write,
)
from services.ai.chat.response_text import (
    chunk_parts_from_stream,
    merge_stream_text,
    resolve_assistant_parts,
)
from services.ai.chat.session_service import AiChatSessionService, ComposerRunContext
from services.ai.chat.subagent_events import SubagentEventTracker
from services.ai.chat.tool_activity_events import (
    ToolActivityTracker,
    tool_call_ids_from_confirmation_payload,
)
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


_MUTATE_EXECUTE_TOOLS = frozenset(
    {
        "postmark_workspace_mutate",
        "postmark_workspace_execute",
        "postmark_import",
    }
)


def _is_mutate_or_execute_observation(event: object) -> bool:
    """Return True for ObservationEvents from mutate/execute tools."""
    name = type(event).__name__
    if name != "ObservationEvent":
        try:
            from openhands.sdk.event.llm_convertible.observation import ObservationEvent

            if not isinstance(event, ObservationEvent):
                return False
        except Exception:
            return False
    tool_name = str(getattr(event, "tool_name", "") or "")
    return tool_name in _MUTATE_EXECUTE_TOOLS


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


class AiChatWorker(QObject):
    """Run one AI chat turn on a background thread.

    Configure via setters before ``moveToThread`` / ``QThread.start``.
    Uses ``Conversation.arun()`` so :meth:`cancel` can interrupt in-flight LLM
    calls. When the SDK pauses for confirmation, the worker keeps the
    Conversation alive and parks on a nested ``QEventLoop`` until Approve,
    Reject, or Stop.
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

    def is_awaiting_confirmation(self) -> bool:
        """Return whether this worker is parked for Approve/Reject."""
        return self._waiting_for_confirmation

    def notify_mutation_bridge_ready(self) -> None:
        """Signal the GUI thread to drain mutation bridge events."""
        self.mutation_bridge_ready.emit(self._session_id)

    @Slot()
    def approve_confirmation(self) -> None:
        """Resume the parked run after user Approve (SDK implicit confirm)."""
        ids = tool_call_ids_from_confirmation_payload(self._pending_confirmation)
        if self._tool_activity_tracker.on_confirmation_approved(ids):
            self.tool_activity_updated.emit(self._tool_activity_tracker.records())
        self._confirmation_decision = "approve"
        self._pending_confirmation = None
        if self._session_id:
            self.confirmation_cleared.emit(self._session_id)
        loop = self._confirm_loop
        if loop is not None and loop.isRunning():
            loop.quit()

    @Slot(str)
    def reject_confirmation(self, reason: str = "") -> None:
        """Reject pending actions then resume so the agent can continue."""
        ids = tool_call_ids_from_confirmation_payload(self._pending_confirmation)
        if self._tool_activity_tracker.on_confirmation_rejected(ids):
            self.tool_activity_updated.emit(self._tool_activity_tracker.records())
        self._confirmation_decision = "reject"
        self._reject_reason = reason or "user rejected"
        self._pending_confirmation = None
        conv = self._conv
        if conv is not None:
            reject = getattr(conv, "reject_pending_actions", None)
            if callable(reject):
                try:
                    reject(reason=self._reject_reason)
                except Exception:
                    logger.exception("AI chat reject_pending_actions failed")
        if self._session_id:
            self.confirmation_cleared.emit(self._session_id)
        loop = self._confirm_loop
        if loop is not None and loop.isRunning():
            loop.quit()

    def _wait_for_confirmation_decision(self, conv: BaseConversation) -> str:
        """Park on a nested event loop until Approve, Reject, or Stop.

        Returns ``approve``, ``reject``, or ``stop``.
        """
        # Mark waiting before emit so a concurrent cancel() takes the waiting branch.
        self._waiting_for_confirmation = True
        self._confirmation_decision = None
        if self._stop_requested:
            self._waiting_for_confirmation = False
            self._reject_pending_on_worker(conv, _STOPPED_MESSAGE)
            return "stop"

        payload = pending_actions_payload(conv)
        self._pending_confirmation = payload
        self.confirmation_needed.emit(self._session_id, payload)
        self.status_changed.emit("Waiting for approval…")

        # TOCTOU: cancel may have arrived after WAITING but before the loop starts.
        if self._stop_requested or self._confirmation_decision == "stop":
            self._waiting_for_confirmation = False
            self._pending_confirmation = None
            if self._session_id:
                self.confirmation_cleared.emit(self._session_id)
            self._reject_pending_on_worker(conv, _STOPPED_MESSAGE)
            return "stop"

        loop = QEventLoop()
        self._confirm_loop = loop
        try:
            if self._stop_requested or self._confirmation_decision == "stop":
                decision = "stop"
            else:
                loop.exec()
                decision = self._confirmation_decision or "stop"
        finally:
            self._confirm_loop = None
            self._waiting_for_confirmation = False

        if decision == "stop":
            self._reject_pending_on_worker(conv, _STOPPED_MESSAGE)
            if self._session_id:
                self.confirmation_cleared.emit(self._session_id)
        return decision

    def _reject_pending_on_worker(
        self,
        conv: BaseConversation | None,
        reason: str,
    ) -> None:
        """Reject unmatched actions on the worker thread only."""
        if conv is None:
            return
        reject = getattr(conv, "reject_pending_actions", None)
        if not callable(reject):
            return
        try:
            reject(reason=reason)
        except Exception:
            logger.exception("AI chat reject_pending_actions failed")

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
                    if observation_indicates_write(_observation_text(event)):
                        record_workspace_write(self._session_id)
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

            # Confirmation loop: arun may return WAITING multiple times per turn.
            while True:
                asyncio.run(conv.arun())
                if self._stop_requested:
                    self._emit_failure(conv, _STOPPED_MESSAGE)
                    return
                if not is_waiting_for_confirmation(conv):
                    break
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

            self._finish_success(
                conv,
                baseline_cost=baseline_cost,
                ring_total=ring_total,
                ring_used=ring_used,
                diagnostics=diagnostics,
            )
            conv = None
        except Exception as exc:
            logger.exception("AI chat run failed")
            if self._stop_requested:
                self._emit_failure(conv, _STOPPED_MESSAGE)
            else:
                self._emit_failure(conv, str(exc))
