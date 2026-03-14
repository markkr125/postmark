"""Wrapped multi-row request tab deck."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QKeyEvent, QMouseEvent, QResizeEvent, QWheelEvent
from PySide6.QtWidgets import QMenu, QSizePolicy, QTabBar, QWidget

from .labels import FolderTabLabel, TabLabel, layout_config
from .tab_button import TabButton

if TYPE_CHECKING:
    from ui.styling.tab_settings_manager import TabSettingsManager

_MAX_TOOLTIP_LEN = 300
_ROW_GAP = 2
_TAB_GAP = 2
_PADDING_X = 4
_PADDING_Y = 4
_MIN_SINGLE_ROW_WIDTH = 1


@dataclass
class _TabEntry:
    """Single tab entry tracked by the wrapped deck."""

    tab_type: str
    button: TabButton
    label: TabLabel | FolderTabLabel
    path: str | None = None


class RequestTabBar(QWidget):
    """Wrapped multi-row top tab deck with a QTabBar-like compatibility API."""

    currentChanged = Signal(int)
    tabCloseRequested = Signal(int)
    tab_close_requested = Signal(int)
    tab_double_clicked = Signal(int)
    new_tab_requested = Signal()
    close_others_requested = Signal(int)
    close_all_requested = Signal()
    force_close_all_requested = Signal()
    tab_reordered = Signal(int, int)

    def __init__(
        self,
        tab_settings_manager: TabSettingsManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the wrapped tab deck."""
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._tab_settings_manager = tab_settings_manager
        self._entries: list[_TabEntry] = []
        self._current_index = -1
        self._tabs_closable = True
        self._hover_suppressed = False
        self._layout_height = layout_config(False).tab_height + (_PADDING_Y * 2)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tabCloseRequested.connect(self.tab_close_requested.emit)
        self._apply_settings()
        if self._tab_settings_manager is not None:
            self._tab_settings_manager.settings_changed.connect(self._apply_settings)

    def count(self) -> int:
        """Return the number of open tabs."""
        return len(self._entries)

    def currentIndex(self) -> int:
        """Return the current tab index, or ``-1`` when no tab is selected."""
        return self._current_index

    def setCurrentIndex(self, index: int) -> None:
        """Select the tab at the given index."""
        new_index = index if 0 <= index < self.count() else -1
        if new_index == self._current_index:
            return
        self._current_index = new_index
        self._sync_selection_styles()
        self.currentChanged.emit(new_index)

    def tabsClosable(self) -> bool:
        """Return whether tabs expose close affordances."""
        return self._tabs_closable

    def tabRect(self, index: int) -> QRect:
        """Return the geometry for the tab at the given index."""
        entry = self._entry(index)
        return entry.button.geometry() if entry is not None else QRect()

    def tabAt(self, point: QPoint) -> int:
        """Return the tab index at the given point, or ``-1`` when none matches."""
        for index, entry in enumerate(self._entries):
            if entry.button.geometry().contains(point):
                return index
        return -1

    def tabToolTip(self, index: int) -> str:
        """Return the tooltip for the tab at the given index."""
        entry = self._entry(index)
        return entry.button.toolTip() if entry is not None else ""

    def setTabToolTip(self, index: int, text: str) -> None:
        """Set the tooltip for the tab at the given index."""
        entry = self._entry(index)
        if entry is not None:
            entry.button.setToolTip(text)

    def tabButton(self, index: int, position: QTabBar.ButtonPosition):
        """Return the embedded label or close button for test compatibility."""
        entry = self._entry(index)
        if entry is None:
            return None
        if position == QTabBar.ButtonPosition.RightSide:
            return entry.button.close_button()
        if position == QTabBar.ButtonPosition.LeftSide:
            return entry.label
        return None

    def tab_search_text(self, index: int) -> str:
        """Return a human-readable tab label for search and jump actions."""
        entry = self._entry(index)
        if entry is None:
            return ""
        if entry.tab_type == "request" and isinstance(entry.label, TabLabel):
            text = f"{entry.label._method} {entry.label._name}"
        elif isinstance(entry.label, FolderTabLabel):
            text = f"Folder {entry.label._name}"
        else:
            text = ""
        if entry.path and entry.path not in text:
            return f"{text} - {entry.path}"
        return text

    def select_next_tab(self) -> None:
        """Activate the next tab, wrapping at the end of the deck."""
        self._cycle_current(1)

    def select_previous_tab(self) -> None:
        """Activate the previous tab, wrapping at the start of the deck."""
        self._cycle_current(-1)

    def refresh_theme(self) -> None:
        """Refresh button styling after a theme change."""
        for entry in self._entries:
            entry.button.refresh_style()
        self._sync_selection_styles()
        self.update()

    def add_request_tab(
        self,
        method: str,
        name: str,
        *,
        is_preview: bool = False,
        path: str | None = None,
        index: int | None = None,
    ) -> int:
        """Add a new tab for a request and return its index.

        Args:
            method: HTTP method badge text.
            name: Request name shown in the tab label.
            is_preview: Whether the tab uses preview styling.
            path: Full breadcrumb path used for duplicate disambiguation and hover text.
            index: Optional insertion index within the current deck.
        """
        label = TabLabel(
            method,
            name,
            is_preview=is_preview,
            compact=self._small_labels,
            mark_modified=self._mark_modified,
        )
        return self._insert_entry("request", label, path, index)

    def add_folder_tab(
        self,
        name: str,
        *,
        path: str | None = None,
        index: int | None = None,
    ) -> int:
        """Add a new tab for a folder and return its index.

        Args:
            name: Folder name shown in the tab label.
            path: Full breadcrumb path used for hover text.
            index: Optional insertion index within the current deck.
        """
        label = FolderTabLabel(
            name,
            compact=self._small_labels,
            mark_modified=self._mark_modified,
        )
        idx = self._insert_entry("folder", label, path, index)
        self._apply_tooltip(idx, name, path)
        return idx

    def update_tab(
        self,
        index: int,
        *,
        method: str | None = None,
        name: str | None = None,
        path: str | None = None,
        is_preview: bool | None = None,
        is_dirty: bool | None = None,
        is_sending: bool | None = None,
    ) -> None:
        """Update properties of an existing tab."""
        entry = self._entry(index)
        if entry is None:
            return

        if path is not None:
            entry.path = path
        if entry.tab_type == "request":
            request_label = entry.label
            assert isinstance(request_label, TabLabel)
            if method is not None:
                request_label.set_method(method)
            if name is not None:
                request_label.set_name(name)
            if is_preview is not None:
                request_label.set_preview(is_preview)
            if is_dirty is not None:
                request_label.set_dirty(is_dirty)
            if is_sending is not None:
                request_label.set_sending(is_sending)
            self._refresh_request_labels()
            return

        folder_label = entry.label
        assert isinstance(folder_label, FolderTabLabel)
        if name is not None:
            folder_label.set_name(name)
        if is_dirty is not None:
            folder_label.set_dirty(is_dirty)
        tooltip_name = name if name is not None else folder_label._name
        self._apply_tooltip(index, tooltip_name, entry.path)
        self._relayout_tabs()

    def remove_request_tab(self, index: int) -> None:
        """Remove a tab at the given index and clean up its widgets."""
        if not 0 <= index < self.count():
            return
        entry = self._entries.pop(index)
        entry.button.setParent(None)
        entry.button.deleteLater()

        if not self._entries:
            self._current_index = -1
        elif self._current_index > index:
            self._current_index -= 1
        elif self._current_index >= self.count():
            self._current_index = self.count() - 1

        self._reindex_entries()
        self._refresh_request_labels()
        self._relayout_tabs()
        self._sync_selection_styles()

    def move_tab(self, from_index: int, to_index: int) -> None:
        """Move a tab to a new position and emit the reorder signal."""
        if not 0 <= from_index < self.count() or not 0 <= to_index < self.count():
            return
        if from_index == to_index:
            return

        entry = self._entries.pop(from_index)
        self._entries.insert(to_index, entry)

        current_index = self._current_index
        new_current = current_index
        if current_index == from_index:
            new_current = to_index
        elif from_index < current_index <= to_index:
            new_current = current_index - 1
        elif to_index <= current_index < from_index:
            new_current = current_index + 1

        self._reindex_entries()
        self._refresh_request_labels()
        self._relayout_tabs()
        self.tab_reordered.emit(from_index, to_index)
        self._current_index = new_current
        self._sync_selection_styles()
        if new_current != current_index:
            self.currentChanged.emit(new_current)

    def tab_label(self, index: int) -> TabLabel | None:
        """Return the request-tab label widget for the given index, or ``None``."""
        entry = self._entry(index)
        if entry is None or entry.tab_type != "request":
            return None
        label = entry.label
        return label if isinstance(label, TabLabel) else None

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Reflow the tab chips whenever the deck width changes."""
        super().resizeEvent(event)
        self._relayout_tabs()

    def showEvent(self, event) -> None:  # type: ignore[override]
        """Lay out the current tabs when the deck becomes visible."""
        super().showEvent(event)
        self._relayout_tabs()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Promote preview tabs when the user double-clicks a chip body."""
        index = self.tabAt(event.position().toPoint())
        if index >= 0:
            self.tab_double_clicked.emit(index)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Close tabs on middle-click and select them on left-click."""
        index = self.tabAt(event.position().toPoint())
        if index >= 0 and event.button() == Qt.MouseButton.MiddleButton:
            self.tab_close_requested.emit(index)
            event.accept()
            return
        if index >= 0 and event.button() == Qt.MouseButton.LeftButton:
            self.setCurrentIndex(index)
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Support arrow-key tab traversal when the wrapped deck has focus."""
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.select_previous_tab()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.select_next_tab()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Home and self.count() > 0:
            self.setCurrentIndex(0)
            event.accept()
            return
        if event.key() == Qt.Key.Key_End and self.count() > 0:
            self.setCurrentIndex(self.count() - 1)
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Cycle through tabs on mouse wheel scroll."""
        if self.count() < 2:
            return
        for entry in self._entries:
            entry.button.suppress_hover()
        self._hover_suppressed = True
        delta = event.angleDelta().y()
        if delta > 0:
            self._cycle_current(-1)
        elif delta < 0:
            self._cycle_current(1)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Restore hover visuals after a wheel-scroll suppression."""
        if self._hover_suppressed:
            self._hover_suppressed = False
            for entry in self._entries:
                entry.button.restore_hover()
        super().mouseMoveEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Show the tab context menu when right-clicking the deck."""
        index = self.tabAt(event.pos())
        if index < 0:
            return
        self._show_context_menu(index, event.globalPos())
        event.accept()

    def sizeHint(self) -> QSize:  # type: ignore[override]
        """Return a size hint that tracks the wrapped deck height."""
        return QSize(max(240, self.width()), self._layout_height)

    def minimumSizeHint(self) -> QSize:  # type: ignore[override]
        """Return the minimum size for the wrapped deck."""
        return QSize(120, self._layout_height)

    def _insert_entry(
        self,
        tab_type: str,
        label: TabLabel | FolderTabLabel,
        path: str | None,
        index: int | None,
    ) -> int:
        """Insert a generic tab entry and return its index."""
        idx = self.count() if index is None or index >= self.count() else max(index, 0)
        button = TabButton(idx, label, self)
        button.clicked.connect(self.setCurrentIndex)
        button.close_requested.connect(self.tab_close_requested.emit)
        button.double_clicked.connect(self.tab_double_clicked.emit)
        button.reorder_requested.connect(self.move_tab)
        button.context_requested.connect(self._show_context_menu)
        button.show()

        self._entries.insert(
            idx, _TabEntry(tab_type=tab_type, button=button, label=label, path=path)
        )
        self._reindex_entries()
        self._refresh_request_labels()
        self._relayout_tabs()
        self._sync_selection_styles()
        return idx

    def _entry(self, index: int) -> _TabEntry | None:
        """Return the tab entry at the given index, or ``None``."""
        if 0 <= index < self.count():
            return self._entries[index]
        return None

    def _reindex_entries(self) -> None:
        """Synchronise chip indices after insert/remove/reorder."""
        for index, entry in enumerate(self._entries):
            entry.button.set_index(index)

    def _apply_tooltip(self, index: int, name: str, path: str | None) -> None:
        """Update the tooltip for the given tab according to settings."""
        tooltip = path if self._show_full_path_on_hover and path else name
        self.setTabToolTip(index, tooltip[:_MAX_TOOLTIP_LEN])

    @staticmethod
    def _short_path_label(path: str | None) -> str | None:
        """Return a compact parent-path label for duplicate request names."""
        if not path:
            return None
        parts = [part.strip() for part in path.split(" / ") if part.strip()]
        if len(parts) <= 1:
            return path
        return parts[-2]

    def _refresh_request_labels(self) -> None:
        """Refresh request label text and tooltips after name/settings changes."""
        counts: dict[str, int] = {}
        for entry in self._entries:
            if entry.tab_type == "request" and isinstance(entry.label, TabLabel):
                counts[entry.label._name] = counts.get(entry.label._name, 0) + 1

        for index, entry in enumerate(self._entries):
            if entry.tab_type != "request" or not isinstance(entry.label, TabLabel):
                if entry.tab_type == "folder" and isinstance(entry.label, FolderTabLabel):
                    self._apply_tooltip(index, entry.label._name, entry.path)
                continue
            display_name = entry.label._name
            if self._show_path_for_duplicates and counts.get(entry.label._name, 0) > 1:
                short_path = self._short_path_label(entry.path)
                if short_path:
                    display_name = f"{entry.label._name} ({short_path})"
            entry.label.set_display_name(display_name)
            self._apply_tooltip(index, entry.label._name, entry.path)
        self._relayout_tabs()

    def _apply_settings(self) -> None:
        """Refresh the wrapped deck rendering from the persisted tab settings."""
        self._small_labels = bool(
            self._tab_settings_manager.small_labels if self._tab_settings_manager else True
        )
        self._mark_modified = bool(
            self._tab_settings_manager.mark_modified if self._tab_settings_manager else True
        )
        self._wrap_mode = str(
            self._tab_settings_manager.wrap_mode if self._tab_settings_manager else "multiple_rows"
        )
        self._show_full_path_on_hover = bool(
            self._tab_settings_manager.show_full_path_on_hover
            if self._tab_settings_manager
            else True
        )
        self._show_path_for_duplicates = bool(
            self._tab_settings_manager.show_path_for_duplicates
            if self._tab_settings_manager
            else True
        )

        for entry in self._entries:
            entry.label.apply_config(compact=self._small_labels, mark_modified=self._mark_modified)
            entry.button.refresh_style()
        self._refresh_request_labels()
        self._sync_selection_styles()

    def _sync_selection_styles(self) -> None:
        """Update chip selection styling after the active index changes."""
        for index, entry in enumerate(self._entries):
            entry.button.set_selected(index == self._current_index)

    def _cycle_current(self, step: int) -> None:
        """Move the current index forward or backward, wrapping around."""
        count = self.count()
        if count <= 0:
            return
        current = self._current_index if self._current_index >= 0 else 0
        self.setCurrentIndex((current + step) % count)

    @staticmethod
    def _fit_single_row_widths(base_widths: list[int], available_width: int) -> list[int]:
        """Compress tab widths to fit a single visible row."""
        if not base_widths:
            return []
        if sum(base_widths) <= available_width:
            return base_widths

        total = sum(base_widths)
        scaled = [
            max(_MIN_SINGLE_ROW_WIDTH, (width * available_width) // total) for width in base_widths
        ]
        assigned = sum(scaled)
        remainder = available_width - assigned

        index = 0
        while remainder > 0:
            scaled[index % len(scaled)] += 1
            remainder -= 1
            index += 1

        index = 0
        while remainder < 0:
            target = index % len(scaled)
            if scaled[target] > _MIN_SINGLE_ROW_WIDTH:
                scaled[target] -= 1
                remainder += 1
            index += 1

        return scaled

    def _relayout_single_row(self) -> None:
        """Lay out every tab on a single compressed row."""
        content = self.contentsRect()
        available_width = max(1, content.width() - (_PADDING_X * 2))
        available_for_tabs = max(1, available_width - (_TAB_GAP * max(0, self.count() - 1)))
        base_widths = [entry.button.sizeHint().width() for entry in self._entries]
        widths = self._fit_single_row_widths(base_widths, available_for_tabs)
        row_height = max(entry.button.sizeHint().height() for entry in self._entries)

        x = content.x() + _PADDING_X
        y = content.y() + _PADDING_Y
        for entry, width in zip(self._entries, widths, strict=False):
            entry.button.setGeometry(x, y, width, row_height)
            x += width + _TAB_GAP

        total_height = y + row_height + _PADDING_Y
        if total_height != self._layout_height:
            self._layout_height = total_height
            self.setFixedHeight(total_height)
        self.updateGeometry()

    def _relayout_tabs(self) -> None:
        """Wrap the tab chips across multiple rows based on the current width."""
        if not self._entries:
            self._layout_height = layout_config(self._small_labels).tab_height + (_PADDING_Y * 2)
            self.setFixedHeight(self._layout_height)
            return

        if self._wrap_mode == "single_row":
            self._relayout_single_row()
            return

        content = self.contentsRect()
        available_width = max(1, content.width() - (_PADDING_X * 2))
        x = content.x() + _PADDING_X
        y = content.y() + _PADDING_Y
        row_height = 0
        row_start = x

        for entry in self._entries:
            hint = entry.button.sizeHint()
            width = min(max(hint.width(), 92), available_width)
            height = hint.height()
            if x > row_start and x + width > row_start + available_width:
                x = row_start
                y += row_height + _ROW_GAP
                row_height = 0
            entry.button.setGeometry(x, y, width, height)
            x += width + _TAB_GAP
            row_height = max(row_height, height)

        total_height = y + row_height + _PADDING_Y
        if total_height != self._layout_height:
            self._layout_height = total_height
            self.setFixedHeight(total_height)
        self.updateGeometry()

    def _show_context_menu(self, index: int, global_pos: QPoint) -> None:
        """Show the standard tab context menu for the given index."""
        menu = QMenu(self)
        close_act = menu.addAction("Close")
        close_others_act = menu.addAction("Close Others")
        close_all_act = menu.addAction("Close All")
        menu.addSeparator()
        force_close_all_act = menu.addAction("Force Close All")

        chosen = menu.exec(global_pos)
        if chosen == close_act:
            self.tab_close_requested.emit(index)
        elif chosen == close_others_act:
            self.close_others_requested.emit(index)
        elif chosen == close_all_act:
            self.close_all_requested.emit()
        elif chosen == force_close_all_act:
            self.force_close_all_requested.emit()
            self.force_close_all_requested.emit()
