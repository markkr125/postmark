"""Debug UI: step controls, inspector split, and facade.

``DebugControls`` is the toolbar (step buttons + position).
``DebugInspectorSplit`` is call stack | watch strip + unified variables tree.
``DebugPanel`` composes controls and the split for tests and legacy callers.
"""

from __future__ import annotations

from collections.abc import Callable

from shiboken6 import Shiboken
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from services.scripting.debug import DebugPauseInfo, DebugProtocol
from ui.sidebar.debug_inspector_split import (
    DebugInspectorSplit,
    DebugWatchesPane,
    _make_debug_inspector_separator,
)
from ui.sidebar.debug_scopes_panel import (
    DEBUG_SCOPES_PAGE_MESSAGE,
    DEBUG_SCOPES_PAGE_TREE,
    DebugScopesPanel,
)
from ui.styling.icons import phi
from ui.styling.theme import COLOR_ACCENT, COLOR_TEXT, COLOR_WHITE

# Back-compat names for tests and docs.
DEBUG_VARIABLES_PAGE_TREE = DEBUG_SCOPES_PAGE_TREE
DEBUG_VARIABLES_PAGE_MESSAGE = DEBUG_SCOPES_PAGE_MESSAGE


class DebugVariablesPanel(QWidget):
    """Watch strip + unified tree for isolated tests (matches inspector right column)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Stack strip and scopes tree like :class:`DebugInspectorSplit` right side."""
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._scopes = DebugScopesPanel(self)
        self._strip = DebugWatchesPane(self._scopes, self)
        lay.addWidget(self._strip)
        lay.addWidget(_make_debug_inspector_separator())
        lay.addWidget(self._scopes, 1)

    @property
    def _tree(self) -> QTreeWidget:
        return self._scopes._tree

    @property
    def watch_state(self):
        """Ordered watch expressions."""
        return self._scopes.watch_state

    @property
    def _watches_root(self):
        return self._scopes.watches_root

    @property
    def _watch_add_edit(self):
        return self._strip._watch_add_edit

    @property
    def _protocol(self) -> DebugProtocol | None:
        return self._scopes._protocol

    def set_protocol(self, protocol: DebugProtocol | None) -> None:
        """Attach the active debug protocol for watch evaluation."""
        self._scopes.set_protocol(protocol)

    def _add_watch_expression(self) -> None:
        self._strip._add_watch_expression()

    def _remove_selected_watch(self) -> None:
        self._strip._remove_selected_watch()

    def refresh_watches(self) -> None:
        """Queue watch re-evaluation when paused."""
        self._strip.refresh_watches()

    def update_pause(self, info: DebugPauseInfo) -> None:
        """Refresh the unified variables tree from a pause payload."""
        self._scopes.update_pause(
            info.get("local_vars", {}),
            info.get("env_changes", {}) or {},
            info.get("global_changes", {}) or {},
        )

    def clear_session(self) -> None:
        """End session; keep watch expressions with placeholder values."""
        self._scopes.clear_session()

    def set_idle(self) -> None:
        """Clear protocol; keep watch rows with placeholder values."""
        self._scopes.set_idle()
        self.set_protocol(None)


def _qt_valid(obj: object | None) -> bool:
    """Return whether *obj* is a live Qt C++ wrapper (not deleted)."""
    return obj is not None and Shiboken.isValid(obj)


def format_debug_pause_status(info: DebugPauseInfo) -> str:
    """Human-readable pause line for toolbars and the script editor status bar."""
    source = info.get("source_name", "")
    line = int(info.get("line", 0))
    script_type = info.get("script_type", "")
    return f"Paused at line {line + 1}  \u2014  {script_type}" + (f" ({source})" if source else "")


def _make_debug_toolbar_separator() -> QFrame:
    """Vertical rule between breakpoint tools and step controls."""
    sep = QFrame()
    sep.setObjectName("scriptToolbarSeparator")
    sep.setFrameShape(QFrame.Shape.NoFrame)
    sep.setFixedWidth(1)
    sep.setFixedHeight(20)
    return sep


