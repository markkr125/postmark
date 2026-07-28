"""Collapsible stack of compact main-agent tool-activity rows.

A run of tool calls collapses into one summary line ("N tool calls · 2.4s")
that expands on click, so the transcript stays glanceable; rows that failed
stay visible even while collapsed, and a running row keeps the turn from
looking dead. Rows below are the compact :class:`ToolActivityCard` lines.
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from services.ai.chat.tool_activity_events import ToolActivityRecord
from ui.sidebar.ai.message_bubble.tool_activity.card import ToolActivityCard

_FAILED_STATUSES = frozenset({"error", "rejected"})
_RUNNING_OR_PENDING = frozenset({"running", "pending_confirm"})


def _group_duration(records: list[ToolActivityRecord]) -> str:
    """Return the total elapsed time across *records*, e.g. ``2.4s``, or empty."""
    elapsed = 0.0
    any_timing = False
    for record in records:
        started = record.get("started_at")
        completed = record.get("completed_at")
        if started is None or completed is None:
            continue
        elapsed += max(0.0, completed - started)
        any_timing = True
    if not any_timing:
        return ""
    return f"{elapsed:.1f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"


class _GroupHeader(QWidget):
    """Clickable summary line that toggles the group's collapsed state."""

    def __init__(self, group: ToolActivityGroup) -> None:
        """Build a header wired to toggle *group*."""
        super().__init__(group)
        self.setObjectName("aiChatToolActivityGroupHeader")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(6)

        self._chevron = QToolButton(self)
        self._chevron.setObjectName("aiChatToolActivityGroupChevron")
        self._chevron.setArrowType(Qt.ArrowType.RightArrow)
        self._chevron.setAutoRaise(True)
        self._chevron.setCheckable(True)
        self._chevron.setFixedSize(16, 16)
        self._chevron.toggled.connect(group.on_header_toggled)
        row.addWidget(self._chevron, 0, Qt.AlignmentFlag.AlignVCenter)

        self._summary = QLabel(self)
        self._summary.setObjectName("aiChatToolActivityGroupSummary")
        self._summary.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._summary, 1, Qt.AlignmentFlag.AlignVCenter)

        self._timing = QLabel(self)
        self._timing.setObjectName("aiChatToolActivityGroupTiming")
        self._timing.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._timing, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, _event: object) -> None:
        """Toggle the chevron when the summary line is clicked."""
        self._chevron.toggle()

    def sync(self, records: list[ToolActivityRecord], expanded: bool) -> None:
        """Refresh the summary, timing, and chevron direction from *records*."""
        count = len(records)
        running = sum(1 for record in records if record["status"] == "running")
        failed = sum(1 for record in records if record["status"] in _FAILED_STATUSES)
        parts = [f"{count} tool call" + ("" if count == 1 else "s")]
        if running:
            parts.append(f"{running} running")
        if failed:
            parts.append(f"{failed} failed")
        self._summary.setText(" · ".join(parts))
        self._summary.setProperty("failed", "true" if failed else "false")
        self._summary.style().unpolish(self._summary)
        self._summary.style().polish(self._summary)
        self._timing.setText(_group_duration(records))
        self._chevron.blockSignals(True)
        self._chevron.setChecked(expanded)
        self._chevron.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._chevron.blockSignals(False)


