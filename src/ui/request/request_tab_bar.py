"""Closeable tab bar for open requests with method badges and dirty indicators.

Each tab shows a short method badge (coloured), the request name, and
optionally a dirty marker.  Tabs can be closed, reordered by drag, and
display an italic style when in preview mode.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QSizePolicy, QTabBar, QWidget

from ui.theme import (
    BADGE_BORDER_RADIUS,
    BADGE_FONT_SIZE,
    BADGE_HEIGHT,
    BADGE_MIN_WIDTH,
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_SENDING,
    COLOR_TEXT,
    COLOR_WHITE,
    method_color,
    method_short_label,
)

# Dirty indicator bullet prefix
_DIRTY_BULLET = "\u2022 "

# Tab bar height
_TAB_HEIGHT = 30


class _TabLabel(QWidget):
    """Custom tab label with a method badge and request name."""

    def __init__(
        self,
        method: str = "GET",
        name: str = "",
        *,
        is_preview: bool = False,
        is_dirty: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the tab label with method badge and name."""
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        # Method badge
        self._badge = QLabel(method_short_label(method))
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedSize(BADGE_MIN_WIDTH, BADGE_HEIGHT)
        color = method_color(method)
        self._badge.setStyleSheet(
            f"background: {color}; color: {COLOR_WHITE};"
            f" font-size: {BADGE_FONT_SIZE}px; font-weight: bold;"
            f" border-radius: {BADGE_BORDER_RADIUS}px;"
            f" font-family: monospace;"
        )
        layout.addWidget(self._badge)

        # Request name
        self._name_label = QLabel(name)
        self._name_label.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 11px;")
        self._name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._name_label)

        self._method = method
        self._name = name
        self._is_preview = is_preview
        self._is_dirty = is_dirty
        self._is_sending = False

        # Sending spinner indicator
        self._spinner = QLabel("\u25cf")
        self._spinner.setStyleSheet(f"color: {COLOR_SENDING}; font-size: 10px; padding: 0;")
        self._spinner.hide()
        layout.addWidget(self._spinner)

        self._apply_style()

    def set_method(self, method: str) -> None:
        """Update the method badge."""
        self._method = method
        self._badge.setText(method_short_label(method))
        color = method_color(method)
        self._badge.setStyleSheet(
            f"background: {color}; color: {COLOR_WHITE};"
            f" font-size: {BADGE_FONT_SIZE}px; font-weight: bold;"
            f" border-radius: {BADGE_BORDER_RADIUS}px;"
            f" font-family: monospace;"
        )

    def set_name(self, name: str) -> None:
        """Update the request name."""
        self._name = name
        self._apply_style()

    def set_preview(self, preview: bool) -> None:
        """Toggle the preview (italic) style."""
        self._is_preview = preview
        self._apply_style()

    def set_dirty(self, dirty: bool) -> None:
        """Toggle the dirty indicator."""
        self._is_dirty = dirty
        self._apply_style()

    def set_sending(self, sending: bool) -> None:
        """Toggle the sending spinner indicator."""
        self._is_sending = sending
        self._spinner.setVisible(sending)

    def _apply_style(self) -> None:
        """Rebuild the display text and font style."""
        prefix = _DIRTY_BULLET if self._is_dirty else ""
        self._name_label.setText(f"{prefix}{self._name}")

        font = self._name_label.font()
        font.setItalic(self._is_preview)
        self._name_label.setFont(font)


