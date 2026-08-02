"""Stack of pending-tool Approve cards inside one assistant message row."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from services.ai.chat.mutation.auto_approve import add_rule, kind_label
from ui.sidebar.ai.message_bubble.confirm.card import PendingActionDict, PendingToolCard


class PendingToolGroup(QWidget):
    """Vertical list of :class:`PendingToolCard` rows with batch footer actions."""

    approve_requested = Signal()
    reject_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an empty hidden group."""
        super().__init__(parent)
        self.setObjectName("aiChatPendingToolGroup")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 8)
        self._layout.setSpacing(8)
        self._cards: list[PendingToolCard] = []
        self._actions: list[PendingActionDict] = []

        self._footer = QWidget(self)
        self._footer.setObjectName("aiChatPendingToolFooter")
        footer_row = QHBoxLayout(self._footer)
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.setSpacing(8)

        self._allow_all = QPushButton("Allow all")
        self._allow_all.setObjectName("aiChatPendingAllow")
        self._allow_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self._allow_all.clicked.connect(self._on_approve)
        footer_row.addWidget(self._allow_all)

        self._reject_all = QPushButton("Reject all")
        self._reject_all.setObjectName("aiChatPendingReject")
        self._reject_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reject_all.clicked.connect(self.reject_requested.emit)
        footer_row.addWidget(self._reject_all)

        self._always_all = QPushButton("Always allow")
        self._always_all.setObjectName("aiChatPendingAlwaysAllow")
        self._always_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self._always_all.clicked.connect(self._on_always_allow)
        footer_row.addWidget(self._always_all)

        footer_row.addStretch()
        self._layout.addWidget(self._footer)
        self._footer.hide()
        self.hide()

    def show_pending(self, payload: object) -> None:
        """Replace cards from *payload* and show the group."""
        actions = _normalize_actions(payload)
        self._actions = actions
        self._rebuild_cards(actions)
        kinds = _unique_kinds(actions)
        multi = len(actions) > 1
        continue_prompt = any(
            str(action.get("kind") or "") == "continue_iterations" for action in actions
        )
        self._footer.setVisible(multi and not continue_prompt)
        for button in (self._allow_all, self._reject_all, self._always_all):
            button.setEnabled(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._always_all.setEnabled(bool(kinds) and not continue_prompt)
        self._always_all.setVisible(not continue_prompt)
        if len(kinds) == 1 and not continue_prompt:
            self._always_all.setText(f"Always allow: {kind_label(kinds[0])}")
        else:
            self._always_all.setText("Always allow")
        if actions:
            self.show()
        else:
            self.hide()

    def clear_pending(self) -> None:
        """Remove all pending cards and hide the group."""
        self._actions = []
        self._rebuild_cards([])
        self._footer.hide()
        self.hide()

    def has_pending(self) -> bool:
        """Return whether any pending action cards are mounted."""
        return bool(self._actions) and not self.isHidden()

    def _rebuild_cards(self, actions: list[PendingActionDict]) -> None:
        for card in self._cards:
            self._layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        show_buttons = len(actions) == 1
        # Insert cards above the footer (last layout item).
        insert_at = max(0, self._layout.count() - 1)
        for index, action in enumerate(actions):
            card = PendingToolCard(self)
            card.apply_action(action, show_buttons=show_buttons)
            if show_buttons:
                card.approve_requested.connect(self._on_approve)
                card.reject_requested.connect(self.reject_requested.emit)
                card.always_allow_requested.connect(self._on_always_allow)
            self._layout.insertWidget(insert_at + index, card)
            self._cards.append(card)

    def _on_always_allow(self) -> None:
        """Persist whitelist rules for pending kinds, then Approve."""
        for kind in _unique_kinds(self._actions):
            add_rule(kind)
        self._on_approve()

    def _on_approve(self) -> None:
        """Show immediate starting feedback before worker confirmation clears."""
        for card in self._cards:
            card.set_starting()
        for button in (self._allow_all, self._reject_all, self._always_all):
            button.setEnabled(False)
            button.setCursor(Qt.CursorShape.ArrowCursor)
        self.approve_requested.emit()


def _normalize_actions(payload: object) -> list[PendingActionDict]:
    """Coerce a worker payload into a list of action dicts."""
    if not isinstance(payload, dict):
        return []
    raw = payload.get("actions")
    if not isinstance(raw, list):
        return []
    out: list[PendingActionDict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool_name") or "")
        kind_raw = item.get("kind")
        kind = str(kind_raw) if kind_raw is not None else None
        title = str(item.get("title") or item.get("kind_label") or "").strip()
        detail = str(item.get("detail") or item.get("summary") or item.get("visualize") or "")
        url = str(item.get("url") or "").strip()
        risk = str(item.get("risk") or "normal").strip().lower() or "normal"
        row: PendingActionDict = {
            "tool_name": tool_name,
            "kind": kind,
            "title": title,
            "detail": detail,
            "summary": detail,
            "risk": risk,
        }
        if title:
            row["kind_label"] = title
        if url:
            row["url"] = url
        out.append(row)
    return out


def _unique_kinds(actions: list[PendingActionDict]) -> list[str]:
    """Return distinct non-empty kind strings from *actions*."""
    seen: set[str] = set()
    out: list[str] = []
    for action in actions:
        kind = action.get("kind")
        if not isinstance(kind, str):
            continue
        kind = kind.strip()
        if not kind or kind in seen:
            continue
        seen.add(kind)
        out.append(kind)
    return out


__all__ = ["PendingToolGroup"]
