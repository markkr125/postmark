"""Floating debug hover popup with optional expandable object tree.

Used when the script debugger is paused: hovering identifiers like ``pm``
shows a JetBrains-style tree for dict/list snapshots instead of a flat JSON
blob.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QHideEvent, QMouseEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from shiboken6 import Shiboken

from ui.widgets.debug_value_tree import (
    is_expandable_container,
    make_debug_value_tree,
    populate_debug_tree,
)


class DebugValuePopup(QFrame):
    """Floating popup: JSON text for primitives, tree for dict/list/tuple.

    Stays visible until the user clicks outside the popup (editor, rest of the
    main window, or presses Escape in the editor), matching JetBrains debug hover.
    """

    def __init__(self, parent: QWidget) -> None:
        """Create a frameless tool window with stacked text and tree pages."""
        super().__init__(None)
        self._anchor_widget = parent
        self._filter_hosts: list[QWidget] = []
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setObjectName("infoPopup")
        self.setMinimumWidth(220)
        self.setMaximumWidth(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(4)

        self._name_label = QLabel()
        self._name_label.setObjectName("infoPopupTitle")
        root.addWidget(self._name_label)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._text_page = QWidget()
        text_layout = QVBoxLayout(self._text_page)
        text_layout.setContentsMargins(0, 0, 0, 0)
        self._value_label = QLabel()
        self._value_label.setObjectName("variableValueLabel")
        self._value_label.setWordWrap(True)
        self._value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_layout.addWidget(self._value_label)
        self._stack.addWidget(self._text_page)

        self._tree_page = QWidget()
        tree_layout = QVBoxLayout(self._tree_page)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        self._tree = make_debug_value_tree(object_name="debugHoverValueTree", show_header=True)
        self._tree.setMinimumHeight(140)
        self._tree.setMaximumHeight(320)
        tree_layout.addWidget(self._tree)
        self._stack.addWidget(self._tree_page)

    def _detach_click_filter(self) -> None:
        """Remove :meth:`installEventFilter` from every host we attached to."""
        for host in self._filter_hosts:
            with contextlib.suppress(RuntimeError):
                if Shiboken.isValid(host):
                    host.removeEventFilter(self)
        self._filter_hosts.clear()

    def showEvent(self, event: QShowEvent) -> None:
        """Watch mouse presses on the editor and its top-level window for click-away."""
        super().showEvent(event)
        self._detach_click_filter()
        if self._anchor_widget is not None and Shiboken.isValid(self._anchor_widget):
            aw = self._anchor_widget
            candidates = (aw, aw.window())
            seen: set[int] = set()
            for h in candidates:
                if not isinstance(h, QWidget) or not Shiboken.isValid(h):
                    continue
                hid = id(h)
                if hid in seen:
                    continue
                seen.add(hid)
                h.installEventFilter(self)
                self._filter_hosts.append(h)

    def hideEvent(self, event: QHideEvent) -> None:
        """Detach click filters when hidden."""
        self._detach_click_filter()
        super().hideEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Hide when the user presses the mouse outside this popup (JetBrains-style).

        Prefer the event *receiver* (``watched``): ``widgetAt`` is unreliable on some
        platforms (e.g. returns ``None`` under Wayland), which left the popup stuck.
        """
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and Shiboken.isValid(self)
            and self.isVisible()
            and isinstance(event, QMouseEvent)
        ):
            recv = watched if isinstance(watched, QWidget) else None
            if recv is not None:
                if recv is not self and not self.isAncestorOf(recv):
                    self.hide()
            else:
                gp = event.globalPosition().toPoint()
                w_at = QApplication.widgetAt(gp)
                if w_at is None or (w_at is not self and not self.isAncestorOf(w_at)):
                    self.hide()
        return False

    def show_value(self, name: str, value: Any, global_pos: QPoint) -> None:
        """Show *value* for *name* near *global_pos* (tree or text)."""
        self._name_label.setText(name)
        if is_expandable_container(value):
            self._stack.setCurrentWidget(self._tree_page)
            populate_debug_tree(self._tree, value)
            self._tree.resizeColumnToContents(0)
        else:
            self._stack.setCurrentWidget(self._text_page)
            try:
                pretty = json.dumps(value, indent=2, ensure_ascii=False)
            except (TypeError, ValueError):
                pretty = repr(value)
            if len(pretty) > 2000:
                pretty = pretty[:2000] + "…"
            self._value_label.setText(pretty)
            self._value_label.setToolTip(pretty)

        self.adjustSize()
        target = QPoint(global_pos.x() + 10, global_pos.y() + 14)
        screen = QApplication.screenAt(global_pos)
        if screen is not None:
            geo = screen.availableGeometry()
            if target.x() + self.width() > geo.right():
                target.setX(global_pos.x() - self.width() - 6)
            if target.y() + self.height() > geo.bottom():
                target.setY(global_pos.y() - self.height() - 6)
        self.move(target)
        self.show()
