"""Inline banner for inherited pre-request / post-response scripts."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.styling import theme
from ui.styling.theme import current_palette
from ui.styling.icons import phi


class InheritedScriptsBanner(QFrame):
    """Thin banner: inherited script count, ancestor names, and View chain.

    Hidden when there are no applicable ancestor scripts for this type.
    """

    view_chain_requested = Signal()

    def __init__(self, *, script_type: str, parent: QWidget | None = None) -> None:
        """Create a pre-request or post-response inherited-scripts banner row."""
        super().__init__(parent)
        self._script_type = script_type
        self.setObjectName("InheritedScriptsBanner")
        _input = current_palette()["input_bg"]
        self.setStyleSheet(
            f"QFrame#InheritedScriptsBanner {{"
            f" background-color: {_input};"
            f" border: 1px solid {theme.COLOR_ACCENT};"
            f" border-left: 3px solid {theme.COLOR_ACCENT};"
            f" border-radius: 4px;"
            f" margin-top: 0px;"
            f" margin-bottom: 10px;"
            f" }}"
            f"QFrame#InheritedScriptsBanner QLabel {{"
            f" color: {theme.COLOR_ACCENT};"
            f" }}"
            f"QPushButton#inheritedViewChainBtn {{"
            f" padding: 4px 10px;"
            f" border: 1px solid {theme.COLOR_ACCENT};"
            f" border-radius: 3px;"
            f" color: {theme.COLOR_ACCENT};"
            f" background: transparent;"
            f" }}"
            f"QPushButton#inheritedViewChainBtn:hover {{"
            f" background: {theme.COLOR_ACCENT};"
            f" color: {theme.COLOR_WHITE};"
            f" }}"
        )

        outer = QVBoxLayout(self)
        # Tight under the toolbars above; a little inner top padding for the border; space below the bar.
        outer.setContentsMargins(10, 4, 10, 8)
        outer.setSpacing(2)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._icon = QLabel()
        self._icon.setPixmap(
            phi("tree-structure", size=16, color=theme.COLOR_ACCENT).pixmap(16, 16)
        )
        row.addWidget(self._icon)

        self._text = QLabel("")
        self._text.setWordWrap(True)
        row.addWidget(self._text, 1)

        self._view_btn = QPushButton("View chain")
        self._view_btn.setObjectName("inheritedViewChainBtn")
        self._view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view_btn.clicked.connect(self.view_chain_requested.emit)
        row.addWidget(self._view_btn)

        outer.addLayout(row)

        self.setAccessibleName("Inherited scripts")
        self._text.setAccessibleName("Inherited scripts summary")
        self._view_btn.setAccessibleName("View inherited script chain")
        self._view_btn.setToolTip("View inherited scripts and per-request disable options")
        self.setVisible(False)

    def set_inherited_info(self, count: int, name_snippet: str) -> None:
        """Show the banner, or hide when *count* is 0.

        *name_snippet* is a trimmed human-readable list of collection names
        (e.g. "Auth, Users API").
        """
        if count <= 0:
            self.setVisible(False)
            return
        kind = "pre-request" if self._script_type == "pre_request" else "post-response"
        if count == 1:
            msg = f"This request inherits 1 {kind} script from {name_snippet}."
        else:
            msg = f"This request inherits {count} {kind} scripts from {name_snippet}."
        self._text.setText(msg)
        self.setVisible(True)
        self._text.setToolTip(name_snippet)
