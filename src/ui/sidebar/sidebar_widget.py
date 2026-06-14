"""Postman-style right sidebar with icon rail and flyout panel.

The sidebar consists of two widgets placed as **separate children** in
the parent ``QSplitter``:

- :class:`_FlyoutPanel` — collapsible content area (AI assistant,
  variables, code-snippet, saved responses, history).  The QSplitter
  enforces its ``minimumSizeHint`` so
  content is never crushed: dragging past the minimum snaps it to 0.
- :class:`RightSidebar` — the always-visible icon rail.

``RightSidebar`` owns the flyout and exposes the same public API as
before.  Call :pymethod:`install_in_splitter` after construction to
place both widgets into the target splitter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from services.collection_service import SavedResponseDict
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.chat_sessions.session_title import AiChatSessionTitle
from ui.sidebar.history.panel import HistoryPanel
from ui.sidebar.saved_responses.panel import SavedResponsesPanel
from ui.sidebar.snippet_panel import SnippetPanel
from ui.sidebar.variables_panel import VariablesPanel
from ui.styling.icons import phi
from ui.styling.theme import RIGHT_FLYOUT_MIN_WIDTH_EM, RIGHT_FLYOUT_OPEN_WIDTH_EM

if TYPE_CHECKING:
    from services.environment_service import LocalOverride, VariableDetail

_RAIL_TOOLTIP_SAVED_RESPONSES = "Saved responses"
_RAIL_TOOLTIP_HISTORY = "History"
_RAIL_TOOLTIP_SAVED_DRAFT = "Save the request to the collection first."
_RAIL_TOOLTIP_HISTORY_DRAFT = "Save the request to the collection first."
_RAIL_TOOLTIP_SAVED_ORPHAN = (
    "Saved responses belong to a request in the collection. "
    "The original request was deleted — save this tab to the collection to use saved responses."
)
_RAIL_TOOLTIP_HISTORY_ORPHAN = (
    "Per-request history belongs to a saved request. "
    "The original request was deleted — save this tab or use workspace History on the left."
)


def _rail_tooltip(enabled: bool, enabled_tip: str, disabled_tip: str) -> str:
    """Return the rail-button tooltip for *enabled* vs disabled state."""
    return enabled_tip if enabled else disabled_tip


# ------------------------------------------------------------------
# Flyout panel — separate splitter child
# ------------------------------------------------------------------
class _FlyoutPanel(QWidget):
    """Collapsible content panel placed as its own splitter child."""

    def __init__(
        self,
        request_history_panel: HistoryPanel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Build title bar and all flyout content panels."""
        super().__init__(parent)
        self.setObjectName("sidebarPanelArea")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        em = self.fontMetrics().height()
        self._min_width: int = round(RIGHT_FLYOUT_MIN_WIDTH_EM * em)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.variables_panel = VariablesPanel()
        self.snippet_panel = SnippetPanel()
        self.saved_responses_panel = SavedResponsesPanel()
        self.request_history_panel = request_history_panel or HistoryPanel()
        self.ai_chat_panel = AiChatPanel()
        self.snippet_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(12, 8, 8, 4)
        title_bar.setSpacing(4)

        self.title_label = QLabel()
        self.title_label.setObjectName("sidebarTitleLabel")
        title_bar.addWidget(self.title_label)
        title_bar.addStretch()

        self._history_refresh_btn = self.request_history_panel.refresh_button()
        self._history_refresh_btn.setFixedSize(28, 28)
        self._history_refresh_btn.hide()
        title_bar.addWidget(self._history_refresh_btn)

        self._ai_history_btn = QPushButton()
        self._ai_history_btn.setObjectName("iconButton")
        self._ai_history_btn.setCheckable(True)
        self._ai_history_btn.setFixedSize(28, 28)
        self._ai_history_btn.setIcon(phi("clock-counter-clockwise", size=16))
        self._ai_history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ai_history_btn.setToolTip("Session history")

        self._ai_new_chat_btn = QPushButton()
        self._ai_new_chat_btn.setObjectName("iconButton")
        self._ai_new_chat_btn.setFixedSize(28, 28)
        self._ai_new_chat_btn.setIcon(phi("plus", size=16))
        self._ai_new_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ai_new_chat_btn.setToolTip("New conversation")

        self._ai_settings_btn = QPushButton()
        self._ai_settings_btn.setObjectName("iconButton")
        self._ai_settings_btn.setFixedSize(28, 28)
        self._ai_settings_btn.setIcon(phi("gear", size=16))
        self._ai_settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ai_settings_btn.setToolTip("AI settings")
        self._ai_settings_btn.hide()
        title_bar.addWidget(self._ai_settings_btn)

        layout.addLayout(title_bar)

        self._ai_session_title_bar = QWidget()
        self._ai_session_title_bar.setObjectName("aiChatSessionTitleBar")
        session_title_layout = QHBoxLayout(self._ai_session_title_bar)
        session_title_layout.setContentsMargins(12, 0, 8, 4)
        session_title_layout.setSpacing(4)
        self._ai_session_title_label = AiChatSessionTitle(self._ai_session_title_bar)
        session_title_layout.addWidget(self._ai_session_title_label, 1)
        session_title_layout.addWidget(self._ai_history_btn, 0)
        session_title_layout.addWidget(self._ai_new_chat_btn, 0)
        layout.addWidget(self._ai_session_title_bar)
        self._ai_session_title_bar.hide()

        title_sep = QLabel()
        title_sep.setObjectName("sidebarSeparator")
        title_sep.setFixedHeight(1)
        layout.addWidget(title_sep)
        layout.addWidget(self.variables_panel, 1)
        layout.addWidget(self.snippet_panel, 1)
        layout.addWidget(self.saved_responses_panel, 1)
        layout.addWidget(self.request_history_panel, 1)
        layout.addWidget(self.ai_chat_panel, 1)
        self.variables_panel.hide()
        self.snippet_panel.hide()
        self.saved_responses_panel.hide()
        self.request_history_panel.hide()
        self.ai_chat_panel.hide()

    def minimumSizeHint(self) -> QSize:
        """Enforce a readable minimum width for the flyout."""
        return QSize(self._min_width, 0)

    def set_ai_session_title(self, title: str) -> None:
        """Update the conversation title shown under the AI assistant headline."""
        self._ai_session_title_label.set_full_text(title)

    def set_ai_session_title_rename_enabled(self, enabled: bool) -> None:
        """Allow or block inline rename for the active session title."""
        self._ai_session_title_label.set_rename_enabled(enabled)


