"""Confirmation / continue-iteration parking for :class:`AiChatWorker`."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEventLoop, Slot

from services.ai.chat.compaction import (
    CHAT_CONDENSER_DIAGNOSTIC_USAGE_FRACTION,
    log_compaction_diagnostics,
)
from services.ai.chat.confirmation_payload import (
    continue_iterations_payload,
    is_continue_iterations_payload,
    pending_actions_payload,
)
from services.ai.chat.context_usage import metrics_from_conversation
from services.ai.chat.response_text import resolve_assistant_parts
from services.ai.chat.tool_activity_events import tool_call_ids_from_confirmation_payload

if TYPE_CHECKING:
    from openhands.sdk import BaseConversation

logger = logging.getLogger(__name__)

_STOPPED_MESSAGE = "Stopped"
_WAITING_CONTINUE_STATUS = "Waiting to continue…"


class _ChatWorkerConfirmMixin:
    """Approve / Reject / Continue parking shared by the chat worker."""

    _session_id: str
    _conv: Any
    _stop_requested: bool
    _thinking_buffer: str
    _content_buffer: str
    _compaction_status_emitted: bool
    _confirmation_decision: str | None
    _reject_reason: str
    _pending_confirmation: object | None
    _confirm_loop: QEventLoop | None
    _waiting_for_confirmation: bool
    _tool_activity_tracker: Any
    _subagent_tracker: Any

    # Signals provided by AiChatWorker
    confirmation_needed: Any
    confirmation_cleared: Any
    status_changed: Any
    tool_activity_updated: Any
    subagent_updated: Any
    chunk_received: Any
    usage_updated: Any
    assistant_finished: Any
    failed: Any
    mutation_bridge_ready: Any

    def notify_mutation_bridge_ready(self) -> None:
        """Signal the GUI thread to drain mutation bridge events."""
        self.mutation_bridge_ready.emit(self._session_id)

    def is_awaiting_confirmation(self) -> bool:
        """Return whether this worker is parked for Approve/Reject."""
        return self._waiting_for_confirmation

    @Slot()
    def approve_confirmation(self) -> None:
        """Resume the parked run after user Approve / Continue."""
        ids = tool_call_ids_from_confirmation_payload(self._pending_confirmation)
        if ids and self._tool_activity_tracker.on_confirmation_approved(ids):
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
        """Reject pending actions (or Stop a continue prompt), then resume."""
        pending = self._pending_confirmation
        continue_prompt = is_continue_iterations_payload(pending)
        ids = tool_call_ids_from_confirmation_payload(pending)
        if ids and self._tool_activity_tracker.on_confirmation_rejected(ids):
            self.tool_activity_updated.emit(self._tool_activity_tracker.records())
        self._confirmation_decision = "reject"
        self._reject_reason = reason or "user rejected"
        self._pending_confirmation = None
        # Continue/Stop is not an SDK tool confirmation — do not reject actions.
        if not continue_prompt:
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
        """Park until Approve, Reject, or Stop for a tool confirmation."""
        return self._wait_for_user_decision(
            conv,
            pending_actions_payload(conv),
            status_text="Waiting for approval…",
            reject_pending_on_stop=True,
        )

    def _wait_for_continue_decision(self, conv: BaseConversation) -> str:
        """Park until Continue or Stop after a max-iterations pause."""
        limit = int(getattr(conv, "max_iteration_per_run", 0) or 0)
        payload = continue_iterations_payload(
            tool_calls=len(self._tool_activity_tracker.records()),
            limit=limit,
        )
        return self._wait_for_user_decision(
            conv,
            payload,
            status_text=_WAITING_CONTINUE_STATUS,
            reject_pending_on_stop=False,
        )

    def _wait_for_user_decision(
        self,
        conv: BaseConversation,
        payload: object,
        *,
        status_text: str,
        reject_pending_on_stop: bool,
    ) -> str:
        """Park on a nested event loop until Approve, Reject, or Stop.

        Returns ``approve``, ``reject``, or ``stop``.
        """
        # Mark waiting before emit so a concurrent cancel() takes the waiting branch.
        self._waiting_for_confirmation = True
        self._confirmation_decision = None
        if self._stop_requested:
            self._waiting_for_confirmation = False
            if reject_pending_on_stop:
                self._reject_pending_on_worker(conv, _STOPPED_MESSAGE)
            return "stop"

        self._pending_confirmation = payload
        self.confirmation_needed.emit(self._session_id, payload)
        self.status_changed.emit(status_text)

        # TOCTOU: cancel may have arrived after WAITING but before the loop starts.
        if self._stop_requested or self._confirmation_decision == "stop":
            self._waiting_for_confirmation = False
            self._pending_confirmation = None
            if self._session_id:
                self.confirmation_cleared.emit(self._session_id)
            if reject_pending_on_stop:
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
            if reject_pending_on_stop:
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

    def _finish_at_iteration_limit(
        self,
        conv: BaseConversation,
        *,
        baseline_cost: float,
        ring_total: int,
        ring_used: int,
        diagnostics: object,
        safe_close: Any,
    ) -> None:
        """End the turn gracefully after the user declines another iteration round."""
        n = len(self._tool_activity_tracker.records())
        calls = "tool call" if n == 1 else "tool calls"
        note = (
            f"Stopped after {n} {calls} — the assistant hit the step limit "
            "and you chose not to continue."
        )
        final = resolve_assistant_parts(conv, self._thinking_buffer, self._content_buffer)
        content = final.content
        if note not in content:
            content = f"{content.rstrip()}\n\n{note}" if content.strip() else note
        think_tail = final.thinking[len(self._thinking_buffer) :]
        content_tail = content[len(self._content_buffer) :]
        if think_tail or content_tail:
            self.chunk_received.emit(think_tail, content_tail)
        self._thinking_buffer = final.thinking
        self._content_buffer = content
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
        safe_close(conv)
        self._conv = None
        self.assistant_finished.emit(final.thinking, content)


__all__ = ["_STOPPED_MESSAGE", "_ChatWorkerConfirmMixin"]
