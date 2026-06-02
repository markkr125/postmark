"""Replayed-send banner shown in the response viewer status corner."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from ui.styling.icons import phi
from ui.styling.theme import COLOR_ACCENT
from ui.widgets.info_popup import ClickableLabel


class ResponseReplayIndicator(QFrame):
    """Compact pill: replay icon, label, and link to the source history row."""

    link_clicked = Signal(int)

    def __init__(self, parent: QFrame | None = None) -> None:
        """Build the indicator (hidden until a replay source is set)."""
        super().__init__(parent)
        self.setObjectName("responseReplayIndicator")
        self._entry_id: int | None = None

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 3, 10, 3)
        row.setSpacing(6)

        icon = QLabel()
        icon.setPixmap(phi("arrow-clockwise", color=COLOR_ACCENT).pixmap(14, 14))
        icon.setFixedSize(14, 14)
        row.addWidget(icon)

        prefix = QLabel("Replayed request")
        prefix.setObjectName("responseReplayPrefix")
        row.addWidget(prefix)

        self._link = ClickableLabel("View in history")
        self._link.setObjectName("responseReplayLink")
        self._link.setToolTip("Open History and select this send")
        self._link.clicked.connect(self._on_link_clicked)
        row.addWidget(self._link)

        self.hide()

    def set_source(self, entry_id: int, link_text: str) -> None:
        """Show the indicator for history row *entry_id*."""
        self._entry_id = entry_id
        self._link.setText(link_text)
        self.show()

    def clear_source(self) -> None:
        """Hide the indicator."""
        self._entry_id = None
        self.hide()

    def _on_link_clicked(self) -> None:
        if self._entry_id is not None:
            self.link_clicked.emit(self._entry_id)


__all__ = ["ResponseReplayIndicator"]
