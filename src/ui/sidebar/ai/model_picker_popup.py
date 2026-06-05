"""Cursor-style model picker popover for the AI chat composer."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import ClassVar

from PySide6.QtCore import QDateTime, QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
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

from services.ai.ai_config import AiConfig, AiModelEntry, model_entry_enabled
from services.ai.reasoning_effort import clamp_effort, format_reasoning_effort
from ui.sidebar.ai.model_picker_edit import (
    AiModelPickerEditPanel,
    context_label_for_row,
    entry_has_edit_options,
    reasoning_levels_for_entry,
)
from ui.styling.icons import phi
from ui.styling.theme import COLOR_ACCENT, COLOR_SELECTED_BG

_ID_ROLE = Qt.ItemDataRole.UserRole + 1
_SHOW_GRACE_MS = 200


def _entry_label(entry: AiModelEntry) -> str:
    """Return the display label for *entry*."""
    return entry.get("label") or entry["model"]


def _provider_group_name(entry: AiModelEntry) -> str:
    """Return the provider heading for *entry*."""
    return str(entry.get("provider_display_name") or entry.get("provider") or "Other").strip()


def _effort_for_entry(entry: AiModelEntry) -> str:
    """Return the effective leveled reasoning effort for *entry*."""
    efforts = reasoning_levels_for_entry(entry)
    if not efforts:
        return ""
    stored = entry.get("reasoning_effort")
    if isinstance(stored, str) and stored.strip():
        return clamp_effort(
            stored.strip().lower(),
            efforts,
            str(entry.get("reasoning_default", "")),
        )
    default = str(entry.get("reasoning_default", ""))
    if default:
        return clamp_effort(default, efforts, default)
    from services.ai.reasoning_effort import default_effort_for

    return default_effort_for(efforts)


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


class _ModelListWidget(QListWidget):
    """List that does not treat Edit-button clicks as item activation."""

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Skip base handling when the release is on a row's Edit button."""
        if event.button() == Qt.MouseButton.LeftButton and self._release_on_edit(event):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _release_on_edit(self, event: QMouseEvent) -> bool:
        pos = event.position().toPoint()
        item = self.itemAt(pos)
        if item is None:
            return False
        row = self.itemWidget(item)
        if not isinstance(row, _ModelRow):
            return False
        local = row.mapFrom(self.viewport(), pos)
        target = row.childAt(local)
        while target is not None:
            if target is row._edit_btn:
                return True
            target = target.parentWidget()
        return False


class _ModelRow(QWidget):
    """One selectable model row with context tag, optional reasoning tag, and Edit."""

    activated = Signal()
    edit_requested = Signal()

    def __init__(
        self,
        entry: AiModelEntry,
        *,
        current_id: str | None,
        parent: QWidget | None = None,
    ) -> None:
        """Build name + tags + optional Edit for *entry*."""
        super().__init__(parent)
        self.setObjectName("aiModelPickerRow")
        self._entry = entry
        self._current_id = current_id
        self._can_edit = entry_has_edit_options(entry)
        self._show_reasoning_tag = bool(reasoning_levels_for_entry(entry))
        self._hover = False
        self._editing = False

        self.setMouseTracking(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 3, 8, 3)
        layout.setSpacing(6)

        self._name = QLabel(_entry_label(entry))
        self._name.setObjectName("aiModelPickerName")
        self._name.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._name, 0)

        self._ctx_lbl = QLabel(context_label_for_row(entry))
        self._ctx_lbl.setObjectName("aiModelPickerContext")
        layout.addWidget(self._ctx_lbl, 0)

        self._effort_lbl = QLabel("")
        self._effort_lbl.setObjectName("aiModelPickerEffort")
        self._effort_lbl.hide()
        layout.addWidget(self._effort_lbl, 0)

        layout.addStretch(1)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setObjectName("aiModelPickerEdit")
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setToolTip("Edit context, thinking, and reasoning")
        self._edit_btn.clicked.connect(self._on_edit_clicked)
        self._edit_btn.hide()
        layout.addWidget(self._edit_btn, 0, Qt.AlignmentFlag.AlignRight)

        self._update_tags()

    def set_editing(self, editing: bool) -> None:
        """Highlight this row while its edit flyout is open."""
        if self._editing == editing:
            return
        self._editing = editing
        self.setProperty("editing", "true" if editing else "false")
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def paintEvent(self, event) -> None:
        """Paint an editing highlight behind row contents."""
        if self._editing:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            fill = QColor(COLOR_SELECTED_BG)
            accent = QColor(COLOR_ACCENT)
            accent.setAlpha(48)
            painter.setBrush(fill)
            painter.drawRoundedRect(self.rect().adjusted(0, 1, -1, -1), 4, 4)
            painter.setBrush(accent)
            painter.drawRoundedRect(self.rect().adjusted(0, 1, -1, -1), 4, 4)
        super().paintEvent(event)

    def _update_tags(self) -> None:
        """Refresh context and reasoning tags from entry metadata."""
        self._ctx_lbl.setText(context_label_for_row(self._entry))
        if self._show_reasoning_tag:
            self._effort_lbl.setText(format_reasoning_effort(_effort_for_entry(self._entry)))
            self._effort_lbl.show()
        else:
            self._effort_lbl.hide()
        if self._can_edit and (
            self._hover or self._editing or self._entry["id"] == self._current_id
        ):
            self._edit_btn.show()
        else:
            self._edit_btn.hide()

    def enterEvent(self, event) -> None:
        """Show Edit on hover when settings are editable."""
        self._hover = True
        if self._can_edit:
            self._edit_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Hide Edit when the pointer leaves (unless this is the current row)."""
        self._hover = False
        if self._entry["id"] != self._current_id and not self._editing:
            self._edit_btn.hide()
        super().leaveEvent(event)

    def _on_edit_clicked(self) -> None:
        """Emit edit_requested without selecting the row."""
        self.edit_requested.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Activate row on left click unless the click hit the Edit button."""
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        child = self.childAt(event.position().toPoint())
        if child is not None:
            target = child
            while target is not None:
                if target is self._edit_btn:
                    super().mousePressEvent(event)
                    return
                parent = target.parentWidget()
                if parent is None:
                    break
                target = parent
        self.activated.emit()
        super().mousePressEvent(event)


