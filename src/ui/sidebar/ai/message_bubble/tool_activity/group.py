"""Stack of main-agent tool activity cards inside one assistant message row."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from services.ai.chat.tool_activity_events import ToolActivityRecord
from ui.sidebar.ai.message_bubble.tool_activity.card import ToolActivityCard


class ToolActivityGroup(QWidget):
    """Vertical list of :class:`ToolActivityCard` rows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an empty hidden group."""
        super().__init__(parent)
        self.setObjectName("aiChatToolActivityGroup")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 8)
        self._layout.setSpacing(8)
        self._cards: dict[str, ToolActivityCard] = {}
        self.hide()

    def upsert_record(self, record: ToolActivityRecord) -> ToolActivityCard:
        """Create or update the card for *record*."""
        card = self._cards.get(record["id"])
        if card is None:
            card = ToolActivityCard(self)
            self._cards[record["id"]] = card
            self._layout.addWidget(card)
        card.apply_record(record)
        self._sync_visibility()
        return card

    def sync_records(self, records: list[ToolActivityRecord]) -> list[ToolActivityCard]:
        """Upsert *records* and remove cards that are no longer present."""
        incoming_ids = {record["id"] for record in records}
        for record_id in list(self._cards):
            if record_id in incoming_ids:
                continue
            card = self._cards.pop(record_id)
            self._layout.removeWidget(card)
            card.deleteLater()
        cards: list[ToolActivityCard] = []
        for record in records:
            cards.append(self.upsert_record(record))
        self._sync_visibility()
        return cards

    def active_count(self) -> int:
        """Return cards still running."""
        return sum(1 for card in self._cards.values() if card.status() == "running")

    def clear_cards(self) -> None:
        """Remove all cards."""
        self.sync_records([])

    def _sync_visibility(self) -> None:
        if self._cards:
            self.show()
        else:
            self.hide()


__all__ = ["ToolActivityGroup"]
