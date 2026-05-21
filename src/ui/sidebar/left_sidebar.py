"""VSCode-style left activity bar with a collapsible flyout panel.

Mirrors the structure of :class:`RightSidebar` on the opposite edge of the
main splitter. The rail hosts icon buttons that toggle a content panel
sitting between the rail and the main editor area.

The rail is always visible and fixed-width. The flyout snaps to 0 width
when the user drags the splitter handle past the minimum, and reopens
when an icon is clicked.

Composition: the caller injects flyout pages via :meth:`set_content` (collections
and environments splitter) and optionally :meth:`set_local_scripts_panel` for a
second stacked page toggled from the activity rail.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import (
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.styling.icons import phi
from ui.styling.theme import (
    LEFT_RAIL_ACCENT_STRIPE_WIDTH_PX,
    LEFT_RAIL_BUTTON_EXTRA_HEIGHT_PX,
    LEFT_RAIL_ICON_EM,
    LEFT_RAIL_WIDTH_EM,
)


_COLLECTIONS_KEY = "collections"
_LOCAL_SCRIPTS_KEY = "local_scripts"
# Stacked flyout page order (left → right in internal stack indices).
_FLYOUT_PAGE_ORDER: tuple[str, ...] = (_COLLECTIONS_KEY, _LOCAL_SCRIPTS_KEY)

# Local stylesheet when the flyout splitter width is 0. Qt often does not apply
# ``[collapsed="true"]`` from a Python ``bool`` dynamic property, so borders
# must be cleared this way (runtime-only; see ``_sync_left_flyout_chrome``).
_LEFT_FLYOUT_COLLAPSED_QSS = (
    "#leftSidebarFlyout { border: none; background: transparent; }\n"
    "#leftSidebarFlyout QScrollArea { border: none; }"
)


class _LeftRailButton(QToolButton):
    """Rail icon; paints a full-height left accent when checked.

    Fusion-style ``QToolButton`` stylesheets often clip ``border-left`` to the
    content rectangle, so the selection stripe is drawn after the base paint
    pass instead.
    """

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the default tool button, then a full-height accent when checked."""
        super().paintEvent(event)
        if not self.isChecked():
            return
        from ui.styling.theme import COLOR_ACCENT

        w = min(LEFT_RAIL_ACCENT_STRIPE_WIDTH_PX, max(1, self.width()))
        with QPainter(self) as painter:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLOR_ACCENT))
            painter.drawRect(QRect(0, 0, w, self.height()))


class _LeftFlyoutPanel(QWidget):
    """Collapsible content area placed as its own child of the parent splitter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("leftSidebarFlyout")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._chrome_sync: Callable[[], None] | None = None

        em = self.fontMetrics().height()
        self._min_width: int = round(12.0 * em)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        layout.addLayout(self._content_layout, 1)

        self._panel_stack = QStackedWidget(self)
        self._content_layout.addWidget(self._panel_stack, 1)
        self._widgets_by_key: dict[str, QWidget] = {}

    def _stack_insert_index(self, key: str) -> int:
        """Return the ``QStackedWidget`` index for a newly inserted *key*."""
        if key not in _FLYOUT_PAGE_ORDER:
            return self._panel_stack.count()
        my_pos = _FLYOUT_PAGE_ORDER.index(key)
        return sum(1 for k in _FLYOUT_PAGE_ORDER[:my_pos] if k in self._widgets_by_key)

    def set_panel(self, key: str, widget: QWidget) -> None:
        """Register *widget* as the flyout page for *key* (replaces any prior page)."""
        prev = self._widgets_by_key.pop(key, None)
        if prev is not None:
            ix = self._panel_stack.indexOf(prev)
            self._panel_stack.removeWidget(prev)
            prev.setParent(None)
            self._panel_stack.insertWidget(ix, widget)
        else:
            ix = self._stack_insert_index(key)
            self._panel_stack.insertWidget(ix, widget)
        self._widgets_by_key[key] = widget

    def show_panel_key(self, key: str) -> bool:
        """Show the page for *key* if registered. Return whether the stack switched."""
        w = self._widgets_by_key.get(key)
        if w is None:
            return False
        self._panel_stack.setCurrentWidget(w)
        return True

    def has_panel(self, key: str) -> bool:
        """Return whether a flyout page is registered for *key*."""
        return key in self._widgets_by_key

    def set_content(self, widget: QWidget) -> None:
        """Install *widget* as the collections / environments flyout page."""
        self.set_panel(_COLLECTIONS_KEY, widget)

    def set_chrome_sync(self, fn: Callable[[], None] | None) -> None:
        """Notify *fn* after geometry changes (e.g. external ``setSizes``)."""
        self._chrome_sync = fn

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Re-evaluate collapsed chrome when the splitter resizes this pane."""
        super().resizeEvent(event)
        if self._chrome_sync is not None:
            self._chrome_sync()

    def minimumSizeHint(self) -> QSize:
        """Enforce a readable minimum width for the flyout."""
        return QSize(self._min_width, 0)


