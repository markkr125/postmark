"""Diff toolbar with search, navigation, copy, counter, and whitespace."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QWidget,
)

from ui.styling.icons import phi

# Whitespace handling modes.
WS_DO_NOT_IGNORE = "Do not ignore"
WS_TRIM = "Trim whitespace"
WS_IGNORE_ALL = "Ignore all whitespace"

# Flat icon-button stylesheet (no chrome, just an icon).
_FLAT_BTN_CSS = """
    QPushButton {
        border: none;
        background: transparent;
        padding: 2px;
        border-radius: 3px;
    }
    QPushButton:hover { background: rgba(0,0,0,0.08); }
    QPushButton:pressed { background: rgba(0,0,0,0.14); }
"""


class _DiffToolbar(QWidget):
    """Toolbar with search, diff navigation, copy, counter, and whitespace."""

    navigate_prev = Signal()
    navigate_next = Signal()
    copy_requested = Signal()
    whitespace_changed = Signal(str)
    search_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the toolbar layout."""
        super().__init__(parent)
        self.setObjectName("diffToolbar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 8, 2)
        layout.setSpacing(2)

        # Search field (left, fixed width aligned with version list)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by content")
        self._search.setClearButtonEnabled(True)
        self._search.setObjectName("versionSearch")
        self._search.addAction(
            phi("magnifying-glass", size=14),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._search.textChanged.connect(self.search_changed)
        layout.addWidget(self._search)

        layout.addSpacing(8)

        # Navigation: prev / next diff
        self._prev_btn = QPushButton()
        self._prev_btn.setIcon(phi("caret-up", size=16))
        self._prev_btn.setToolTip("Previous difference")
        self._prev_btn.setFixedSize(26, 26)
        self._prev_btn.setStyleSheet(_FLAT_BTN_CSS)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.clicked.connect(self.navigate_prev)
        layout.addWidget(self._prev_btn)

        self._next_btn = QPushButton()
        self._next_btn.setIcon(phi("caret-down", size=16))
        self._next_btn.setToolTip("Next difference")
        self._next_btn.setFixedSize(26, 26)
        self._next_btn.setStyleSheet(_FLAT_BTN_CSS)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self.navigate_next)
        layout.addWidget(self._next_btn)

        layout.addSpacing(8)

        # Whitespace toggle dropdown
        self._ws_btn = QToolButton()
        self._ws_btn.setText(WS_DO_NOT_IGNORE)
        self._ws_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._ws_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ws_menu = QMenu(self._ws_btn)
        for mode in (WS_DO_NOT_IGNORE, WS_TRIM, WS_IGNORE_ALL):
            action = ws_menu.addAction(mode)
            action.triggered.connect(lambda _checked, m=mode: self._on_ws_changed(m))
        self._ws_btn.setMenu(ws_menu)
        layout.addWidget(self._ws_btn)

        layout.addSpacing(4)

        # Copy button
        self._copy_btn = QPushButton()
        self._copy_btn.setIcon(phi("copy", size=16))
        self._copy_btn.setToolTip("Copy selected version")
        self._copy_btn.setFixedSize(26, 26)
        self._copy_btn.setStyleSheet(_FLAT_BTN_CSS)
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.clicked.connect(self.copy_requested)
        layout.addWidget(self._copy_btn)

        # Push counter to the far right
        layout.addStretch()

        # Diff counter
        self._counter_label = QLabel()
        self._counter_label.setObjectName("mutedLabel")
        layout.addWidget(self._counter_label)

    def set_diff_count(self, count: int) -> None:
        """Update the differences counter label."""
        suffix = "s" if count != 1 else ""
        self._counter_label.setText(f"{count} difference{suffix}")

    @property
    def search_widget(self) -> QLineEdit:
        """Return the search field for external width synchronisation."""
        return self._search

    def _on_ws_changed(self, mode: str) -> None:
        """Handle whitespace mode selection."""
        self._ws_btn.setText(mode)
        self.whitespace_changed.emit(mode)
