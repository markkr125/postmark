"""Compact toolbar button signalling inherited pre-request / post-response scripts."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QEnterEvent, QIcon
from PySide6.QtWidgets import QPushButton, QWidget

from ui.styling import theme
from ui.styling.icons import phi


class InheritedScriptsBanner(QPushButton):
    """Slim "View Chain (N)" button that lives on the script editor toolbar.

    Hidden when there are no applicable ancestor scripts for this type.
    Tooltip carries the count + ancestor names.
    """

    view_chain_requested = Signal()

    def __init__(self, *, script_type: str, parent: QWidget | None = None) -> None:
        """Create a pre-request or post-response inherited-scripts button."""
        super().__init__(parent)
        self._script_type = script_type
        size = 14
        # Qt doesn't auto-swap a QPushButton's icon on hover, so cache both
        # tints and switch in enterEvent / leaveEvent below.
        self._icon_normal: QIcon = phi("tree-structure", size=size, color=theme.COLOR_ACCENT)
        self._icon_hover: QIcon = phi("tree-structure", size=size, color=theme.COLOR_WHITE)
        self.setObjectName("inheritedViewChainBtn")
        self.setIcon(self._icon_normal)
        self.setText("View Chain")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton#inheritedViewChainBtn {{"
            f" padding: 3px 10px;"
            f" border: 1px solid {theme.COLOR_ACCENT};"
            f" border-radius: 3px;"
            f" color: {theme.COLOR_ACCENT};"
            f" background: transparent;"
            f" font-size: 11px;"
            f" }}"
            f"QPushButton#inheritedViewChainBtn:hover {{"
            f" background: {theme.COLOR_ACCENT};"
            f" color: {theme.COLOR_WHITE};"
            f" }}"
        )
        self.clicked.connect(self.view_chain_requested.emit)
        self.setAccessibleName("View inherited script chain")
        self.setToolTip("View inherited scripts and per-request disable options")
        self.setVisible(False)

    def enterEvent(self, event: QEnterEvent) -> None:
        """Switch the icon to white when the cursor enters the button."""
        self.setIcon(self._icon_hover)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """Restore the accent-coloured icon when the cursor leaves."""
        self.setIcon(self._icon_normal)
        super().leaveEvent(event)

    def set_inherited_info(self, count: int, name_snippet: str) -> None:
        """Show the button, or hide when *count* is 0.

        *name_snippet* is a trimmed human-readable list of collection names
        (e.g. "Auth, Users API").
        """
        if count <= 0:
            self.setVisible(False)
            return
        kind = "pre-request" if self._script_type == "pre_request" else "post-response"
        if count == 1:
            tip = f"This request inherits 1 {kind} script from {name_snippet}."
        else:
            tip = f"This request inherits {count} {kind} scripts from {name_snippet}."
        self.setText(f"View Chain ({count})")
        self.setToolTip(tip)
        self.setVisible(True)
