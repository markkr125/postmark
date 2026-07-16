"""Stack of agent-execute result cards inside one assistant message row."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from services.ai.chat.execute_events import ExecuteRunRecord
from ui.sidebar.ai.message_bubble.execute.card import ExecuteResultCard


class ExecuteResultGroup(QWidget):
    """Vertical list of :class:`ExecuteResultCard` rows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an empty hidden group."""
        super().__init__(parent)
        self.setObjectName("aiChatExecuteGroup")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 8)
        self._layout.setSpacing(8)
        self._cards: dict[str, ExecuteResultCard] = {}
        self.hide()

    def upsert_record(self, record: ExecuteRunRecord) -> ExecuteResultCard:
        """Create or update the card for *record*."""
        card = self._cards.get(record["id"])
        if card is None:
            card = ExecuteResultCard(self)
            self._cards[record["id"]] = card
            self._layout.addWidget(card)
        card.apply_record(record)
        self._sync_visibility()
        return card

    def sync_records(self, records: list[ExecuteRunRecord]) -> list[ExecuteResultCard]:
        """Upsert *records* and remove cards that are no longer present."""
        incoming_ids = {record["id"] for record in records}
        for record_id in list(self._cards):
            if record_id in incoming_ids:
                continue
            card = self._cards.pop(record_id)
            self._layout.removeWidget(card)
            card.deleteLater()
        cards: list[ExecuteResultCard] = []
        for record in records:
            cards.append(self.upsert_record(record))
        self._sync_visibility()
        return cards

    def set_records(self, records: list[ExecuteRunRecord]) -> list[ExecuteResultCard]:
        """Replace all cards from *records*."""
        return self.sync_records(records)

    def cards(self) -> list[ExecuteResultCard]:
        """Return cards in layout order."""
        return list(self._cards.values())

    def clear_cards(self) -> None:
        """Remove all cards."""
        self.set_records([])

    def _sync_visibility(self) -> None:
        if self._cards:
            self.show()
        else:
            self.hide()


__all__ = ["ExecuteResultGroup"]
