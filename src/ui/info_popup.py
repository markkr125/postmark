"""Reusable click-triggered popup and clickable label widgets.

``InfoPopup`` is a lightweight floating frame positioned below an anchor
widget.  It closes on Escape, when the user clicks outside, or when the
parent window moves/resizes.  Uses ``Qt.WindowType.Tool`` so that
external screenshot utilities can still capture it.

``ClickableLabel`` is a ``QLabel`` subclass that emits a ``clicked``
signal on mouse press and shows a pointing-hand cursor.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from ui.icons import phi

# Grace period (seconds) after show_below() during which the event
# filter ignores mouse presses.  Prevents the opening click from
# immediately closing the popup.
_SHOW_GRACE_SEC = 0.15


class InfoPopup(QFrame):
    """Floating popup frame positioned below an anchor widget.

    Subclass or compose to add custom content.  The internal layout
    is a ``QVBoxLayout`` accessible via :pyattr:`content_layout`.

    Uses ``Tool | FramelessWindowHint`` instead of ``Popup`` so that
    external screenshot tools can capture the window.

    Inherits ``QFrame`` so that QSS ``border`` renders reliably on
    frameless top-level windows.  Styling comes from the global QSS
    rule targeting ``objectName="infoPopup"``.  The popup auto-closes
    when the parent window moves or resizes.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the popup with frameless tool-window flags."""
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setObjectName("infoPopup")

        self._content_layout = QVBoxLayout(self)
        self._content_layout.setContentsMargins(12, 10, 12, 10)
        self._content_layout.setSpacing(6)

        self._show_time: float = 0.0

    @property
    def content_layout(self) -> QVBoxLayout:
        """Return the internal vertical layout for adding content."""
        return self._content_layout

    # -- Copy helpers --------------------------------------------------

    def _make_header_with_copy(
        self,
        title_text: str,
    ) -> tuple[QHBoxLayout, QPushButton]:
        """Create a header row with *title_text* and a Copy button.

        Returns the layout and button so the caller can connect the
        button's ``clicked`` signal to a copy slot.
        """
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        title = QLabel(title_text)
        title.setObjectName("infoPopupTitle")
        row.addWidget(title)
        row.addStretch()

        btn = QPushButton(" Copy")
        btn.setIcon(phi("clipboard"))
        btn.setToolTip("Copy as Markdown")
        btn.setObjectName("flatMutedButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(btn)
        return row, btn

    def _copy_to_clipboard(self, text: str, btn: QPushButton) -> None:
        """Copy *text* to the system clipboard and flash *btn* feedback."""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        original_text = btn.text()
        btn.setText(" Copied!")
        btn.setIcon(phi("check"))

        def _restore() -> None:
            btn.setText(original_text)
            btn.setIcon(phi("clipboard"))

        QTimer.singleShot(1200, _restore)

    # -- Positioning ---------------------------------------------------

    def show_below(self, anchor: QWidget) -> None:
        """Position the popup below *anchor* and show it.

        If the popup would extend beyond the bottom of the screen,
        it is shown above the anchor instead.  All child ``QLabel``
        widgets are made text-selectable automatically.
        """
        # Make every label selectable so users can copy values.
        for label in self.findChildren(QLabel):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

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
        self._show_time = time.monotonic()
        self.show()
        self.activateWindow()
        self.setFocus()
        # Install app-wide event filter to catch clicks outside
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    # -- Dismiss behaviour --------------------------------------------

    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:  # type: ignore[override]
        """Close on click-outside or parent window move/resize.

        A short grace period after :meth:`show_below` prevents the
        opening click itself from immediately dismissing the popup.
        """
        etype = event.type()

        # Close when any top-level window (other than us) moves or resizes.
        if (
            etype in (QEvent.Type.Move, QEvent.Type.Resize)
            and obj is not self
            and hasattr(obj, "isWindow")
            and obj.isWindow()  # type: ignore[union-attr]
        ):
            self.close()
            return False

        if etype == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            # Ignore clicks that arrive within the grace period after show.
            if time.monotonic() - self._show_time < _SHOW_GRACE_SEC:
                return False
            if not self.geometry().contains(event.globalPosition().toPoint()):
                self.close()
                return False

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Close on Escape key."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        """Remove the event filter when the popup closes."""
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)  # type: ignore[arg-type]


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