class RequestTabBar(QTabBar):
    """Tab bar for open request tabs with method badges and dirty indicators.

    Signals:
        tab_close_requested(int): Emitted when a tab close button is clicked.
        tab_double_clicked(int): Emitted on double-click (promote preview).
        new_tab_requested(): Emitted when the "+" button is clicked (future).
    """

    tab_close_requested = Signal(int)
    tab_double_clicked = Signal(int)
    new_tab_requested = Signal()
    close_others_requested = Signal(int)
    close_all_requested = Signal()
    force_close_all_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the tab bar with close buttons and movable tabs."""
        super().__init__(parent)
        self.setMovable(True)
        self.setTabsClosable(True)
        self.setExpanding(False)
        self.setDrawBase(False)
        self.setDocumentMode(True)

        self.setStyleSheet(
            f"""
            QTabBar {{
                border-bottom: 1px solid {COLOR_BORDER};
            }}
            QTabBar::tab {{
                height: {_TAB_HEIGHT}px;
                padding: 0 12px;
                border: none;
                border-bottom: 2px solid transparent;
                background: transparent;
            }}
            QTabBar::tab:selected {{
                border-bottom: 2px solid {COLOR_ACCENT};
            }}
            QTabBar::tab:hover {{
                background: rgba(0, 0, 0, 0.04);
            }}
            QTabBar::close-button {{
                image: none;
                subcontrol-position: right;
                padding: 2px;
            }}
            """
        )

        self.tabCloseRequested.connect(self.tab_close_requested.emit)

        # Map tab index → _TabLabel for custom styling
        self._tab_labels: dict[int, _TabLabel] = {}

    # -- Public API ----------------------------------------------------

    def add_request_tab(
        self,
        method: str,
        name: str,
        *,
        is_preview: bool = False,
    ) -> int:
        """Add a new tab for a request and return its index.

        Args:
            method: HTTP method (for badge).
            name: Request name (displayed in tab).
            is_preview: Whether this tab is preview-only (italic).
        """
        label_widget = _TabLabel(method, name, is_preview=is_preview)
        idx = self.addTab("")
        self.setTabButton(idx, QTabBar.ButtonPosition.LeftSide, label_widget)
        self._tab_labels[idx] = label_widget
        return idx

    def update_tab(
        self,
        index: int,
        *,
        method: str | None = None,
        name: str | None = None,
        is_preview: bool | None = None,
        is_dirty: bool | None = None,
        is_sending: bool | None = None,
    ) -> None:
        """Update properties of an existing tab.

        Only the provided keyword arguments are changed.
        """
        label = self._tab_labels.get(index)
        if label is None:
            return
        if method is not None:
            label.set_method(method)
        if name is not None:
            label.set_name(name)
        if is_preview is not None:
            label.set_preview(is_preview)
        if is_dirty is not None:
            label.set_dirty(is_dirty)
        if is_sending is not None:
            label.set_sending(is_sending)

    def remove_request_tab(self, index: int) -> None:
        """Remove a tab at the given index and clean up its label."""
        self._tab_labels.pop(index, None)
        self.removeTab(index)
        # Re-index labels after removal
        new_labels: dict[int, _TabLabel] = {}
        for old_idx, label in self._tab_labels.items():
            new_idx = old_idx if old_idx < index else old_idx - 1
            new_labels[new_idx] = label
        self._tab_labels = new_labels

    def tab_label(self, index: int) -> _TabLabel | None:
        """Return the label widget for a tab, or ``None``."""
        return self._tab_labels.get(index)

    # -- Event overrides -----------------------------------------------

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Emit double-click signal for tab promotion."""
        index = self.tabAt(event.pos())
        if index >= 0:
            self.tab_double_clicked.emit(index)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        """Show right-click context menu with Close / Close Others / Close All."""
        index = self.tabAt(event.pos())
        if index < 0:
            return

        menu = QMenu(self)
        close_act = menu.addAction("Close")
        close_others_act = menu.addAction("Close Others")
        close_all_act = menu.addAction("Close All")
        menu.addSeparator()
        force_close_all_act = menu.addAction("Force Close All")

        chosen = menu.exec(event.globalPos())
        if chosen == close_act:
            self.tab_close_requested.emit(index)
        elif chosen == close_others_act:
            self.close_others_requested.emit(index)
        elif chosen == close_all_act:
            self.close_all_requested.emit()
        elif chosen == force_close_all_act:
            self.force_close_all_requested.emit()
