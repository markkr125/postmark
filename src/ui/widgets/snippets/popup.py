"""Frameless popover that lists script snippets and inserts them at the cursor.

The popover mirrors the interaction model of ``SnippetSettingsPopup``
(``ui.sidebar.snippet_panel``): a ``Tool`` + ``FramelessWindowHint`` window
that stays above the main UI, dismisses on outside click (with a short
grace period so the opening click does not immediately close it), and
closes on Escape.

Window flags (why each is set)
------------------------------
- ``Qt.WindowType.Tool``: floating auxiliary surface that does not appear in
  the taskbar and behaves like a transient helper to the anchor widget.
- ``Qt.WindowType.FramelessWindowHint``: no native title bar — the panel is
  a compact card (styled via global QSS) rather than a framed dialog.
- ``Qt.WindowType.WindowStaysOnTopHint``: keeps the list above the script
  editor and status bar while the user reads options; matches other small
  tool popups in Postmark.

Singleton rationale
---------------------
Only one snippet palette should be visible at a time across the whole app.
``SnippetsPopup.instance()`` returns a process-wide singleton, similar in
spirit to other floating pickers (e.g. the code editor completion popup
lives as a dedicated child widget of the editor, but is still conceptually
one active surface).  A singleton avoids stacking multiple popovers when
switching between Pre-request and Post-response tabs.

Threading
---------
All public APIs must run on the Qt GUI thread — they manipulate widgets,
install an application-wide ``eventFilter``, and call ``QWidget.show``.

Data shape
----------
Snippet payloads come from :mod:`ui.widgets.snippets.loader` (categories,
names, bodies).  This module does not parse JSON.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from shiboken6 import Shiboken
from PySide6.QtCore import QDateTime, QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFrame,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styling.theme import COLOR_TEXT_MUTED
from ui.widgets.snippets.loader import (
    SnippetCategory,
    load_snippets_for,
)

# Item data role for the snippet body (``None`` for category headers).
_BODY_ROLE = Qt.ItemDataRole.UserRole + 1

# Window-flag-locked tool windows can receive a synthetic mouse-press from the
# very click that opened them; ``_SHOW_GRACE_MS`` swallows that initial press.
# Aligns with :class:`ui.sidebar.snippet_panel.SnippetSettingsPopup`, which uses
# the same ``QDateTime``-based guard.
_SHOW_GRACE_MS = 200


class SnippetsPopup(QFrame):
    """Anchor-below popover; singleton so only one instance is shown at once."""

    snippet_picked = Signal(str)

    _instance: ClassVar[SnippetsPopup | None] = None

    @classmethod
    def instance(cls) -> SnippetsPopup:
        """Return the shared popover instance, creating it on first use."""
        if cls._instance is not None and not Shiboken.isValid(cls._instance):
            cls._instance = None
        if cls._instance is None:
            cls._instance = SnippetsPopup()
        return cls._instance

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build search field, list, and signals; window flags match other tool popups."""
        super().__init__(parent)
        self.setObjectName("snippetsPopup")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFixedWidth(320)
        self.setMinimumHeight(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._search = QLineEdit()
        self._search.setObjectName("snippetsSearch")
        self._search.setPlaceholderText("Search snippets…")
        self._search.setClearButtonEnabled(True)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setObjectName("snippetsList")
        layout.addWidget(self._list, 1)

        self._search.textChanged.connect(self._apply_filter)
        self._list.itemClicked.connect(self._on_item_activated)
        self._activate_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), self._list)
        self._activate_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self._activate_shortcut.activated.connect(self._activate_current_item)
        self._activate_shortcut_alt = QShortcut(QKeySequence(Qt.Key.Key_Enter), self._list)
        self._activate_shortcut_alt.setContext(Qt.ShortcutContext.WidgetShortcut)
        self._activate_shortcut_alt.activated.connect(self._activate_current_item)

        self._all: tuple[SnippetCategory, ...] = ()
        self._on_pick: Callable[[str], None] | None = None
        self._opened_at_ms = 0

        def _clear_singleton_ref(*_args: object) -> None:
            if SnippetsPopup._instance is self:
                SnippetsPopup._instance = None

        self.destroyed.connect(_clear_singleton_ref)

    def show_for(
        self,
        anchor: QWidget,
        language: str,
        script_type: str,
        on_pick: Callable[[str], None],
    ) -> None:
        """Load snippets for *language* / *script_type*, anchor below *anchor*.

        ``script_type`` is ``"pre_request"`` or ``"test"`` and filters
        out categories tagged for the other context (e.g. the
        ``Tests`` category never shows on a pre-request editor).
        ``on_pick`` is invoked with the snippet body when the user
        picks a row; the caller inserts text and manages editor focus.
        """
        app = QGuiApplication.instance()
        if app is not None and self.isVisible():
            app.removeEventFilter(self)
        self._all = load_snippets_for(language, script_type)
        self._on_pick = on_pick
        self._search.clear()
        self._populate(self._all)
        self._position_below(anchor)
        self.show()
        self.raise_()
        self.activateWindow()
        self._search.setFocus()
        self._opened_at_ms = QDateTime.currentMSecsSinceEpoch()
        if app is not None:
            app.installEventFilter(self)

    def hidePopup(self) -> None:
        """Hide the popover, remove the event filter, and drop the pick callback."""
        app = QGuiApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.hide()
        self._on_pick = None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Dismiss on Escape; delegate other keys to ``QFrame``."""
        if event.key() == Qt.Key.Key_Escape:
            self.hidePopup()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Close on mouse press outside the popover after the open grace window."""
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            if QDateTime.currentMSecsSinceEpoch() - self._opened_at_ms < _SHOW_GRACE_MS:
                return super().eventFilter(obj, event)
            global_pos = event.globalPosition().toPoint()
            if not self.geometry().contains(global_pos):
                self.hidePopup()
        return super().eventFilter(obj, event)

    def _position_below(self, anchor: QWidget) -> None:
        """Move so the top-left sits just under the anchor, clamped to the screen."""
        bottom_left = anchor.mapToGlobal(QPoint(0, anchor.height()))
        screen = QGuiApplication.screenAt(bottom_left)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        sr = screen.availableGeometry() if screen else None
        x = bottom_left.x()
        y = bottom_left.y() + 4
        if sr is not None:
            x = max(sr.left(), min(x, sr.right() - self.width()))
            y = max(sr.top(), min(y, sr.bottom() - self.height()))
        self.move(x, y)

    def _populate(self, cats: tuple[SnippetCategory, ...]) -> None:
        """Fill the list from *cats*; headers use ``NoItemFlags``."""
        self._list.clear()
        if not cats:
            empty = QListWidgetItem("No snippets for this language")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            empty.setForeground(QColor(COLOR_TEXT_MUTED))
            self._list.addItem(empty)
            return
        for cat in cats:
            header = QListWidgetItem(cat.name)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            f = header.font()
            f.setBold(True)
            header.setFont(f)
            self._list.addItem(header)
            for snip in cat.snippets:
                item = QListWidgetItem(f"  {snip.name}")
                item.setData(_BODY_ROLE, snip.body)
                self._list.addItem(item)

    def _apply_filter(self, text: str) -> None:
        """Filter categories/snippets by case-insensitive substring in name or body."""
        needle = text.strip().lower()
        if not needle:
            self._populate(self._all)
            return
        filtered: list[SnippetCategory] = []
        for cat in self._all:
            kept = tuple(
                s for s in cat.snippets if needle in s.name.lower() or needle in s.body.lower()
            )
            if kept:
                filtered.append(SnippetCategory(name=cat.name, snippets=kept))
        self._populate(tuple(filtered))

    def _activate_current_item(self) -> None:
        """Insert the current list row when activated via keyboard."""
        item = self._list.currentItem()
        if item is not None:
            self._on_item_activated(item)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        """Insert snippet *body* at the editor cursor and close."""
        body = item.data(_BODY_ROLE)
        if not isinstance(body, str):
            return
        if self._on_pick is not None:
            self._on_pick(body)
        self.snippet_picked.emit(body)
        self.hidePopup()
