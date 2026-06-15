"""Context usage ring refresh and popup wiring for :class:`AiChatPanel`."""

# mypy: disable-error-code=attr-defined

from __future__ import annotations

from typing import cast

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Slot

from services.ai.chat.agent_registry import DEFAULT_AGENT_ID
from services.ai.chat.context_usage import ContextUsageBreakdown, ContextUsageSdkMetrics
from services.ai.chat.session_service import AiChatMessageDict, AiChatSessionService
from ui.sidebar.ai.chat_context_popup import AiChatContextUsagePopup
from ui.sidebar.ai.workers.context_usage_worker import ContextUsageLoader

_CONTEXT_REFRESH_DEBOUNCE_MS = 200


class _ChatPanelContextUsageMixin:  # type: ignore[misc]
    """Debounced context-usage refresh and popover toggle."""

    _context_breakdown: ContextUsageBreakdown | None
    _context_refresh_timer: QTimer
    _context_usage_loader: ContextUsageLoader
    _context_session_id: str | None
    _context_sdk_metrics: ContextUsageSdkMetrics | None
    _pending_turn_sdk_metrics: ContextUsageSdkMetrics | None
    _context_refresh_pending: bool
    _context_refresh_generation: int
    _summarized_notice_session_id: str | None

    def _init_context_usage_state(self) -> None:
        """Initialise context ring worker state (call from ``__init__``)."""
        self._context_breakdown = None
        self._context_session_id = None
        self._context_sdk_metrics = None
        self._pending_turn_sdk_metrics = None
        self._context_refresh_pending = False
        self._context_refresh_generation = 0
        self._summarized_notice_session_id = None
        self._context_usage_loader = ContextUsageLoader(cast(QObject, self))
        queued = Qt.ConnectionType.QueuedConnection
        self._context_usage_loader.finished.connect(self._on_context_usage_loader_finished, queued)
        self._context_refresh_timer = QTimer(cast(QObject, self))
        self._context_refresh_timer.setSingleShot(True)
        self._context_refresh_timer.setInterval(_CONTEXT_REFRESH_DEBOUNCE_MS)
        self._context_refresh_timer.timeout.connect(self._run_context_usage_refresh)
        self._context_ring.context_requested.connect(self._toggle_context_popup)
        AiChatContextUsagePopup.instance().hidden.connect(self._restore_context_ring_tooltip)
        self._input.textChanged.connect(self._schedule_context_usage_refresh)

    def set_context_breakdown(self, breakdown: ContextUsageBreakdown) -> None:
        """Apply a breakdown to the ring and cached popover state."""
        self._context_breakdown = breakdown
        self._context_ring.set_usage(breakdown["used_tokens"], breakdown["total_tokens"])
        if breakdown["has_summarized"]:
            self.on_context_compacted()
        popup = AiChatContextUsagePopup.instance()
        if popup.isVisible():
            popup.set_breakdown(breakdown)
            self._context_ring.setToolTip("")

    def set_context_session_id(self, session_id: str | None) -> None:
        """Set the session used for full-transcript usage accounting."""
        self._context_session_id = session_id

    def set_context_usage(self, used_tokens: int, total_tokens: int) -> None:
        """Thin wrapper updating the ring tooltip only."""
        self._context_ring.set_usage(used_tokens, total_tokens)

    def refresh_context_usage(
        self,
        *,
        sdk_metrics: object | None = None,
    ) -> None:
        """Request an immediate or SDK-informed context usage refresh."""
        if isinstance(sdk_metrics, dict):
            if "categories" in sdk_metrics:
                self.set_context_breakdown(cast(ContextUsageBreakdown, sdk_metrics))
                return
            self._context_sdk_metrics = cast(ContextUsageSdkMetrics, sdk_metrics)
        self._schedule_context_usage_refresh()

    @Slot()
    def deliver_context_usage_refresh(self) -> None:
        """GUI-thread slot for worker ``context_compacted`` refresh requests."""
        if QThread.currentThread() != self.thread():
            self._context_usage_refresh_delivery_requested.emit()  # type: ignore[attr-defined]
            return
        self.refresh_context_usage()

    @Slot(object)
    def deliver_context_usage_metrics(self, sdk_metrics: object) -> None:
        """GUI-thread slot for worker ``usage_updated`` payloads."""
        if QThread.currentThread() != self.thread():
            self._context_usage_metrics_delivery_requested.emit(sdk_metrics)  # type: ignore[attr-defined]
            return
        self._apply_context_usage_metrics(sdk_metrics)

    def _apply_context_usage_metrics(self, sdk_metrics: object) -> None:
        """Apply SDK metrics after delivery has reached the GUI thread."""
        if isinstance(sdk_metrics, dict) and "categories" not in sdk_metrics:
            self._pending_turn_sdk_metrics = cast(ContextUsageSdkMetrics, sdk_metrics)
        self.refresh_context_usage(sdk_metrics=sdk_metrics)

    def take_pending_turn_sdk_metrics(self) -> ContextUsageSdkMetrics | None:
        """Return and clear SDK metrics stashed for the active assistant turn."""
        metrics = self._pending_turn_sdk_metrics
        self._pending_turn_sdk_metrics = None
        return metrics

    @Slot()
    def _apply_context_usage_refresh(self) -> None:
        """Refresh context usage after delivery has reached the GUI thread."""
        self.refresh_context_usage()

    def _schedule_context_usage_refresh(self, *_args: object) -> None:
        """Debounce expensive token accounting during composer typing."""
        if QThread.currentThread() != self.thread():
            self._context_usage_schedule_requested.emit()  # type: ignore[attr-defined]
            return
        self._schedule_context_usage_refresh_on_gui()

    @Slot()
    def _schedule_context_usage_refresh_on_gui(self) -> None:
        """Arm the debounce timer on the GUI thread."""
        self._context_refresh_pending = True
        self._context_refresh_timer.start()

    def _context_usage_request_kwargs(self) -> dict[str, object] | None:
        """Build worker parameters for the current panel state."""
        entry = self.current_model_entry()
        if entry is None:
            self._context_breakdown = None
            self._context_ring.set_usage(0, 0)
            return None
        session_id = getattr(self, "_virtual_session_id", None) or self._context_session_id
        agent_id = DEFAULT_AGENT_ID
        messages: list[AiChatMessageDict] = []
        if session_id:
            row = AiChatSessionService.get_session(session_id)
            if row is not None:
                agent_id = row.get("agent_id", DEFAULT_AGENT_ID)
            messages = AiChatSessionService.get_messages(session_id)
        return {
            "session_id": session_id,
            "messages": messages,
            "entry": entry,
            "agent_id": agent_id,
            "draft_text": self._input.toPlainText(),
            "streaming_thinking": self.streaming_assistant_thinking()
            if getattr(self, "_streaming_bubble", None)
            else "",
            "streaming_content": self.streaming_assistant_text()
            if getattr(self, "_streaming_bubble", None)
            else "",
            "sdk_metrics": self._context_sdk_metrics,
        }

    def _run_context_usage_refresh(self) -> None:
        """Start a background worker to rebuild the usage breakdown."""
        if self._context_usage_loader.is_running():
            self._context_refresh_pending = True
            return
        request = self._context_usage_request_kwargs()
        if request is None:
            self._context_refresh_pending = False
            return
        self._context_refresh_pending = False
        self._context_refresh_generation += 1
        generation = self._context_refresh_generation
        self._context_usage_loader.run_breakdown(generation, **request)

    @Slot(int, object)
    def _on_context_usage_loader_finished(self, generation: int, breakdown: object) -> None:
        """Apply worker breakdown and replay a pending refresh when needed."""
        self._apply_context_usage_breakdown(breakdown, generation)
        if self._context_refresh_pending:
            self._context_refresh_pending = False
            QTimer.singleShot(0, self._run_context_usage_refresh)

    @Slot(object, int)
    def _apply_context_usage_breakdown(self, breakdown: object, generation: int) -> None:
        """Apply worker breakdown on the GUI thread."""
        if generation != self._context_refresh_generation:
            return
        if not isinstance(breakdown, dict):
            return
        self.set_context_breakdown(cast(ContextUsageBreakdown, breakdown))

    def _shutdown_context_usage_worker(self) -> None:
        """Stop any in-flight context usage worker."""
        self._context_refresh_pending = False
        self._context_refresh_generation += 1
        if self._context_refresh_timer.isActive():
            self._context_refresh_timer.stop()
        self._context_usage_loader.shutdown()

    def _hide_context_popup(self) -> None:
        """Dismiss the context usage popover."""
        AiChatContextUsagePopup.instance().hide_popup()

    def _restore_context_ring_tooltip(self) -> None:
        """Restore the ring tooltip after the popup closes."""
        breakdown = self._context_breakdown
        if breakdown is not None:
            self._context_ring.set_usage(breakdown["used_tokens"], breakdown["total_tokens"])
            return
        self._context_ring.set_usage(0, self.current_run_context_tokens())

    def _hide_peer_ai_popups_for_context(self) -> None:
        """Close model/mode/history popups before opening the context tray."""
        self._picker_popup.hidePopup()
        self._mode_popup.hide_popup()
        from ui.sidebar.ai.chat_sessions.history_popup import AiSessionHistoryPopup

        AiSessionHistoryPopup.instance().hide_popup()

    def _toggle_context_popup(self) -> None:
        """Toggle the context breakdown popover above the ring."""
        self.context_requested.emit()
        popup = AiChatContextUsagePopup.instance()
        if popup.isVisible():
            popup.hide_popup()
            return
        self._hide_peer_ai_popups_for_context()
        breakdown = self._context_breakdown
        if breakdown is None:
            self.refresh_context_usage()
            breakdown = self._context_breakdown
        popup.show_for(self._context_ring, breakdown)
        self._context_ring.setToolTip("")

    def _reset_context_usage_chrome(self) -> None:
        """Clear ring state on session switch or new chat."""
        self._hide_context_popup()
        self._context_breakdown = None
        self._context_session_id = None
        self._context_sdk_metrics = None
        self._context_refresh_pending = False
        if self._context_refresh_timer.isActive():
            self._context_refresh_timer.stop()
        self._summarized_notice_session_id = None
        entry = self.current_model_entry()
        total = self.current_run_context_tokens() if entry is not None else 0
        self._context_ring.set_usage(0, total)

    def on_context_compacted(self) -> None:
        """Show the muted transcript notice after the first compaction."""
        session_id = getattr(self, "_virtual_session_id", None)
        if not session_id or session_id == self._summarized_notice_session_id:
            return
        self._summarized_notice_session_id = session_id
        self._ensure_summarized_notice()

    def _ensure_summarized_notice(self) -> None:
        """Insert the one-line summarized-context notice if missing."""
        from ui.sidebar.ai.transcript.summarized_notice import (
            find_summarized_notice,
            make_summarized_notice,
        )

        if find_summarized_notice(self._messages) is not None:
            return
        notice = make_summarized_notice(self._messages)
        index = self._messages_layout.indexOf(self._empty_label)
        if index < 0:
            self._messages_layout.insertWidget(0, notice)
        else:
            self._messages_layout.insertWidget(index, notice)
