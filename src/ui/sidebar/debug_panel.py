"""Debug panel for the right sidebar.

Displays local variables, current position, and step controls during
a script debug session.  Opened automatically when the debugger pauses
and closed when the debug session ends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.styling.icons import phi

if TYPE_CHECKING:
    from services.scripting.debug import DebugPauseInfo


class DebugPanel(QWidget):
    """Sidebar panel showing debug state and step controls.

    Signals:
        step_requested(str): Emitted with step mode name
            (``continue``, ``step_over``, ``step_into``,
            ``step_out``, ``stop``).
    """

    step_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the debug panel with step buttons and variable list."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # -- Step controls -------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._continue_btn = self._make_btn("play", "Continue", "continue")
        self._step_over_btn = self._make_btn("arrow-line-down", "Step Over", "step_over")
        self._step_into_btn = self._make_btn("arrow-line-down-right", "Step Into", "step_into")
        self._step_out_btn = self._make_btn("arrow-line-up-right", "Step Out", "step_out")
        self._stop_btn = self._make_btn("stop", "Stop", "stop")
        self._stop_btn.setObjectName("dangerButton")

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

        # -- Position info -------------------------------------------------
        self._position_label = QLabel("Idle")
        self._position_label.setObjectName("mutedLabel")
        self._position_label.setWordWrap(True)
        layout.addWidget(self._position_label)

        # -- Variables section ---------------------------------------------
        var_header = QLabel("Local Variables")
        var_header.setObjectName("sectionLabel")
        layout.addWidget(var_header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        layout.addWidget(self._scroll, 1)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(2)
        self._content_layout.addStretch()
        self._scroll.setWidget(self._content)

        self._set_buttons_enabled(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def update_pause(self, info: DebugPauseInfo) -> None:
        """Refresh display with data from a debug pause event."""
        source = info.get("source_name", "")
        line = info.get("line", 0)
        script_type = info.get("script_type", "")
        self._position_label.setText(
            f"Paused at line {line + 1}  \u2014  {script_type}" + (f" ({source})" if source else "")
        )
        self._load_variables(info.get("local_vars", {}))
        self._set_buttons_enabled(True)

    def clear_session(self) -> None:
        """Reset the panel when a debug session ends."""
        self._position_label.setText("Session ended")
        self._clear_variables()
        self._set_buttons_enabled(False)

    def set_idle(self) -> None:
        """Reset to idle state (no active session)."""
        self._position_label.setText("Idle")
        self._clear_variables()
        self._set_buttons_enabled(False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _make_btn(self, icon_name: str, tooltip: str, mode: str) -> QPushButton:
        """Create a step-control button."""
        btn = QPushButton()
        btn.setIcon(phi(icon_name, size=14))
        btn.setToolTip(tooltip)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.step_requested.emit(mode))
        return btn

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable all step buttons."""
        for btn in (
            self._continue_btn,
            self._step_over_btn,
            self._step_into_btn,
            self._step_out_btn,
            self._stop_btn,
        ):
            btn.setEnabled(enabled)

    def _load_variables(self, variables: dict[str, Any]) -> None:
        """Populate the variable list from a locals dict."""
        self._clear_variables()
        if not variables:
            empty = QLabel("No local variables")
            empty.setObjectName("mutedLabel")
            self._content_layout.insertWidget(0, empty)
            return
        for name, value in sorted(variables.items()):
            row = QHBoxLayout()
            row.setSpacing(8)
            key_lbl = QLabel(name)
            key_lbl.setObjectName("mutedLabel")
            key_lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
            val_lbl = QLabel(str(value))
            val_lbl.setToolTip(str(value))
            val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(key_lbl)
            row.addWidget(val_lbl, 1)
            self._content_layout.insertLayout(self._content_layout.count() - 1, row)

    def _clear_variables(self) -> None:
        """Remove all variable rows from the content layout."""
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                continue
            sub = item.layout()
            if sub is not None:
                self._clear_sub_layout(sub)

    @staticmethod
    def _clear_sub_layout(layout: Any) -> None:
        """Recursively delete all items in a sub-layout."""
        while layout.count():
            child = layout.takeAt(0)
            if child is None:
                continue
            w = child.widget()
            if w is not None:
                w.setParent(None)
            elif child.layout() is not None:
                DebugPanel._clear_sub_layout(child.layout())
