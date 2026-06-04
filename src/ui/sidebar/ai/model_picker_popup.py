"""Cursor-style model picker popover for the AI chat composer.

A frameless ``Tool`` window (singleton) anchored to the model button. It
shows a search field, a scrollable list of enabled models grouped by provider
(bold provider header, indented model rows), and a trailing **Manage models**
link that opens Settings -> AI -> Models.

Window flags mirror :class:`ui.widgets.snippets.popup.SnippetsPopup`:
``Tool`` (no taskbar entry), ``FramelessWindowHint`` (compact card styled by
global QSS), and ``WindowStaysOnTopHint`` (stays above the composer). The
popover dismisses on Escape or an outside click (after a short grace window
that swallows the opening click).

All public APIs must run on the Qt GUI thread.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import ClassVar

from PySide6.QtCore import QDateTime, QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeyEvent, QKeySequence, QMouseEvent, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import Shiboken

from services.ai.ai_config import AiModelEntry, model_entry_enabled

# Item data role storing the model id on each list row.
_ID_ROLE = Qt.ItemDataRole.UserRole + 1

# Swallow the synthetic mouse-press from the click that opened the popover.
_SHOW_GRACE_MS = 200


def _entry_label(entry: AiModelEntry) -> str:
    """Return the display label for *entry* (falls back to the model string)."""
    return entry.get("label") or entry["model"]


def _provider_group_name(entry: AiModelEntry) -> str:
    """Return the provider heading for *entry* (display name, else provider key)."""
    return str(entry.get("provider_display_name") or entry.get("provider") or "Other").strip()


def _group_by_provider(entries: list[AiModelEntry]) -> list[tuple[str, list[AiModelEntry]]]:
    """Group *entries* by provider heading; sort groups and models alphabetically."""
    buckets: dict[str, list[AiModelEntry]] = defaultdict(list)
    for entry in entries:
        buckets[_provider_group_name(entry)].append(entry)
    groups: list[tuple[str, list[AiModelEntry]]] = []
    for name in sorted(buckets, key=str.casefold):
        models = sorted(buckets[name], key=lambda e: _entry_label(e).casefold())
        groups.append((name, models))
    return groups


class _ModelRow(QWidget):
    """One selectable model row (indented under its provider header)."""

    activated = Signal()

    def __init__(self, entry: AiModelEntry, *, parent: QWidget | None = None) -> None:
        """Build the model name label for *entry*."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 3, 8, 3)
        layout.setSpacing(0)

        name = QLabel(_entry_label(entry))
        name.setObjectName("aiModelPickerName")
        name.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(name, 1)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit ``activated`` on a left click anywhere in the row."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mousePressEvent(event)


