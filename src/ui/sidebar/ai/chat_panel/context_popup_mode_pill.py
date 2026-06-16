"""Segmented mode pill for the context usage flyout (Context / Cost)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton


class ContextPopupModePill(QPushButton):
    """Compact pill toggling context vs cost views inside ``AiChatContextUsagePopup``."""

    def __init__(self, label: str, parent=None) -> None:
        """Build one mode pill with *label*."""
        super().__init__(label, parent)
        self.setObjectName("aiChatContextPopupMode")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        """Mark this pill as the selected flyout mode."""
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)


__all__ = ["ContextPopupModePill"]
