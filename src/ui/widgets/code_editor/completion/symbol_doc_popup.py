"""Floating quick-documentation popup for hovered or focused identifiers.

Shown by Ctrl+hover and Ctrl+Q. Mirrors :class:`ParameterHintPopup`
window flags so it never steals focus from the editor.
"""

from __future__ import annotations

import html
from typing import NamedTuple

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFocusEvent, QGuiApplication
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class SymbolDoc(NamedTuple):
    """Resolved symbol information rendered in the popup."""

    label: str
    kind: str
    type_str: str
    doc: str
    signature: str
    origin: str


def _accent() -> str:
    """Return the current theme accent colour as a hex string."""
    from ui.styling.theme import COLOR_ACCENT

    return COLOR_ACCENT


def format_symbol_rich(sym: SymbolDoc) -> str:
    """Build the HTML payload shown in the popup body."""
    accent = _accent()
    label_html = f"<span style='font-weight:600;font-size:13px;'>{html.escape(sym.label)}</span>"
    if sym.signature:
        sig = sym.signature.strip()
        if sig.startswith("(") and sig.endswith(")"):
            inner = sig[1:-1]
            params = [p.strip() for p in inner.split(",") if p.strip()]
            inner_html = ", ".join(
                f"<span style='color:{accent}'>{html.escape(p)}</span>" for p in params
            )
            label_html += f"({inner_html})"
        else:
            label_html += html.escape(sig)
    head_parts = [label_html]
    if sym.type_str:
        head_parts.append(
            f"<span style='font-size:11px;'>&rarr; {html.escape(sym.type_str)}</span>"
        )
    body_lines = ["&nbsp;&nbsp;".join(head_parts)]
    if sym.doc:
        body_lines.append(f"<span style='font-size:11px;'>{html.escape(sym.doc)}</span>")
    if sym.origin and sym.origin != "pm API":
        body_lines.append(
            f"<span style='font-size:10px;opacity:0.7;'>{html.escape(sym.origin)}</span>"
        )
    return "<br>".join(body_lines)


class SymbolDocPopup(QFrame):
    """Frameless quick-doc tooltip used by Ctrl+hover and Ctrl+Q."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the popup with non-activating tool-window flags."""
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setObjectName("symbolDocPopup")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self._label = QLabel()
        self._label.setObjectName("symbolDocPopupLabel")
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        lay.addWidget(self._label)

    def show_for(self, anchor_global: QPoint, sym: SymbolDoc) -> None:
        """Render *sym* and place the popup just below *anchor_global*."""
        self._label.setText(format_symbol_rich(sym))
        self.adjustSize()
        w = max(self._label.sizeHint().width() + 24, 280)
        h = self._label.sizeHint().height() + 16
        self.resize(w, h)
        screen = QGuiApplication.screenAt(anchor_global)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        sr = screen.availableGeometry() if screen else None
        x = anchor_global.x()
        y = anchor_global.y() + 18
        if sr is not None:
            x = max(sr.left(), min(x, sr.right() - self.width()))
            y = max(sr.top(), min(y, sr.bottom() - self.height()))
        self.move(x, y)
        self.show()
        self.raise_()

    def hide_popup(self) -> None:
        """Hide the popup (no-op when already hidden)."""
        self.hide()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        """Hide when focus genuinely leaves the popup."""
        super().focusOutEvent(event)
        self.hide_popup()