class LeftSidebar(QWidget):
    """Always-visible icon rail on the left edge that controls a flyout panel.

    After construction:
      1. Call :meth:`set_content` to install the collections / environments page.
      2. Optionally call :meth:`set_local_scripts_panel` to register a second
         flyout page and reveal its rail icon.
      3. Call :meth:`install_in_splitter` to insert the rail + flyout into
         the main horizontal splitter as its first two children.

    :signal:`panel_state_changed` (``bool``) emits ``True`` when the flyout
    gains non-zero width, ``False`` when it collapses to zero width — whether
    from the status bar, rail toggle, or dragging the splitter handle.
    """

    panel_state_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the rail layout, flyout shell, and default collections rail button."""
        super().__init__(parent)
        self.setObjectName("leftSidebarRail")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        em = self.fontMetrics().height()
        self._rail_width: int = round(LEFT_RAIL_WIDTH_EM * em)
        self._icon_size: int = round(LEFT_RAIL_ICON_EM * em)
        self._rail_btn_width: int = self._rail_width
        self._rail_btn_height: int = self._icon_size + LEFT_RAIL_BUTTON_EXTRA_HEIGHT_PX
        self._panel_hint_width: int = round(20.0 * em)

        self.setFixedWidth(self._rail_width)

        self._flyout = _LeftFlyoutPanel()

        rail_layout = QVBoxLayout(self)
        rail_layout.setContentsMargins(0, 0, 0, 0)
        rail_layout.setSpacing(0)

        self._collections_btn = self._make_rail_button(
            "files",
            "Collections & Environments",
        )
        self._collections_btn.setEnabled(True)
        rail_layout.addWidget(self._collections_btn)

        self._local_scripts_btn = self._make_rail_button("code", "Local scripts")
        self._local_scripts_btn.setVisible(False)
        rail_layout.addWidget(self._local_scripts_btn)
        rail_layout.addStretch()

        self._buttons: dict[str, QToolButton] = {
            _COLLECTIONS_KEY: self._collections_btn,
            _LOCAL_SCRIPTS_KEY: self._local_scripts_btn,
        }

        self._active_panel: str | None = None
        self._last_panel: str | None = _COLLECTIONS_KEY
        self._splitter: QSplitter | None = None
        self._flyout_idx: int = -1
        self._last_signal_open: bool = False
        self._last_flyout_chrome_collapsed: bool | None = None

        self._collections_btn.clicked.connect(
            lambda: self._toggle_panel(_COLLECTIONS_KEY),
        )
        self._local_scripts_btn.clicked.connect(
            lambda: self._toggle_panel(_LOCAL_SCRIPTS_KEY),
        )

        self._flyout.set_chrome_sync(self._sync_left_flyout_chrome)

    # Composition / splitter integration
    # ------------------------------------------------------------------
    def set_content(self, widget: QWidget) -> None:
        """Install the collections / environments flyout page."""
        self._flyout.set_content(widget)

    def set_local_scripts_panel(self, widget: QWidget) -> None:
        """Register the **Local scripts** flyout page and show its rail icon."""
        self._flyout.set_panel(_LOCAL_SCRIPTS_KEY, widget)
        self._local_scripts_btn.setVisible(True)

    def install_in_splitter(self, splitter: QSplitter) -> None:
        """Insert the rail and flyout as the leftmost children of *splitter*.

        Must be called **before** the main content is added to the splitter
        so the rail ends up on the outer left edge.
        """
        self._splitter = splitter
        splitter.addWidget(self)
        rail_idx = splitter.indexOf(self)
        splitter.addWidget(self._flyout)
        self._flyout_idx = splitter.indexOf(self._flyout)

        splitter.setCollapsible(rail_idx, False)
        splitter.setStretchFactor(rail_idx, 0)

        splitter.setCollapsible(self._flyout_idx, True)
        splitter.setStretchFactor(self._flyout_idx, 0)

        # Squash the handle between rail (index 0) and flyout (index 1).
        # ``QSplitter.handle(0)`` is *before* the rail — wrong. ``handle(i)`` is
        # immediately left of widget ``i``, so ``handle(self._flyout_idx)`` is
        # the rail|flyout seam. The draggable resize handle is
        # ``handle(self._flyout_idx + 1)`` (flyout vs main content).
        rail_flyout_handle = splitter.handle(self._flyout_idx)
        if rail_flyout_handle:
            rail_flyout_handle.setFixedWidth(0)
            rail_flyout_handle.setEnabled(False)

        splitter.splitterMoved.connect(self._on_splitter_moved)
        QTimer.singleShot(0, self._sync_left_flyout_chrome)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        """Return whether the flyout has non-zero width (visibly open)."""
        return self.flyout_width > 0

    @property
    def active_panel(self) -> str | None:
        """Return the key of the currently open panel, or *None*."""
        return self._active_panel

    @property
    def flyout_width(self) -> int:
        """Return the current flyout width in pixels (0 when collapsed)."""
        if not self._splitter or self._flyout_idx < 0:
            return 0
        return self._splitter.sizes()[self._flyout_idx]

    def session_panel_key(self) -> str:
        """Return the flyout page key to persist across app restarts."""
        return self._active_panel or self._last_panel or _COLLECTIONS_KEY

    def open_panel(self, panel: str = _COLLECTIONS_KEY) -> None:
        """Programmatically open a panel by key."""
        if not self._flyout.has_panel(panel):
            return
        self._show_panel(panel)

    def close_panel(self) -> None:
        """Collapse the flyout, keeping the icon rail visible."""
        self._close_panel()

    def toggle_panel(self, panel: str = _COLLECTIONS_KEY) -> None:
        """Toggle the given panel open or closed."""
        self._toggle_panel(panel)

    def refresh_theme(self) -> None:
        """Re-render rail-button icons against the current palette."""
        for btn in self._buttons.values():
            name = btn.property("rail_icon_name")
            if isinstance(name, str) and name:
                self._apply_rail_icon(btn, name)
        self._last_flyout_chrome_collapsed = None
        self._sync_left_flyout_chrome()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _make_rail_button(self, icon_name: str, tooltip: str) -> _LeftRailButton:
        btn = _LeftRailButton()
        btn.setObjectName("leftSidebarRailButton")
        btn.setIconSize(QSize(self._icon_size, self._icon_size))
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setFixedSize(self._rail_btn_width, self._rail_btn_height)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("rail_icon_name", icon_name)
        self._apply_rail_icon(btn, icon_name)
        return btn

    def _apply_rail_icon(self, btn: QToolButton, icon_name: str) -> None:
        from ui.styling.theme import COLOR_ACCENT, COLOR_TEXT_MUTED

        size = self._icon_size
        icon = QIcon()
        icon.addPixmap(
            phi(icon_name, color=COLOR_TEXT_MUTED, size=size).pixmap(size, size),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        icon.addPixmap(
            phi(icon_name, color=COLOR_ACCENT, size=size).pixmap(size, size),
            QIcon.Mode.Normal,
            QIcon.State.On,
        )
        btn.setIcon(icon)

    def _toggle_panel(self, panel: str) -> None:
        if not self._flyout.has_panel(panel):
            return
        if self._active_panel == panel and self.is_open:
            self._close_panel()
        else:
            self._show_panel(panel)

    def _show_panel(self, panel: str, *, expand_flyout: bool = True) -> None:
        if not self._flyout.show_panel_key(panel):
            return
        self._active_panel = panel
        self._last_panel = panel
        for key, btn in self._buttons.items():
            btn.setChecked(key == panel)
        self._flyout.show()
        if expand_flyout:
            self._expand_flyout()
        self._emit_open_state_if_changed()
        self._sync_left_flyout_chrome()

    def _close_panel(self) -> None:
        self._active_panel = None
        for btn in self._buttons.values():
            btn.setChecked(False)
        self._collapse_flyout()
        self._sync_left_flyout_chrome()
        self._emit_open_state_if_changed()

    def _expand_flyout(self, target_width: int | None = None) -> None:
        """Expand the flyout by taking width from the trailing main pane."""
        if not self._splitter or self._flyout_idx < 0:
            self._sync_left_flyout_chrome()
            return
        want = target_width if target_width is not None else self._panel_hint_width
        rail_idx = self._splitter.indexOf(self)
        donor_idx = self._trailing_content_index()
        if donor_idx < 0:
            self._sync_left_flyout_chrome()
            return
        sw = max(1, self._splitter.width())
        sizes = list(self._splitter.sizes())
        n = self._splitter.count()
        while len(sizes) < n:
            sizes.append(0)

        if sizes[self._flyout_idx] >= want:
            self._sync_left_flyout_chrome()
            return

        need = want - sizes[self._flyout_idx]
        give = min(need, sizes[donor_idx])
        if give <= 0 and sw > 100:
            # 1. Sizes are still stale (typical before the first layout pass).
            rail_w = max(
                self._rail_width, sizes[rail_idx] if rail_idx < len(sizes) else self._rail_width
            )
            remain = max(0, sw - rail_w - 8)
            min_centre = min(320, max(160, remain // 2))
            fly_w = min(want, max(0, remain - min_centre))
            cent_w = max(min_centre, remain - fly_w)
            fly_w = min(fly_w, remain - cent_w)
            new_sizes = [0] * n
            new_sizes[rail_idx] = rail_w
            new_sizes[self._flyout_idx] = fly_w
            new_sizes[donor_idx] = cent_w
            self._splitter.setSizes(new_sizes)
            self._sync_left_flyout_chrome()
            return

        if give <= 0:
            self._sync_left_flyout_chrome()
            return
        sizes[donor_idx] -= give
        sizes[self._flyout_idx] += give
        self._splitter.setSizes(sizes)
        self._sync_left_flyout_chrome()

    def _collapse_flyout(self) -> None:
        """Collapse the flyout to width 0; return pixels to the trailing main pane."""
        if not self._splitter or self._flyout_idx < 0:
            self._sync_left_flyout_chrome()
            return
        donor_idx = self._trailing_content_index()
        sizes = list(self._splitter.sizes())
        n = self._splitter.count()
        while len(sizes) < n:
            sizes.append(0)
        freed = sizes[self._flyout_idx]
        if freed <= 0:
            self._sync_left_flyout_chrome()
            return
        if donor_idx >= 0:
            sizes[donor_idx] += freed
        sizes[self._flyout_idx] = 0
        self._splitter.setSizes(sizes)
        self._sync_left_flyout_chrome()

    def _trailing_content_index(self) -> int:
        """Return the splitter index of the main content to the right of the flyout."""
        if not self._splitter or self._splitter.count() < 3:
            return -1
        return self._splitter.count() - 1

    def _emit_open_state_if_changed(self) -> None:
        """Emit :signal:`panel_state_changed` when flyout open/closed visibility flips."""
        open_now = self.flyout_width > 0
        if open_now == self._last_signal_open:
            return
        self._last_signal_open = open_now
        self.panel_state_changed.emit(open_now)

    def _sync_left_flyout_chrome(self) -> None:
        """Clear flyout borders when splitter width is 0.

        Qt can still paint ``border-left`` / ``border-right`` on a zero-width
        splitter child, which stacks with the main horizontal handle and reads
        as a thick double line beside the activity rail.

        Global QSS ``[collapsed="true"]`` on a ``bool`` dynamic property is
        unreliable across Qt versions, so collapsed state uses
        ``QWidget.setStyleSheet`` on the flyout only; expanded clears it so the
        app-wide stylesheet applies again.
        """
        if not self._splitter or self._flyout_idx < 0:
            return
        collapsed = self.flyout_width <= 0
        if self._last_flyout_chrome_collapsed is collapsed:
            return
        self._last_flyout_chrome_collapsed = collapsed
        if collapsed:
            self._flyout.setStyleSheet(_LEFT_FLYOUT_COLLAPSED_QSS)
        else:
            self._flyout.setStyleSheet("")

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        if not self._splitter or self._flyout_idx < 0:
            return
        flyout_width = self._splitter.sizes()[self._flyout_idx]

        if flyout_width == 0 and self._active_panel:
            self._active_panel = None
            for btn in self._buttons.values():
                btn.setChecked(False)

        if flyout_width > 0 and not self._active_panel:
            panel = self._last_panel or _COLLECTIONS_KEY
            if not self._flyout.has_panel(panel):
                panel = _COLLECTIONS_KEY
            self._flyout.show_panel_key(panel)
            self._active_panel = panel
            self._last_panel = panel
            for key, btn in self._buttons.items():
                btn.setChecked(key == panel)
            self._flyout.show()

        self._emit_open_state_if_changed()
        self._sync_left_flyout_chrome()