# ------------------------------------------------------------------
# Icon rail + controller
# ------------------------------------------------------------------
class RightSidebar(QWidget):
    """Always-visible icon rail that controls a flyout panel.

    After construction, call :pymethod:`install_in_splitter` to place
    both the flyout and the rail into the parent splitter.
    """

    ai_settings_requested = Signal()
    ai_new_chat_requested = Signal()
    ai_session_history_requested = Signal()
    ai_session_title_renamed = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        request_history_panel: HistoryPanel | None = None,
    ) -> None:
        """Initialise the icon rail and create the flyout panel."""
        super().__init__(parent)
        self.setObjectName("sidebarRail")

        # Derive sizes from the application font.
        em = self.fontMetrics().height()
        self._rail_width: int = round(2.4 * em)
        self._icon_size: int = round(1.35 * em)
        self._btn_size: int = self._rail_width - round(0.35 * em)
        self._panel_hint_width: int = round(RIGHT_FLYOUT_OPEN_WIDTH_EM * em)

        self.setFixedWidth(self._rail_width)

        # --- Flyout (separate widget, placed in splitter later) -------
        self._flyout = _FlyoutPanel(request_history_panel)
        self._title_label = self._flyout.title_label
        self._variables_panel = self._flyout.variables_panel
        self._snippet_panel = self._flyout.snippet_panel
        self._saved_responses_panel = self._flyout.saved_responses_panel
        self._request_history_panel = self._flyout.request_history_panel
        self._ai_chat_panel = self._flyout.ai_chat_panel
        self._flyout._ai_new_chat_btn.clicked.connect(self.ai_new_chat_requested.emit)
        self._flyout._ai_history_btn.clicked.connect(self.ai_session_history_requested.emit)
        self._flyout._ai_settings_btn.clicked.connect(self.ai_settings_requested.emit)
        self._flyout._ai_session_title_label.rename_committed.connect(
            self.ai_session_title_renamed.emit,
        )

        # --- Rail layout ----------------------------------------------
        rail_layout = QVBoxLayout(self)
        rail_layout.setContentsMargins(0, 6, 0, 6)
        rail_layout.setSpacing(12)

        self._ai_btn = self._make_rail_button("sparkle", "AI assistant")
        self._ai_btn.setEnabled(True)
        self._var_btn = self._make_rail_button(
            "brackets-curly",
            "Variables",
        )
        self._snippet_btn = self._make_rail_button("code", "Code snippet")
        self._saved_btn = self._make_rail_button("floppy-disk-back", _RAIL_TOOLTIP_SAVED_RESPONSES)
        self._history_btn = self._make_rail_button("clock-counter-clockwise", _RAIL_TOOLTIP_HISTORY)
        self._snippet_btn.hide()
        self._saved_btn.hide()
        self._history_btn.hide()
        rail_layout.addWidget(self._ai_btn)
        rail_layout.addWidget(self._var_btn)
        rail_layout.addWidget(self._snippet_btn)
        rail_layout.addWidget(self._saved_btn)
        rail_layout.addWidget(self._history_btn)
        rail_layout.addStretch()

        # State
        self._active_panel: str | None = None
        self._last_panel: str | None = None
        self._available_panels: set[str] = set()
        self._default_panel: str | None = None
        self._splitter: QSplitter | None = None
        self._flyout_idx: int = -1
        self._flyout_resize_handle: QWidget | None = None

        # Wire rail buttons
        self._ai_btn.clicked.connect(lambda: self._toggle_panel("ai"))
        self._var_btn.clicked.connect(lambda: self._toggle_panel("variables"))
        self._snippet_btn.clicked.connect(
            lambda: self._toggle_panel("snippet"),
        )
        self._saved_btn.clicked.connect(
            lambda: self._toggle_panel("saved_responses"),
        )
        self._history_btn.clicked.connect(
            lambda: self._toggle_panel("request_history"),
        )

    # Keep a reference for the ``_rail`` attribute used by tests.
    @property
    def _rail(self) -> QWidget:
        """Return self — the rail *is* this widget."""
        return self

    @property
    def ai_chat_panel(self) -> AiChatPanel:
        """Expose the AI chat panel for MainWindow wiring."""
        return self._ai_chat_panel

    @property
    def ai_history_button(self) -> QWidget:
        """Header button the session-history popover anchors to."""
        return self._flyout._ai_history_btn

    def set_ai_session_title(self, title: str) -> None:
        """Update the active conversation title in the AI flyout chrome."""
        self._flyout.set_ai_session_title(title)

    def set_ai_session_title_rename_enabled(self, enabled: bool) -> None:
        """Allow or block inline rename for the active session title."""
        self._flyout.set_ai_session_title_rename_enabled(enabled)

    # ------------------------------------------------------------------
    # Splitter integration
    # ------------------------------------------------------------------
    def install_in_splitter(self, splitter: QSplitter) -> None:
        """Add the flyout and rail as children of *splitter*.

        Must be called **after** the content area has been added to
        the splitter so the flyout sits between content and rail.
        """
        self._splitter = splitter
        splitter.addWidget(self._flyout)
        self._flyout_idx = splitter.indexOf(self._flyout)
        splitter.addWidget(self)
        rail_idx = splitter.indexOf(self)

        # Flyout: collapsible (snap-to-close), no stretch.
        splitter.setCollapsible(self._flyout_idx, True)
        splitter.setStretchFactor(self._flyout_idx, 0)

        # Rail: fixed, non-collapsible, no stretch.
        splitter.setCollapsible(rail_idx, False)
        splitter.setStretchFactor(rail_idx, 0)

        # Hide the handle between flyout and rail — it's not useful
        # since the rail is fixed-width.
        rail_handle = splitter.handle(rail_idx)
        if rail_handle:
            rail_handle.setFixedWidth(0)
            rail_handle.setEnabled(False)

        # Start collapsed — flyout at 0 width.
        sizes = splitter.sizes()
        sizes[self._flyout_idx] = 0
        splitter.setSizes(sizes)

        # React when user drags the splitter handle.
        splitter.splitterMoved.connect(self._on_splitter_moved)
        flyout_handle = splitter.handle(self._flyout_idx)
        if flyout_handle is not None:
            self._flyout_resize_handle = flyout_handle
            flyout_handle.installEventFilter(self)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def variables_panel(self) -> VariablesPanel:
        """Return the variables panel widget."""
        return self._variables_panel

    @property
    def snippet_panel(self) -> SnippetPanel:
        """Return the snippet panel widget."""
        return self._snippet_panel

    @property
    def saved_responses_panel(self) -> SavedResponsesPanel:
        """Return the saved responses panel widget."""
        return self._saved_responses_panel

    @property
    def request_history_panel(self) -> HistoryPanel:
        """Return the per-request send history panel widget."""
        return self._request_history_panel

    @property
    def active_panel(self) -> str | None:
        """Return the key of the currently open panel, or *None*."""
        return self._active_panel

    @property
    def panel_open(self) -> bool:
        """Return whether any panel is currently visible."""
        return self._active_panel is not None

    @property
    def flyout_width(self) -> int:
        """Return the current flyout width in pixels (0 when collapsed)."""
        if not self._splitter or self._flyout_idx < 0:
            return 0
        return self._splitter.sizes()[self._flyout_idx]

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Track manual flyout resize drags before child layout work starts."""
        if watched is self._flyout_resize_handle and self._active_panel == "ai":
            if event.type() == QEvent.Type.MouseButtonPress:
                self._ai_chat_panel._prepare_panel_resize_coalescing()
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._ai_chat_panel._schedule_resize_settle()
        return super().eventFilter(watched, event)

    def show_request_panels(
        self,
        variables: dict[str, VariableDetail],
        local_overrides: dict[str, LocalOverride] | None = None,
        has_environment: bool = True,
        *,
        method: str = "",
        url: str = "",
        headers: str | None = None,
        body: str | None = None,
        auth: dict | None = None,
    ) -> None:
        """Configure the sidebar for a request tab."""
        self._available_panels = {
            "ai",
            "variables",
            "snippet",
            "saved_responses",
            "request_history",
        }
        self._default_panel = "snippet"
        self._var_btn.setEnabled(True)
        self._snippet_btn.show()
        self._snippet_btn.setEnabled(True)
        self._saved_btn.show()
        self._saved_btn.setEnabled(True)
        self._history_btn.show()
        self._history_btn.setEnabled(True)

        self._variables_panel.load_variables(
            variables,
            local_overrides=local_overrides,
            has_environment=has_environment,
        )
        self._snippet_panel.update_request(
            method=method,
            url=url,
            headers=headers,
            body=body,
            auth=auth,
        )

        if self._active_panel and self._active_panel not in self._available_panels:
            self._close_panel()

    def show_folder_panels(
        self,
        variables: dict[str, VariableDetail],
        has_environment: bool = True,
    ) -> None:
        """Configure the sidebar for a folder tab."""
        self._available_panels = {"ai", "variables"}
        self._default_panel = "variables"
        self._var_btn.setEnabled(True)
        self._snippet_btn.hide()
        self._saved_btn.hide()
        self._history_btn.hide()

        self._variables_panel.load_variables(
            variables,
            has_environment=has_environment,
        )

        if self._active_panel in {"snippet", "saved_responses", "request_history"}:
            self._close_panel()

    def set_saved_response_context(
        self,
        *,
        request_id: int | None,
        request_name: str | None,
        items: list[SavedResponseDict],
        can_save_current: bool,
        is_persisted_request: bool,
        from_deleted_request_history: bool = False,
    ) -> None:
        """Populate the saved responses panel for the active request context."""
        self._saved_btn.setVisible(True)
        self._saved_btn.setEnabled(is_persisted_request)
        disabled_tip = (
            _RAIL_TOOLTIP_SAVED_ORPHAN
            if from_deleted_request_history
            else _RAIL_TOOLTIP_SAVED_DRAFT
        )
        self._saved_btn.setToolTip(
            _rail_tooltip(is_persisted_request, _RAIL_TOOLTIP_SAVED_RESPONSES, disabled_tip)
        )
        self._saved_responses_panel.set_request_context(request_id, request_name)
        self._saved_responses_panel.set_live_response_available(can_save_current)
        if not is_persisted_request:
            if self._active_panel == "saved_responses":
                self._close_panel()
            empty_msg = (
                "The original request was deleted from the collection. "
                "Save this tab to the collection to store and browse saved responses."
                if from_deleted_request_history
                else "Save the request first to store and browse saved responses."
            )
            self._saved_responses_panel.show_request_required_state(empty_msg)
            return
        self._saved_responses_panel.set_saved_responses(items)

    def set_request_history_context(
        self,
        *,
        request_id: int | None,
        request_name: str | None,
        is_persisted_request: bool,
        load_detail: bool = True,
        from_deleted_request_history: bool = False,
    ) -> None:
        """Populate the send-history panel for the active request context."""
        self._history_btn.setVisible(True)
        self._history_btn.setEnabled(is_persisted_request)
        disabled_tip = (
            _RAIL_TOOLTIP_HISTORY_ORPHAN
            if from_deleted_request_history
            else _RAIL_TOOLTIP_HISTORY_DRAFT
        )
        self._history_btn.setToolTip(
            _rail_tooltip(is_persisted_request, _RAIL_TOOLTIP_HISTORY, disabled_tip)
        )
        panel = self._request_history_panel
        context_unchanged = (
            panel._request_id == request_id
            and panel._is_persisted_request == is_persisted_request
            and is_persisted_request
        )
        panel.set_request_context(
            request_id,
            request_name,
            is_persisted_request=is_persisted_request,
        )
        if not is_persisted_request:
            if self._active_panel == "request_history":
                self._close_panel()
            empty_msg = (
                "The original request was deleted from the collection. "
                "Use workspace History on the left, or save this tab to browse per-request history."
                if from_deleted_request_history
                else "Save the request first to browse history for this request."
            )
            panel.show_request_required_state(empty_msg)
            return
        if not context_unchanged:
            panel.refresh(load_detail=load_detail)

    def clear(self) -> None:
        """Reset the sidebar to an empty state (no tab open)."""
        self._available_panels = {"ai"}
        self._var_btn.setEnabled(False)
        self._snippet_btn.hide()
        self._saved_btn.hide()
        self._history_btn.hide()
        self._close_panel()
        self._variables_panel.clear()
        self._snippet_panel.clear()
        self._saved_responses_panel.clear()
        self._request_history_panel.clear()

    def open_panel(self, panel: str) -> None:
        """Programmatically open a specific panel by key."""
        if panel in self._available_panels:
            self._show_panel(panel)

    def open_default_panel(self) -> None:
        """Open the most relevant available panel for the current context."""
        panel = self._last_panel if self._last_panel in self._available_panels else None
        if panel is None:
            panel = self._default_panel
        if panel is not None:
            self._show_panel(panel)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _make_rail_button(self, icon_name: str, tooltip: str) -> QToolButton:
        """Create a single rail icon button."""
        btn = QToolButton()
        btn.setObjectName("sidebarRailButton")
        btn.setIconSize(QSize(self._icon_size, self._icon_size))
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setFixedSize(self._btn_size, self._btn_size)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setEnabled(False)
        btn.setProperty("rail_icon_name", icon_name)
        self._apply_rail_icon(btn, icon_name)
        return btn

    def _apply_rail_icon(self, btn: QToolButton, icon_name: str) -> None:
        # Two-state icon: muted Off, accent On. Qt swaps automatically when
        # the QToolButton is toggled, giving a clear VSCode-style indicator.
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

    def refresh_theme(self) -> None:
        """Re-render rail-button icons against the current palette."""
        for btn in (
            self._ai_btn,
            self._var_btn,
            self._snippet_btn,
            self._saved_btn,
            self._history_btn,
        ):
            name = btn.property("rail_icon_name")
            if isinstance(name, str) and name:
                self._apply_rail_icon(btn, name)

    def _toggle_panel(self, panel: str) -> None:
        """Toggle the given panel open or closed."""
        if self._active_panel == panel:
            self._close_panel()
        else:
            self._show_panel(panel)

    def _show_panel(self, panel: str, *, expand_flyout: bool = True) -> None:
        """Open *panel*, configuring the flyout content."""
        self._active_panel = panel
        self._last_panel = panel
        self._variables_panel.setVisible(panel == "variables")
        self._snippet_panel.setVisible(panel == "snippet")
        self._saved_responses_panel.setVisible(panel == "saved_responses")
        self._request_history_panel.setVisible(panel == "request_history")
        self._ai_chat_panel.setVisible(panel == "ai")
        self._var_btn.setChecked(panel == "variables")
        self._snippet_btn.setChecked(panel == "snippet")
        self._saved_btn.setChecked(panel == "saved_responses")
        self._history_btn.setChecked(panel == "request_history")
        self._ai_btn.setChecked(panel == "ai")
        titles = {
            "variables": "Variables",
            "snippet": "Code snippet",
            "saved_responses": "Saved Responses",
            "request_history": "History",
            "ai": "AI assistant",
        }
        self._title_label.setText(titles.get(panel, panel))
        self._flyout._history_refresh_btn.setVisible(panel == "request_history")
        self._flyout._ai_settings_btn.setVisible(panel == "ai")
        self._flyout._ai_session_title_bar.setVisible(panel == "ai")
        self._flyout.show()
        if expand_flyout:
            self._expand_flyout()

    def _close_panel(self) -> None:
        """Collapse the flyout, keeping the icon rail visible."""
        self._active_panel = None
        self._variables_panel.hide()
        self._snippet_panel.hide()
        self._saved_responses_panel.hide()
        self._request_history_panel.hide()
        self._ai_chat_panel.hide()
        self._var_btn.setChecked(False)
        self._snippet_btn.setChecked(False)
        self._saved_btn.setChecked(False)
        self._history_btn.setChecked(False)
        self._ai_btn.setChecked(False)
        self._flyout._history_refresh_btn.hide()
        self._flyout._ai_settings_btn.hide()
        self._flyout._ai_session_title_bar.hide()
        self._collapse_flyout()

    def _expand_flyout(self, target_width: int | None = None) -> None:
        """Expand the flyout in the parent splitter via setSizes."""
        if not self._splitter or self._flyout_idx < 0:
            return
        if target_width is not None:
            want = target_width
        else:
            em = self.fontMetrics().height()
            want = round(RIGHT_FLYOUT_OPEN_WIDTH_EM * em)
            self._panel_hint_width = want
        sizes = self._splitter.sizes()
        if sizes[self._flyout_idx] >= want:
            return
        # Steal space from the content area (index 0).
        need = want - sizes[self._flyout_idx]
        give = min(need, sizes[0])
        sizes[0] -= give
        sizes[self._flyout_idx] += give
        self._splitter.setSizes(sizes)

    def _collapse_flyout(self) -> None:
        """Collapse the flyout in the parent splitter to 0."""
        if not self._splitter or self._flyout_idx < 0:
            return
        sizes = self._splitter.sizes()
        freed = sizes[self._flyout_idx]
        if freed <= 0:
            return
        sizes[0] += freed
        sizes[self._flyout_idx] = 0
        self._splitter.setSizes(sizes)

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        """React to the user dragging the splitter handle."""
        if not self._splitter or self._flyout_idx < 0:
            return
        flyout_width = self._splitter.sizes()[self._flyout_idx]

        if flyout_width == 0 and self._active_panel:
            # User collapsed the flyout by dragging — same state as close/toggle.
            self._close_panel()

        if flyout_width > 0 and not self._active_panel:
            # User expanded the flyout by dragging — restore last panel content.
            panel = self._last_panel
            if not panel or panel not in self._available_panels:
                panel = self._default_panel
            if panel:
                self._show_panel(panel, expand_flyout=False)
