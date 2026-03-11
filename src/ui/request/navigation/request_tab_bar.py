"""Closeable tab bar for open requests with method badges and dirty indicators.

Each tab shows a short method badge (coloured), the request name, and
optionally a dirty marker.  Tabs can be closed, reordered by drag, and
display an italic style when in preview mode.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics, QMouseEvent
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMenu, QSizePolicy,
                               QTabBar, QWidget)

from ui.styling.icons import phi
from ui.styling.theme import (BADGE_BORDER_RADIUS, BADGE_FONT_SIZE,
                              BADGE_HEIGHT, BADGE_MIN_WIDTH, COLOR_SENDING,
                              COLOR_WHITE, method_color, method_short_label)

# Dirty indicator bullet prefix
_DIRTY_BULLET = "\u2022 "

# Tab bar height
_TAB_HEIGHT = 30

# Maximum display width for tab name labels (pixels)
_MAX_NAME_WIDTH = 180

# Maximum length for the tooltip (characters)
_MAX_TOOLTIP_LEN = 300


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
        self._badge.setObjectName("methodBadge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedSize(BADGE_MIN_WIDTH, BADGE_HEIGHT)
        self._apply_badge_color(method_color(method))
        layout.addWidget(self._badge)

        # Request name
        self._name_label = QLabel(name)
        self._name_label.setMaximumWidth(_MAX_NAME_WIDTH)
        self._name_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
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

    def _apply_badge_color(self, color: str) -> None:
        """Set the badge background colour (dynamic per-method)."""
        self._badge.setStyleSheet(
            f"background: {color}; color: {COLOR_WHITE};"
            f" font-size: {BADGE_FONT_SIZE}px; font-weight: bold;"
            f" border-radius: {BADGE_BORDER_RADIUS}px;"
            f" font-family: monospace;"
        )

    def set_method(self, method: str) -> None:
        """Update the method badge."""
        self._method = method
        self._badge.setText(method_short_label(method))
        self._apply_badge_color(method_color(method))

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
        full_text = f"{prefix}{self._name}"

        # Elide text if it exceeds the max width
        metrics = QFontMetrics(self._name_label.font())
        elided = metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, _MAX_NAME_WIDTH)
        self._name_label.setText(elided)

        font = self._name_label.font()
        font.setItalic(self._is_preview)
        self._name_label.setFont(font)


class _FolderTabLabel(QWidget):
    """Custom tab label for folder tabs with a folder icon and name."""

    def __init__(
        self,
        name: str = "",
        *,
        is_dirty: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the folder tab label with icon and name."""
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        # Folder icon
        self._icon_label = QLabel()
        icon = phi("folder-simple")
        self._icon_label.setPixmap(icon.pixmap(BADGE_HEIGHT, BADGE_HEIGHT))
        self._icon_label.setFixedSize(BADGE_MIN_WIDTH, BADGE_HEIGHT)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon_label)

        # Folder name
        self._name_label = QLabel(name)
        self._name_label.setMaximumWidth(_MAX_NAME_WIDTH)
        self._name_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._name_label)

        self._name = name
        self._is_dirty = is_dirty

        self._apply_style()

    def set_name(self, name: str) -> None:
        """Update the folder name."""
        self._name = name
        self._apply_style()

    def set_dirty(self, dirty: bool) -> None:
        """Toggle the dirty indicator."""
        self._is_dirty = dirty
        self._apply_style()

    def _apply_style(self) -> None:
        """Rebuild the display text from current state."""
        prefix = _DIRTY_BULLET if self._is_dirty else ""
        full_text = f"{prefix}{self._name}"

        metrics = QFontMetrics(self._name_label.font())
        elided = metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, _MAX_NAME_WIDTH)
        self._name_label.setText(elided)


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

        self.tabCloseRequested.connect(self.tab_close_requested.emit)

        # Map tab index -> custom label widget (_TabLabel or _FolderTabLabel)
        self._tab_labels: dict[int, _TabLabel] = {}
        self._folder_labels: dict[int, _FolderTabLabel] = {}

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
        self.setTabToolTip(idx, name[:_MAX_TOOLTIP_LEN])
        self._tab_labels[idx] = label_widget
        return idx

    def add_folder_tab(self, name: str) -> int:
        """Add a new tab for a folder and return its index.

        Args:
            name: Folder name (displayed in tab).
        """
        label_widget = _FolderTabLabel(name)
        idx = self.addTab("")
        self.setTabButton(idx, QTabBar.ButtonPosition.LeftSide, label_widget)
        self.setTabToolTip(idx, name[:_MAX_TOOLTIP_LEN])
        self._folder_labels[idx] = label_widget
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

        Only the provided keyword arguments are changed.  Works for both
        request tabs and folder tabs.
        """
        # 1. Try request tab label
        label = self._tab_labels.get(index)
        if label is not None:
            if method is not None:
                label.set_method(method)
            if name is not None:
                label.set_name(name)
                self.setTabToolTip(index, name[:_MAX_TOOLTIP_LEN])
            if is_preview is not None:
                label.set_preview(is_preview)
            if is_dirty is not None:
                label.set_dirty(is_dirty)
            if is_sending is not None:
                label.set_sending(is_sending)
            return

        # 2. Try folder tab label
        folder_label = self._folder_labels.get(index)
        if folder_label is not None:
            if name is not None:
                folder_label.set_name(name)
                self.setTabToolTip(index, name[:_MAX_TOOLTIP_LEN])
            if is_dirty is not None:
                folder_label.set_dirty(is_dirty)

    def remove_request_tab(self, index: int) -> None:
        """Remove a tab at the given index and clean up its label."""
        self._tab_labels.pop(index, None)
        self._folder_labels.pop(index, None)
        self.removeTab(index)
        # Re-index labels after removal
        new_labels: dict[int, _TabLabel] = {}
        for old_idx, label in self._tab_labels.items():
            new_idx = old_idx if old_idx < index else old_idx - 1
            new_labels[new_idx] = label
        self._tab_labels = new_labels

        new_folder_labels: dict[int, _FolderTabLabel] = {}
        for old_idx, flabel in self._folder_labels.items():
            new_idx = old_idx if old_idx < index else old_idx - 1
            new_folder_labels[new_idx] = flabel
        self._folder_labels = new_folder_labels

    def tab_label(self, index: int) -> _TabLabel | None:
        """Return the label widget for a tab, or ``None``."""
        return self._tab_labels.get(index)

    # -- Event overrides -----------------------------------------------

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Emit double-click signal for tab promotion."""
        index = self.tabAt(event.position().toPoint())
        if index >= 0:
            self.tab_double_clicked.emit(index)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Close tab on middle-click."""
        if event.button() == Qt.MouseButton.MiddleButton:
            index = self.tabAt(event.position().toPoint())
            if index >= 0:
                self.tab_close_requested.emit(index)
                return
        super().mousePressEvent(event)

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
