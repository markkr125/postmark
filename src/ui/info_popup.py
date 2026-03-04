"""Reusable click-triggered popup and clickable label widgets.

``InfoPopup`` is a lightweight floating frame positioned below an anchor
widget.  It auto-dismisses on click-outside or Escape thanks to the
``Qt.WindowType.Popup`` flag.

``ClickableLabel`` is a ``QLabel`` subclass that emits a ``clicked``
signal on mouse press and shows a pointing-hand cursor.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class InfoPopup(QWidget):
    """Floating popup frame positioned below an anchor widget.

    Subclass or compose to add custom content.  The internal layout
    is a ``QVBoxLayout`` accessible via :pyattr:`content_layout`.

    Style via ``setObjectName("infoPopup")`` — the global QSS rule
    provides background, border, border-radius, and padding.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the popup with frameless window flags."""
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setObjectName("infoPopup")

        self._content_layout = QVBoxLayout(self)
        self._content_layout.setContentsMargins(12, 10, 12, 10)
        self._content_layout.setSpacing(6)

    @property
    def content_layout(self) -> QVBoxLayout:
        """Return the internal vertical layout for adding content."""
        return self._content_layout

    def show_below(self, anchor: QWidget) -> None:
        """Position the popup below *anchor* and show it.

        If the popup would extend beyond the bottom of the screen,
        it is shown above the anchor instead.
        """
        self.adjustSize()
        global_pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        screen = anchor.screen()
        if screen is not None:
            screen_rect = screen.availableGeometry()
            if global_pos.y() + self.sizeHint().height() > screen_rect.bottom():
                # Show above the anchor
                global_pos = anchor.mapToGlobal(anchor.rect().topLeft())
                global_pos.setY(global_pos.y() - self.sizeHint().height())
        self.move(global_pos)
        self.show()


class ClickableLabel(QLabel):
    """``QLabel`` that emits :pyattr:`clicked` on mouse press.

    Sets a pointing-hand cursor so users know it is interactive.
    """

    clicked = Signal()

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the label with *text* and pointing-hand cursor."""
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit ``clicked`` on left-button press."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