class DebugControls(QWidget):
    """Step buttons and pause position label (for output panel or composed panel)."""

    step_requested = Signal(str)
    start_debug_requested = Signal()
    view_breakpoints_requested = Signal()
    breakpoints_enabled_toggled = Signal(bool)
    pause_on_exceptions_toggled = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        keep_visible_when_idle: bool = False,
    ) -> None:
        """Build the control row and position line.

        When *keep_visible_when_idle* is True (script **Debugger** tab), the row
        stays visible with buttons disabled until a pause enables them.
        """
        super().__init__(parent)
        self._keep_visible_when_idle = keep_visible_when_idle
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 2, 0, 2)
        btn_row.setSpacing(6)

        self._view_bp_btn = self._make_breakpoint_action_btn(
            "list-bullets",
            "View breakpoints",
            self.view_breakpoints_requested.emit,
        )
        self._disable_bp_btn = self._make_breakpoint_toggle_btn(
            "prohibit",
            "Disable breakpoints",
            "Breakpoints disabled (click to enable)",
            self._on_disable_breakpoints_toggled,
        )
        self._exception_bp_btn = self._make_breakpoint_toggle_btn(
            "warning-circle",
            "Break on uncaught exceptions",
            "Do not break on uncaught exceptions (click to enable)",
            self._on_pause_on_exceptions_toggled,
            checked=True,
        )
        for btn in (self._view_bp_btn, self._disable_bp_btn, self._exception_bp_btn):
            btn_row.addWidget(btn)

        btn_row.addSpacing(8)
        btn_row.addWidget(_make_debug_toolbar_separator())
        btn_row.addSpacing(8)

        self._start_debug_btn: QPushButton | None
        if keep_visible_when_idle:
            self._start_debug_btn = self._make_start_debug_btn()
            btn_row.addWidget(self._start_debug_btn)
        else:
            self._start_debug_btn = None

        self._continue_btn = self._make_btn("play", "Continue", "continue")
        self._step_over_btn = self._make_btn("arrow-line-down", "Step Over", "step_over")
        self._step_into_btn = self._make_btn("arrow-line-down-right", "Step Into", "step_into")
        self._step_out_btn = self._make_btn("arrow-line-up-right", "Step Out", "step_out")
        self._stop_btn = self._make_btn("stop", "Stop", "stop")
        self._stop_btn.setObjectName("dangerButton")
        self._stop_btn.setIcon(phi("stop", color=COLOR_WHITE, size=16))

        for btn in (
            self._continue_btn,
            self._step_over_btn,
            self._step_into_btn,
            self._step_out_btn,
            self._stop_btn,
        ):
            btn_row.addWidget(btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._position_label: QLabel | None
        if keep_visible_when_idle:
            # Pause line lives on :class:`ScriptEditorPane` status bar.
            self._position_label = None
        else:
            self._position_label = QLabel("Idle")
            self._position_label.setObjectName("mutedLabel")
            self._position_label.setWordWrap(True)
            layout.addWidget(self._position_label)

        self._set_buttons_enabled(False)
        if not keep_visible_when_idle:
            self.hide()

    def _make_start_debug_btn(self) -> QPushButton:
        """Start-debug control for the script output **Debugger** tab (idle only)."""
        btn = QPushButton()
        btn.setIcon(phi("bug", size=14))
        btn.setToolTip("Start debug (breakpoints)")
        btn.setFixedSize(28, 28)
        btn.setObjectName("iconButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.start_debug_requested.emit)
        return btn

    def set_start_debug_enabled(self, enabled: bool) -> None:
        """Enable or disable **Start debug** (e.g. while a worker is starting)."""
        if self._start_debug_btn is not None:
            self._start_debug_btn.setEnabled(enabled)

    def _set_start_debug_visible(self, visible: bool) -> None:
        if self._start_debug_btn is not None:
            self._start_debug_btn.setVisible(visible)

    def _sync_script_debugger_idle_chrome(self, *, paused: bool) -> None:
        """Show **Start debug** when idle; hide it while paused so step row stays compact."""
        if not self._keep_visible_when_idle:
            return
        self._set_start_debug_visible(not paused)
        if not paused:
            self.set_start_debug_enabled(True)

    def _make_btn(self, icon_name: str, tooltip: str, mode: str) -> QPushButton:
        btn = QPushButton()
        btn.setIcon(phi(icon_name, size=14))
        btn.setToolTip(tooltip)
        btn.setFixedSize(28, 28)
        btn.setObjectName("iconButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.step_requested.emit(mode))
        return btn

    def _make_breakpoint_action_btn(
        self,
        icon_name: str,
        tooltip: str,
        on_click: Callable[[], None],
    ) -> QPushButton:
        btn = QPushButton()
        btn.setIcon(phi(icon_name, color=COLOR_TEXT, size=14))
        btn.setToolTip(tooltip)
        btn.setFixedSize(28, 28)
        btn.setObjectName("debugBreakpointToolbarButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(on_click)
        return btn

    def _make_breakpoint_toggle_btn(
        self,
        icon_name: str,
        tooltip_on: str,
        tooltip_off: str,
        on_toggled: Callable[[bool], None],
        *,
        checked: bool = False,
    ) -> QPushButton:
        btn = QPushButton()
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setProperty("_bp_icon", icon_name)
        btn.setToolTip(tooltip_on if checked else tooltip_off)
        btn.setFixedSize(28, 28)
        btn.setObjectName("debugBreakpointToolbarButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.toggled.connect(on_toggled)
        btn.toggled.connect(lambda state, b=btn: self._sync_breakpoint_toggle_icon(b, state))
        self._sync_breakpoint_toggle_icon(btn, checked)
        return btn

    @staticmethod
    def _sync_breakpoint_toggle_icon(btn: QPushButton, checked: bool) -> None:
        """Refresh toggle glyph contrast (accent when active)."""
        icon_name = str(btn.property("_bp_icon") or "")
        if not icon_name:
            return
        color = COLOR_ACCENT if checked else COLOR_TEXT
        btn.setIcon(phi(icon_name, color=color, size=14))

    def _on_disable_breakpoints_toggled(self, checked: bool) -> None:
        self._disable_bp_btn.setToolTip(
            "Breakpoints disabled (click to enable)" if checked else "Disable breakpoints"
        )
        self.breakpoints_enabled_toggled.emit(not checked)

    def _on_pause_on_exceptions_toggled(self, checked: bool) -> None:
        self._exception_bp_btn.setToolTip(
            "Break on uncaught exceptions"
            if checked
            else "Do not break on uncaught exceptions (click to enable)"
        )
        self.pause_on_exceptions_toggled.emit(checked)

    def sync_breakpoint_toolbar(self, protocol: DebugProtocol) -> None:
        """Mirror protocol breakpoint flags onto the toolbar toggles."""
        self._disable_bp_btn.blockSignals(True)
        self._disable_bp_btn.setChecked(not protocol.breakpoints_enabled)
        self._disable_bp_btn.blockSignals(False)
        self._on_disable_breakpoints_toggled(self._disable_bp_btn.isChecked())

        self._exception_bp_btn.blockSignals(True)
        self._exception_bp_btn.setChecked(protocol.pause_on_exceptions)
        self._exception_bp_btn.blockSignals(False)
        self._on_pause_on_exceptions_toggled(self._exception_bp_btn.isChecked())
        self._sync_breakpoint_toggle_icon(self._disable_bp_btn, self._disable_bp_btn.isChecked())
        self._sync_breakpoint_toggle_icon(
            self._exception_bp_btn, self._exception_bp_btn.isChecked()
        )

    def reset_breakpoint_toolbar(self) -> None:
        """Restore default breakpoint toolbar state when no session is active."""
        self._disable_bp_btn.blockSignals(True)
        self._disable_bp_btn.setChecked(False)
        self._disable_bp_btn.blockSignals(False)
        self._on_disable_breakpoints_toggled(False)

        self._exception_bp_btn.blockSignals(True)
        self._exception_bp_btn.setChecked(True)
        self._exception_bp_btn.blockSignals(False)
        self._on_pause_on_exceptions_toggled(True)
        self._sync_breakpoint_toggle_icon(self._disable_bp_btn, False)
        self._sync_breakpoint_toggle_icon(self._exception_bp_btn, True)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for btn in (
            self._continue_btn,
            self._step_over_btn,
            self._step_into_btn,
            self._step_out_btn,
            self._stop_btn,
        ):
            btn.setEnabled(enabled)

    def update_pause(self, info: DebugPauseInfo) -> None:
        """Set position text and enable step controls."""
        if self._position_label is not None:
            self._position_label.setObjectName("sidebarTitleLabel")
            self._position_label.setText(format_debug_pause_status(info))
        self._sync_script_debugger_idle_chrome(paused=True)
        self._set_buttons_enabled(True)

    def clear_session(self) -> None:
        """Disable controls after a session ends."""
        if self._position_label is not None:
            self._position_label.setText("Session ended")
            self._position_label.setObjectName("mutedLabel")
        self._sync_script_debugger_idle_chrome(paused=False)
        self._set_buttons_enabled(False)

    def set_idle(self) -> None:
        """Reset toolbar to idle."""
        if self._position_label is not None:
            self._position_label.setText("Idle")
            self._position_label.setObjectName("mutedLabel")
        self._sync_script_debugger_idle_chrome(paused=False)
        self._set_buttons_enabled(False)


class DebugPanel(QWidget):
    """Sidebar panel: controls and split inspector (call stack + watches | scopes)."""

    step_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Stack controls and :class:`DebugInspectorSplit`."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._controls = DebugControls(self)
        self._controls.step_requested.connect(self.step_requested.emit)
        layout.addWidget(self._controls)

        self._inspector = DebugInspectorSplit(self)
        layout.addWidget(self._inspector, 1)

        self._protocol: DebugProtocol | None = None

    @property
    def _call_stack(self):
        return self._inspector.call_stack

    @property
    def _variables(self):
        """Back-compat: scopes pane (``_tree`` is the scope variables tree)."""
        return self._inspector.scopes

    def set_protocol(self, protocol: DebugProtocol | None) -> None:
        """Attach the active debug protocol for watch / frame selection."""
        self._protocol = protocol
        self._inspector.set_protocol(protocol)

    @property
    def _position_label(self) -> QLabel | None:
        return self._controls._position_label

    @property
    def _continue_btn(self) -> QPushButton:
        return self._controls._continue_btn

    @property
    def _step_over_btn(self) -> QPushButton:
        return self._controls._step_over_btn

    @property
    def _step_into_btn(self) -> QPushButton:
        return self._controls._step_into_btn

    @property
    def _step_out_btn(self) -> QPushButton:
        return self._controls._step_out_btn

    @property
    def _stop_btn(self) -> QPushButton:
        return self._controls._stop_btn

    @property
    def _tree(self) -> QTreeWidget:
        return self._inspector.scopes_tree

    def update_pause(self, info: DebugPauseInfo) -> None:
        """Refresh controls, call stack, scopes, and watches."""
        self._controls.update_pause(info)
        self._inspector.update_pause(info)

    def clear_session(self) -> None:
        """End-of-session state for all sections."""
        self._controls.clear_session()
        self._inspector.clear_session()
        self.set_protocol(None)

    def set_idle(self) -> None:
        """Reset all sections to the idle state."""
        self._controls.set_idle()
        self._inspector.set_idle()
        self.set_protocol(None)