class AiModelPickerPopup(QFrame):
    """Anchored model picker; singleton so only one instance shows at a time."""

    model_picked = Signal(str)
    manage_requested = Signal()
    model_settings_changed = Signal(str)

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
        """Build the search field, model list, and manage-models gear control."""
        super().__init__(parent)
        self.setObjectName("aiModelPickerPopup")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedWidth(340)
        self.setMinimumHeight(220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        search_row = QHBoxLayout()
        search_row.setSpacing(4)
        self._search = QLineEdit()
        self._search.setObjectName("aiModelPickerSearch")
        self._search.setPlaceholderText("Search models…")
        self._search.setClearButtonEnabled(True)
        search_row.addWidget(self._search, 1)

        self._manage_btn = QPushButton()
        self._manage_btn.setObjectName("iconButton")
        self._manage_btn.setFixedSize(28, 28)
        self._manage_btn.setIcon(phi("gear", size=16))
        self._manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._manage_btn.setToolTip("Manage models")
        self._manage_btn.clicked.connect(self._handle_manage)
        search_row.addWidget(self._manage_btn, 0)
        layout.addLayout(search_row)

        self._list = _ModelListWidget()
        self._list.setObjectName("aiModelPickerList")
        self._list.setMouseTracking(True)
        layout.addWidget(self._list, 1)

        self._search.textChanged.connect(self._apply_filter)
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self._list)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self._activate_current_item)

        self._entries: list[AiModelEntry] = []
        self._current_id: str | None = None
        self._on_pick: Callable[[str], None] | None = None
        self._on_manage_cb: Callable[[], None] | None = None
        self._on_settings_changed: Callable[[str], None] | None = None
        self._anchor: QWidget | None = None
        self._opened_at_ms = 0
        self._row_widgets: dict[str, _ModelRow] = {}
        self._edit_menu_open = False
        self._editing_model_id: str | None = None
        panel = AiModelPickerEditPanel.instance()
        panel.hidden.connect(self._on_edit_panel_hidden)

        def _clear_singleton_ref(*_args: object) -> None:
            if AiModelPickerPopup._instance is self:
                AiModelPickerPopup._instance = None

        self.destroyed.connect(_clear_singleton_ref)

    def show_for(
        self,
        anchor: QWidget,
        entries: list[AiModelEntry],
        current_id: str | None,
        on_pick: Callable[[str], None],
        on_manage: Callable[[], None],
        on_settings_changed: Callable[[str], None] | None = None,
        on_effort_changed: Callable[[str, str], None] | None = None,
    ) -> None:
        """Populate from *entries* (enabled only) and anchor near *anchor*."""
        app = QGuiApplication.instance()
        if app is not None and self.isVisible():
            app.removeEventFilter(self)
        self._anchor = anchor
        self._entries = [e for e in entries if model_entry_enabled(e)]
        self._current_id = current_id
        self._on_pick = on_pick
        self._on_manage_cb = on_manage
        if on_settings_changed is not None:
            self._on_settings_changed = on_settings_changed
        elif on_effort_changed is not None:
            effort_cb = on_effort_changed

            def _legacy_effort(mid: str) -> None:
                effort_cb(mid, "")

            self._on_settings_changed = _legacy_effort
        else:
            self._on_settings_changed = None
        self._row_widgets.clear()
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
        AiModelPickerEditPanel.instance().hide_panel()
        self.hide()
        self._anchor = None
        self._on_pick = None
        self._on_manage_cb = None
        self._on_settings_changed = None
        self._row_widgets.clear()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Dismiss on Escape."""
        if event.key() == Qt.Key.Key_Escape:
            self.hidePopup()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Close on a mouse press outside the popover after the grace window."""
        is_press = event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent)
        past_grace = QDateTime.currentMSecsSinceEpoch() - self._opened_at_ms >= _SHOW_GRACE_MS
        if is_press and past_grace and self.isVisible():
            mouse = event
            global_pos = mouse.globalPosition().toPoint()  # type: ignore[attr-defined]
            if self.geometry().contains(global_pos):
                return super().eventFilter(obj, event)
            if self._hits_anchor(global_pos):
                return super().eventFilter(obj, event)
            edit_panel = AiModelPickerEditPanel.instance()
            if edit_panel.isVisible():
                if edit_panel.geometry().contains(global_pos):
                    return super().eventFilter(obj, event)
                if self._global_pos_hits_edit_button(global_pos):
                    return super().eventFilter(obj, event)
                edit_panel.hide_panel()
            self.hidePopup()
        return super().eventFilter(obj, event)

    def _hits_anchor(self, global_pos: QPoint) -> bool:
        """True when *global_pos* is over the model button that opened this popover."""
        if self._anchor is None or not self._anchor.isVisible():
            return False
        local = self._anchor.mapFromGlobal(global_pos)
        return self._anchor.rect().contains(local)

    def _item_for_model(self, model_id: str) -> QListWidgetItem | None:
        """Return the list item for *model_id*, if present."""
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item is None:
                continue
            row_id = item.data(_ID_ROLE)
            if row_id == model_id:
                return item
        return None

    def _position_edit_panel(self, panel: AiModelPickerEditPanel, model_id: str) -> None:
        """Place the edit flyout beside the picker, aligned with the edited row."""
        panel.adjustSize()
        gap = 4
        picker_geo = self.geometry()
        panel_h = panel.height()
        panel_w = panel.width()
        x = picker_geo.left() - panel_w - gap
        y = picker_geo.top()

        item = self._item_for_model(model_id)
        if item is not None:
            self._list.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
            row_rect = self._list.visualItemRect(item)
            row_center_y = self._list.mapToGlobal(QPoint(0, row_rect.center().y())).y()
            y = row_center_y - panel_h // 2

        screen = QGuiApplication.screenAt(picker_geo.topLeft()) or QGuiApplication.primaryScreen()
        sr = screen.availableGeometry() if screen else None
        if sr is not None:
            if x < sr.left():
                x = picker_geo.right() + gap
            x = max(sr.left(), min(x, sr.right() - panel_w))
            y = max(sr.top(), min(y, sr.bottom() - panel_h))
        panel.move(x, y)

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
        """Append one selectable model row."""
        model_id = entry["id"]
        row = _ModelRow(entry, current_id=self._current_id, parent=self._list)
        row.activated.connect(lambda mid=model_id: self._pick(mid))
        row.edit_requested.connect(lambda mid=model_id: self._open_edit_menu(mid))
        self._row_widgets[model_id] = row
        item = QListWidgetItem()
        item.setData(_ID_ROLE, model_id)
        item.setSizeHint(row.sizeHint())
        self._list.addItem(item)
        self._list.setItemWidget(item, row)
        if model_id == self._current_id:
            self._list.setCurrentItem(item)

    def _populate(self, entries: list[AiModelEntry]) -> None:
        """Fill the list grouped by provider."""
        self._list.clear()
        self._row_widgets.clear()
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
                label = _entry_label(entry).lower()
                provider = _provider_group_name(entry).lower()
                if needle in label or needle in provider:
                    filtered.append(entry)
        self._populate(filtered)

    def _activate_current_item(self) -> None:
        """Pick the highlighted row when activated via keyboard."""
        item = self._list.currentItem()
        if item is not None:
            model_id = item.data(_ID_ROLE)
            if isinstance(model_id, str) and model_id:
                self._pick(model_id)

    def _pick(self, model_id: str) -> None:
        """Invoke the pick callback, emit, and close."""
        if self._on_pick is not None:
            self._on_pick(model_id)
        self.model_picked.emit(model_id)
        self.hidePopup()

    def _notify_settings_changed(self, model_id: str) -> None:
        """Refresh row UI and bubble settings change to the chat panel."""
        entry = self._find_entry(model_id)
        row = self._row_widgets.get(model_id)
        if entry is not None and row is not None:
            row._entry = entry
            row._update_tags()
        self.model_settings_changed.emit(model_id)
        if self._on_settings_changed is not None:
            self._on_settings_changed(model_id)

    def _find_entry(self, model_id: str) -> AiModelEntry | None:
        """Return the entry with *model_id* from the cached list."""
        for entry in self._entries:
            if entry["id"] == model_id:
                return entry
        return None

    def _on_edit_panel_hidden(self) -> None:
        """Clear edit-flyout state when the panel closes."""
        self._edit_menu_open = False
        self._set_editing_row(None)

    def _set_editing_row(self, model_id: str | None) -> None:
        """Mark *model_id* as the row whose edit flyout is open (or clear)."""
        if self._editing_model_id == model_id:
            return
        prev = self._editing_model_id
        self._editing_model_id = model_id
        if prev is not None:
            old_row = self._row_widgets.get(prev)
            if old_row is not None:
                old_row.set_editing(False)
        if model_id is not None:
            row = self._row_widgets.get(model_id)
            if row is not None:
                row.set_editing(True)

    def _global_pos_hits_edit_button(self, global_pos: QPoint) -> bool:
        """True when *global_pos* is over any model row's Edit control."""
        if not self.isVisible():
            return False
        local = self.mapFromGlobal(global_pos)
        if not self.rect().contains(local):
            return False
        list_local = self._list.mapFromGlobal(global_pos)
        item = self._list.itemAt(list_local)
        if item is None:
            return False
        row = self._list.itemWidget(item)
        if not isinstance(row, _ModelRow):
            return False
        btn_local = row._edit_btn.mapFromGlobal(global_pos)
        return row._edit_btn.isVisible() and row._edit_btn.rect().contains(btn_local)

    def _open_edit_menu(self, model_id: str) -> None:
        """Open the Cursor-style categorized edit flyout for *model_id*."""
        entry = self._find_entry(model_id)
        row = self._row_widgets.get(model_id)
        if entry is None or row is None or not entry_has_edit_options(entry):
            return

        panel = AiModelPickerEditPanel.instance()
        if panel.is_open_for(model_id):
            panel.hide_panel()
            return
        if panel.isVisible():
            panel.hide_panel()

        def on_context(mid: str, tokens: int) -> None:
            entry["context_limit"] = tokens  # type: ignore[typeddict-item]
            AiConfig.set_model_context_limit(mid, tokens)
            self._notify_settings_changed(mid)

        def on_thinking(mid: str, level: str) -> None:
            entry["thinking_enabled"] = level  # type: ignore[typeddict-item]
            AiConfig.set_model_thinking_enabled(mid, level)
            self._notify_settings_changed(mid)

        def on_reasoning(mid: str, level: str) -> None:
            entry["reasoning_effort"] = level  # type: ignore[typeddict-item]
            AiConfig.set_model_reasoning_effort(mid, level)
            self._notify_settings_changed(mid)

        panel.show_for(
            entry,
            model_id,
            on_context=on_context,
            on_thinking=on_thinking,
            on_reasoning=on_reasoning,
        )
        self._edit_menu_open = True
        self._set_editing_row(model_id)
        self._position_edit_panel(panel, model_id)
        panel.raise_()

    def _handle_manage(self) -> None:
        """Invoke the manage callback, emit, and close."""
        if self._on_manage_cb is not None:
            self._on_manage_cb()
        self.manage_requested.emit()
        self.hidePopup()
