"""Background worker to generate an AI chat session title."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from services.ai.ai_config import AiModelEntry
from services.ai.chat.session_service import AiChatSessionService

logger = logging.getLogger(__name__)


class AiChatTitleWorker(QObject):
    """Generate a session title via ``Conversation.generate_title()`` off the GUI thread."""

    title_ready = Signal(str)
    failed = Signal(str)

    def __init__(self) -> None:
        """Initialise with empty parameters."""
        super().__init__()
        self._session_id: str = ""
        self._entry: AiModelEntry | None = None
        self._agent_id: str = ""

    def set_run(
        self,
        *,
        session_id: str,
        entry: AiModelEntry,
        agent_id: str,
    ) -> None:
        """Configure the title generation run."""
        self._session_id = session_id
        self._entry = entry
        self._agent_id = agent_id

    @Slot()
    def run(self) -> None:
        """Build a conversation and call ``generate_title()``."""
        conv = None
        try:
            entry = self._entry
            if entry is None or not self._session_id:
                self.failed.emit("Title worker not configured")
                return
            conv = AiChatSessionService.build_conversation(
                self._session_id,
                entry,
                self._agent_id,
                stream=False,
            )
            title = conv.generate_title()
            cleaned = title.strip() if isinstance(title, str) else ""
            if conv is not None:
                try:
                    conv.close()
                except Exception:
                    logger.exception("AI title conversation close failed")
                conv = None
            if cleaned:
                self.title_ready.emit(cleaned)
            else:
                self.failed.emit("Empty title")
        except Exception as exc:
            logger.exception("AI title generation failed")
            if conv is not None:
                try:
                    conv.close()
                except Exception:
                    logger.exception("AI title conversation close failed")
            self.failed.emit(str(exc))
