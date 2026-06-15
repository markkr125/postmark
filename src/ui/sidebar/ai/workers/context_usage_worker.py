"""Background worker that builds AI chat context usage breakdowns."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from services.ai.ai_config import AiModelEntry
from services.ai.chat.context_usage import (
    ContextUsageBreakdown,
    ContextUsageSdkMetrics,
    build_breakdown,
)
from services.ai.chat.session_service import AiChatMessageDict


class ContextUsageWorker(QObject):
    """Compute context usage off the GUI thread."""

    finished = Signal(object)

    def __init__(self) -> None:
        """Initialise with empty parameters."""
        super().__init__()
        self._session_id: str | None = None
        self._messages: list[AiChatMessageDict] = []
        self._entry: AiModelEntry | None = None
        self._agent_id: str = ""
        self._draft_text: str = ""
        self._streaming_thinking: str = ""
        self._streaming_content: str = ""
        self._sdk_metrics: ContextUsageSdkMetrics | None = None

    def set_request(
        self,
        *,
        session_id: str | None,
        messages: list[AiChatMessageDict],
        entry: AiModelEntry | None,
        agent_id: str,
        draft_text: str = "",
        streaming_thinking: str = "",
        streaming_content: str = "",
        sdk_metrics: ContextUsageSdkMetrics | None = None,
    ) -> None:
        """Configure the next breakdown build (call before starting the thread)."""
        self._session_id = session_id
        self._messages = list(messages)
        self._entry = entry
        self._agent_id = agent_id
        self._draft_text = draft_text
        self._streaming_thinking = streaming_thinking
        self._streaming_content = streaming_content
        self._sdk_metrics = sdk_metrics

    @Slot()
    def run(self) -> None:
        """Build the breakdown and emit ``finished``."""
        breakdown: ContextUsageBreakdown = build_breakdown(
            session_id=self._session_id,
            messages=self._messages,
            entry=self._entry,
            agent_id=self._agent_id,
            draft_text=self._draft_text,
            streaming_thinking=self._streaming_thinking,
            streaming_content=self._streaming_content,
            sdk_metrics=self._sdk_metrics,
        )
        self.finished.emit(breakdown)
