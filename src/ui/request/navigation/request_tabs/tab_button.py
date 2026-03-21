"""Interactive chip widget used by the wrapped request-tab deck."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QWidget

from ui.styling import theme as ui_theme

if TYPE_CHECKING:
    from .bar import RequestTabBar

_BUTTON_PADDING = 18
_MIN_TAB_WIDTH = 92


class TabButton(QFrame):
    """Interactive chip that hosts a tab label widget and close button."""

    clicked = Signal(int)
    close_requested = Signal(int)
    double_clicked = Signal(int)
    reorder_requested = Signal(int, int)
    context_requested = Signal(int, QPoint)

    def __init__(self, index: int, label_widget: QWidget, parent: QWidget | None = None) -> None:
        """Initialise the tab chip around a label widget."""
        super().__init__(parent)
        self._index = index
        self._label_widget = label_widget
        self._selected = False
        self._hovered = False
        self._hover_suppressed = False
        self._press_pos: QPoint | None = None
        self._drag_active = False

        self.setMouseTracking(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 4, 3)
        layout.setSpacing(6)
        layout.addWidget(label_widget, 1)

        self._close_button = QToolButton(self)
        self._close_button.setText("\u00d7")
        self._close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_button.setAutoRaise(True)
        self._close_button.setFixedSize(18, 18)
        self._close_button.clicked.connect(self._emit_close_requested)
        layout.addWidget(self._close_button)

        self.refresh_style()

    def set_index(self, index: int) -> None:
        """Update the chip index after insert/remove/reorder."""
        self._index = index

    def set_selected(self, selected: bool) -> None:
        """Update selected state and refresh the chip style."""
        self._selected = selected
        self.refresh_style()

    def close_button(self) -> QToolButton:
        """Return the close button for compatibility with old tests."""
        return self._close_button

    def label_widget(self) -> QWidget:
        """Return the embedded label widget."""
        return self._label_widget

    def refresh_style(self) -> None:
        """Refresh dynamic per-state styling from the active palette."""
        background = "transparent"
        border = ui_theme.COLOR_BORDER
        text = ui_theme.COLOR_TEXT_MUTED
        bottom_width = "1px"
        bottom_border = ui_theme.COLOR_BORDER
        if self._selected:
            background = ui_theme.COLOR_SELECTED_BG
            text = ui_theme.COLOR_TEXT
            bottom_width = "2px"
            bottom_border = ui_theme.COLOR_ACCENT
        elif self._hovered:
            background = ui_theme.COLOR_SELECTED_BG
            text = ui_theme.COLOR_TEXT

        self.setStyleSheet(
            "TabButton {"
            f"background: {background};"
            f"border: 1px solid {border};"
            f"border-bottom: {bottom_width} solid {bottom_border};"
            "border-radius: 4px;"
            "}"
        )
        self._close_button.setStyleSheet(
            "QToolButton {"
            "background: transparent;"
            "border: none;"
            f"color: {text};"
            "font-size: 13px;"
            "font-weight: bold;"
            "}"
            f"QToolButton:hover {{ color: {ui_theme.COLOR_TEXT}; }}"
        )

    def sizeHint(self):  # type: ignore[override]
        """Return a stable chip size for wrapped-row layout."""
        hint = super().sizeHint()
        return hint.expandedTo(self.minimumSizeHint())

    def minimumSizeHint(self):  # type: ignore[override]
        """Return a compact minimum size that still fits the controls."""
        label_hint = self._label_widget.sizeHint()
        close_hint = self._close_button.sizeHint()
        width = max(_MIN_TAB_WIDTH, label_hint.width() + close_hint.width() + _BUTTON_PADDING)
        height = max(label_hint.height(), close_hint.height()) + 8
        from PySide6.QtCore import QSize

        return QSize(width, height)

    def _emit_close_requested(self) -> None:
        """Emit the tab-close signal for the current chip index."""
        self.close_requested.emit(self._index)

    def _parent_bar(self) -> RequestTabBar | None:
        """Return the parent wrapped tab deck when present."""
        parent = self.parentWidget()
        if parent is not None and parent.metaObject().className() == "RequestTabBar":
            return cast("RequestTabBar", parent)
        return None

    def suppress_hover(self) -> None:
        """Suppress the hover visual until the mouse moves again."""
        self._hover_suppressed = True
        if self._hovered:
            self._hovered = False
            self.refresh_style()

    def restore_hover(self) -> None:
        """Re-enable hover visuals after suppression."""
        self._hover_suppressed = False

    def enterEvent(self, event) -> None:  # type: ignore[override]
        """Refresh hover state when the cursor enters the chip."""
        if not self._hover_suppressed:
            self._hovered = True
            self.refresh_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        """Refresh hover state when the cursor leaves the chip."""
        self._hovered = False
        self.refresh_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Select the tab on left click and close it on middle click."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self.close_requested.emit(self._index)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._drag_active = False
            self.clicked.emit(self._index)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Mark the interaction as a drag once the cursor passes the threshold."""
        if (
            self._press_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and (event.position().toPoint() - self._press_pos).manhattanLength() >= 8
        ):
            self._drag_active = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Emit a reorder request when a drag ends above another tab."""
        if event.button() == Qt.MouseButton.LeftButton and self._drag_active:
            parent = self._parent_bar()
            if parent is not None:
                drop_pos = parent.mapFromGlobal(event.globalPosition().toPoint())
                target = parent.tabAt(drop_pos)
                if target >= 0 and target != self._index:
                    self.reorder_requested.emit(self._index, target)
        self._press_pos = None
        self._drag_active = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Promote preview tabs on double click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self._index)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Delegate the context menu request back to the wrapped tab deck."""
        self.context_requested.emit(self._index, event.globalPos())
        event.accept()