class ToolActivityGroup(QWidget):
    """Collapsible container of :class:`ToolActivityCard` rows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an empty hidden group with a collapsed summary header."""
        super().__init__(parent)
        self.setObjectName("aiChatToolActivityGroup")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 4)
        self._layout.setSpacing(2)

        self._header = _GroupHeader(self)
        self._layout.addWidget(self._header)

        self._rows = QWidget(self)
        self._rows.setObjectName("aiChatToolActivityGroupRows")
        self._rows.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        rows_layout = QVBoxLayout(self._rows)
        rows_layout.setContentsMargins(22, 0, 0, 0)
        rows_layout.setSpacing(2)
        self._rows.setVisible(False)
        self._layout.addWidget(self._rows)

        self._cards: dict[str, ToolActivityCard] = {}
        self._last_records: list[ToolActivityRecord] = []
        self._expanded = False
        self._auto_expanded = False
        self._user_toggled = False
        self.hide()

    def header(self) -> QWidget:
        """Return the summary header widget."""
        return self._header

    def rows_widget(self) -> QWidget:
        """Return the container holding the collapsible rows."""
        return self._rows

    def is_expanded(self) -> bool:
        """Return whether the rows are shown."""
        return self._expanded

    def on_header_toggled(self, expanded: bool) -> None:
        """Record a manual toggle, then apply it.

        A manual choice wins over automatic behavior: a manually expanded group is
        never auto-collapsed, and a manually collapsed one is never auto-expanded.
        """
        self._user_toggled = True
        self._auto_expanded = False
        self.set_expanded(expanded)

    def set_expanded(self, expanded: bool) -> None:
        """Show or hide the rows, keeping failed rows visible when collapsed."""
        self._expanded = expanded
        self._sync_row_visibility()
        self._header.sync(self._last_records, expanded)

    def upsert_record(self, record: ToolActivityRecord) -> ToolActivityCard:
        """Create or update the card for *record*."""
        card = self._cards.get(record["id"])
        if card is None:
            card = ToolActivityCard(self._rows)
            self._cards[record["id"]] = card
            rows_layout = self._rows.layout()
            assert rows_layout is not None
            rows_layout.addWidget(card)
        card.apply_record(record)
        self._last_records = [
            record if existing["id"] == record["id"] else existing
            for existing in self._last_records
        ]
        if all(existing["id"] != record["id"] for existing in self._last_records):
            self._last_records.append(record)
        self._sync_visibility()
        return card

    def sync_records(self, records: list[ToolActivityRecord]) -> list[ToolActivityCard]:
        """Upsert *records* and remove cards that are no longer present."""
        incoming_ids = {record["id"] for record in records}
        for record_id in list(self._cards):
            if record_id in incoming_ids:
                continue
            card = self._cards.pop(record_id)
            rows_layout = self._rows.layout()
            assert rows_layout is not None
            rows_layout.removeWidget(card)
            card.deleteLater()
        cards: list[ToolActivityCard] = []
        rows_layout = self._rows.layout()
        assert rows_layout is not None
        ordered: list[ToolActivityRecord] = []
        for index, record in enumerate(records):
            card = self.upsert_record(record)
            ordered.append(record)
            rows_layout.removeWidget(card)
            cast(QVBoxLayout, rows_layout).insertWidget(index, card)
            cards.append(card)
        self._last_records = ordered
        self._sync_visibility()
        return cards

    def active_count(self) -> int:
        """Return cards still running."""
        return sum(1 for card in self._cards.values() if card.status() == "running")

    def clear_cards(self) -> None:
        """Remove all cards."""
        self.sync_records([])

    def _row_visible(self, card: ToolActivityCard) -> bool:
        """Return whether *card* should be shown in the current collapse state."""
        if self._expanded:
            return True
        # Collapsed: keep failures (and a running row, so the turn reads as
        # alive) visible; hide routine completed rows.
        return card.status() in _FAILED_STATUSES or card.status() == "running"

    def _sync_row_visibility(self) -> None:
        for card in self._cards.values():
            card.setVisible(self._row_visible(card))
        any_visible = any(self._row_visible(card) for card in self._cards.values())
        self._rows.setVisible(self._expanded or any_visible)

    def _sync_visibility(self) -> None:
        if self._cards:
            self._sync_auto_state()
            self._header.sync(self._last_records, self._expanded)
            self._sync_row_visibility()
            self.show()
        else:
            self.hide()

    def _sync_auto_state(self) -> None:
        """Auto-expand while running and auto-collapse when done, unless manually set.

        A group shows its live progress while any row is running, then folds back to
        the summary once the run finishes — but never overrides a manual toggle.
        """
        if self._user_toggled:
            return
        running = any(card.status() in _RUNNING_OR_PENDING for card in self._cards.values())
        if running and not self._expanded:
            self._auto_expanded = True
            self.set_expanded(True)
        elif not running and self._auto_expanded:
            self._auto_expanded = False
            self.set_expanded(False)


__all__ = ["ToolActivityGroup"]