class AiModelPickerPopup(QFrame):
    """Anchored model picker; singleton so only one instance shows at a time."""

    model_picked = Signal(str)
    manage_requested = Signal()

    _instance: ClassVar[AiModelPickerPopup | None] = None

    @classmethod
    def instance(cls) -> AiModelPickerPopup:
        """Return the shared popover, creating it on first use."""
        if cls._instance is not None and not Shiboken.isValid(cls._instance):
            cls._instance = None
        if cls._instance is None:
            cls._instance = AiModelPickerPopup()
        return cls._instance

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the search field, model list, and Manage models link."""
        super().__init__(parent)
        self.setObjectName("aiModelPickerPopup")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedWidth(300)
        self.setMinimumHeight(220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._search = QLineEdit()
        self._search.setObjectName("aiModelPickerSearch")
        self._search.setPlaceholderText("Search models…")
        self._search.setClearButtonEnabled(True)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setObjectName("aiModelPickerList")
        layout.addWidget(self._list, 1)

        self._manage_link = QPushButton("Manage models")
        self._manage_link.setObjectName("aiModelPickerManageLink")
        self._manage_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._manage_link.clicked.connect(self._handle_manage)
        layout.addWidget(self._manage_link, 0, Qt.AlignmentFlag.AlignLeft)

        self._search.textChanged.connect(self._apply_filter)
        self._list.itemClicked.connect(self._on_item_activated)
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self._list)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self._activate_current_item)

        self._entries: list[AiModelEntry] = []
        self._current_id: str | None = None
        self._on_pick: Callable[[str], None] | None = None
        self._on_manage_cb: Callable[[], None] | None = None
        self._opened_at_ms = 0

        def _clear_singleton_ref(*_args: object) -> None:
            if AiModelPickerPopup._instance is self:
                AiModelPickerPopup._instance = None

        self.destroyed.connect(_clear_singleton_ref)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def show_for(
        self,
        anchor: QWidget,
        entries: list[AiModelEntry],
        current_id: str | None,
        on_pick: Callable[[str], None],
        on_manage: Callable[[], None],
    ) -> None:
        """Populate from *entries* (enabled only) and anchor near *anchor*."""
        app = QGuiApplication.instance()
        if app is not None and self.isVisible():
            app.removeEventFilter(self)
        self._entries = [e for e in entries if model_entry_enabled(e)]
        self._current_id = current_id
        self._on_pick = on_pick
        self._on_manage_cb = on_manage
        self._search.clear()
        self._populate(self._entries)
        self._position_for(anchor)
        self.show()
        self.raise_()
        self.activateWindow()
        self._search.setFocus()
        self._opened_at_ms = QDateTime.currentMSecsSinceEpoch()
        if app is not None:
            app.installEventFilter(self)

    def hidePopup(self) -> None:
        """Hide the popover, remove the event filter, and drop callbacks."""
        app = QGuiApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.hide()
        self._on_pick = None
        self._on_manage_cb = None

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Dismiss on Escape; delegate other keys to ``QFrame``."""
        if event.key() == Qt.Key.Key_Escape:
            self.hidePopup()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Close on a mouse press outside the popover after the grace window."""
        is_press = event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent)
        past_grace = QDateTime.currentMSecsSinceEpoch() - self._opened_at_ms >= _SHOW_GRACE_MS
        if is_press and past_grace:
            global_pos = event.globalPosition().toPoint()  # type: ignore[attr-defined]
            if not self.geometry().contains(global_pos):
                self.hidePopup()
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _position_for(self, anchor: QWidget) -> None:
        """Place the popover above the anchor, flipping below if it would clip."""
        self.adjustSize()
        height = self.sizeHint().height()
        top_left = anchor.mapToGlobal(QPoint(0, 0))
        bottom_left = anchor.mapToGlobal(QPoint(0, anchor.height()))
        screen = QGuiApplication.screenAt(top_left) or QGuiApplication.primaryScreen()
        sr = screen.availableGeometry() if screen else None
        x = top_left.x()
        y = top_left.y() - height - 4
        if y < (sr.top() if sr is not None else 0):
            y = bottom_left.y() + 4
        if sr is not None:
            x = max(sr.left(), min(x, sr.right() - self.width()))
            y = max(sr.top(), min(y, sr.bottom() - height))
        self.move(x, y)

    def _add_provider_header(self, name: str) -> None:
        """Append a non-selectable bold provider group heading."""
        header = QListWidgetItem(name)
        header.setFlags(Qt.ItemFlag.NoItemFlags)
        header.setData(_ID_ROLE, None)
        font = header.font()
        font.setBold(True)
        header.setFont(font)
        self._list.addItem(header)

    def _add_model_row(self, entry: AiModelEntry) -> None:
        """Append one selectable model row under the current provider group."""
        model_id = entry["id"]
        row = _ModelRow(entry, parent=self._list)
        row.activated.connect(lambda mid=model_id: self._pick(mid))
        item = QListWidgetItem()
        item.setData(_ID_ROLE, model_id)
        item.setSizeHint(row.sizeHint())
        self._list.addItem(item)
        self._list.setItemWidget(item, row)
        if model_id == self._current_id:
            self._list.setCurrentItem(item)

    def _populate(self, entries: list[AiModelEntry]) -> None:
        """Fill the list grouped by provider; select the current model row."""
        self._list.clear()
        if not entries:
            empty = QListWidgetItem("No models match")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(empty)
            return
        for group_name, group_entries in _group_by_provider(entries):
            self._add_provider_header(group_name)
            for entry in group_entries:
                self._add_model_row(entry)

    def _apply_filter(self, text: str) -> None:
        """Filter by model label or provider group name."""
        needle = text.strip().lower()
        if not needle:
            self._populate(self._entries)
            return
        filtered: list[AiModelEntry] = []
        for group_name, group_entries in _group_by_provider(self._entries):
            if needle in group_name.lower():
                filtered.extend(group_entries)
                continue
            for entry in group_entries:
                if needle in _entry_label(entry).lower():
                    filtered.append(entry)
        self._populate(filtered)

    def _activate_current_item(self) -> None:
        """Pick the highlighted row when activated via keyboard (skip headers)."""
        item = self._list.currentItem()
        if item is not None:
            self._on_item_activated(item)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        """Pick the model id stored on *item*."""
        model_id = item.data(_ID_ROLE)
        if isinstance(model_id, str) and model_id:
            self._pick(model_id)

    def _pick(self, model_id: str) -> None:
        """Invoke the pick callback, emit, and close."""
        if self._on_pick is not None:
            self._on_pick(model_id)
        self.model_picked.emit(model_id)
        self.hidePopup()

    def _handle_manage(self) -> None:
        """Invoke the manage callback, emit, and close."""
        if self._on_manage_cb is not None:
            self._on_manage_cb()
        self.manage_requested.emit()
        self.hidePopup()
