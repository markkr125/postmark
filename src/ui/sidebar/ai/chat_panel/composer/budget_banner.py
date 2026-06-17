"""Budget limit banner above the AI chat composer."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from services.ai.chat.budget_status import (
    ConnectionBudgetStatus,
    format_connection_budget_banner_html,
)


class AiChatBudgetBanner(QFrame):
    """Warn or block messaging when provider connection budgets are exceeded."""

    open_settings_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build a compact warning banner with a Settings link."""
        super().__init__(parent)
        self.setObjectName("aiChatBudgetBanner")
        self._visible_dedupe_key = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 4)
        layout.setSpacing(6)

        self._message = QLabel("")
        self._message.setObjectName("bannerMessage")
        self._message.setWordWrap(True)
        self._message.setOpenExternalLinks(False)
        self._message.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._message.linkActivated.connect(self._on_message_link)
        layout.addWidget(self._message, 1)

    def set_status(self, status: ConnectionBudgetStatus | None) -> None:
        """Show, hide, or update the banner for *status*."""
        if status is None or status["state"] not in {"soft_exceeded", "hard_exceeded"}:
            self._visible_dedupe_key = ""
            self.hide()
            return

        html = format_connection_budget_banner_html(status)
        self._message.setTextFormat(Qt.TextFormat.RichText)
        self._message.setText(html)
        self._visible_dedupe_key = status["dedupe_key"]
        self.show()

    def _on_message_link(self, url: str) -> None:
        """Open Settings on the Budgets page when the inline link is clicked."""
        if url == "action:budgets":
            self.open_settings_clicked.emit()
