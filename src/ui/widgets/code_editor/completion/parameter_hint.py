"""Floating parameter-info hint for script editor method calls (JetBrains-style)."""

from __future__ import annotations

import html

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFocusEvent, QGuiApplication
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


def format_signature_rich(signature: str, active_index: int) -> str:
    """Return HTML for *signature* with the *active_index* parameter highlighted.

    Active parameter is wrapped in ``<b>`` and tinted with the theme accent
    colour so it stands out against the muted ones.
    """
    from ui.styling.theme import COLOR_ACCENT

    sig = signature.strip()
    if not (sig.startswith("(") and sig.endswith(")")):
        return html.escape(sig)
    inner = sig[1:-1]
    depth = 0
    start = 0
    parts: list[str] = []
    for i, c in enumerate(inner):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(inner[start:i].strip())
            start = i + 1
    parts.append(inner[start:].strip())
    if not parts or parts == [""]:
        return html.escape(sig)
    if active_index < 0:
        active_index = 0
    if active_index >= len(parts):
        active_index = len(parts) - 1
    out: list[str] = []
    for i, p in enumerate(parts):
        esc = html.escape(p)
        if i == active_index and esc:
            out.append(f"<b style='color:{COLOR_ACCENT}'>{esc}</b>")
        else:
            out.append(esc)
    return "(" + ", ".join(out) + ")"


class ParameterHintPopup(QFrame):
    """Frameless tooltip showing the active call's parameter signature."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Match completion popup window flags; do not steal focus."""
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setObjectName("parameterHintPopup")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self._label = QLabel()
        self._label.setObjectName("parameterHintPopupLabel")
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        lay.addWidget(self._label)

    def show_hint(
        self,
        global_anchor_top_left: QPoint,
        signature_html: str,
        line_height: int = 0,
    ) -> None:
        """Place the hint near *global_anchor_top_left* and show *signature_html*.

        Prefers placement above the cursor (JetBrains-style); falls back below
        when there is not enough room above. *line_height* is the cursor row
        height used for the below-fallback offset.
        """
        self._label.setText(signature_html)
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self.adjustSize()
        w = max(self._label.sizeHint().width() + 24, 280)
        h = self._label.sizeHint().height() + 16
        self.resize(w, h)
        screen = QGuiApplication.screenAt(global_anchor_top_left)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        sr = screen.availableGeometry() if screen else None
        x = global_anchor_top_left.x()
        above_y = global_anchor_top_left.y() - self.height() - 4
        below_y = global_anchor_top_left.y() + max(line_height, 14) + 4
        y = below_y if sr is not None and above_y < sr.top() else above_y
        if sr is not None:
            x = max(sr.left(), min(x, sr.right() - self.width()))
            y = max(sr.top(), min(y, sr.bottom() - self.height()))
        self.move(x, y)
        self.show()
        self.raise_()

    def hide_hint(self) -> None:
        """Hide the popup."""
        self.hide()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        """Hide when focus genuinely leaves the popup."""
        super().focusOutEvent(event)
        self.hide_hint()
