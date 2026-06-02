"""Global (left-rail) mode helpers for :class:`HistoryPanel`."""

# Mixin methods use attributes defined on :class:`HistoryPanel`.
# mypy: disable-error-code=attr-defined

from __future__ import annotations

from typing import Literal, cast

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QWidget,
)

from ui.styling.icons import phi
from ui.styling.theme import COLOR_WHITE


class _HistoryPanelGlobalMixin:
    """Global workspace history: list all sends and emit open navigation requests."""

    _mode: Literal["request", "global"]
    _global_header: QWidget | None
    _detail_host: QWidget
    _detail_header_row: QHBoxLayout
    _content_splitter: QSplitter
    _open_btn: QPushButton

    def _init_global_mode_state(self) -> None:
        """Set mode defaults; call from :class:`HistoryPanel` ``__init__``."""
        self._mode = "request"
        self._global_header = None

    def set_global_mode(self) -> None:
        """Configure this panel for the left-rail workspace history flyout."""
        self._mode = "global"
        self.setObjectName("globalHistoryPanel")
        self._request_id = None
        self._request_name = ""
        self._is_persisted_request = False
        self._ensure_global_header()
        self._place_date_filter_btn_for_mode()
        self._replay_btn.hide()
        self._open_btn.hide()
        self._apply_global_list_only_layout(True)
        self.refresh()

    def set_request_mode(self) -> None:
        """Restore right-rail per-request mode (objectName and chrome)."""
        self._mode = "request"
        self.setObjectName("requestHistoryPanel")
        self._open_btn.hide()
        self._replay_btn.show()
        self._apply_global_list_only_layout(False)
        if self._global_header is not None:
            self._global_header.hide()
        self._place_date_filter_btn_for_mode()

    def _is_global_mode(self) -> bool:
        return self._mode == "global"

    def _ensure_global_header(self) -> None:
        """Add title + refresh row for the left flyout."""
        if self._global_header is not None:
            self._global_header.show()
            return
        header = QWidget()
        header.setObjectName("globalHistoryHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        title = QLabel("History")
        title.setObjectName("sectionLabel")
        row.addWidget(title)
        row.addStretch(1)
        if self._refresh_btn.parent() is not None:
            self._refresh_btn.setParent(None)
        row.addWidget(self._refresh_btn)
        root = self.layout()
        if root is not None:
            root.insertWidget(0, header)
        self._global_header = header
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.show()
        self._place_date_filter_btn_for_mode()

    def _apply_global_list_only_layout(self, list_only: bool) -> None:
        """Hide the read-only detail stack on the left rail; list-only navigation."""
        self._detail_host.setVisible(not list_only)
        if list_only:
            self._content_splitter.setSizes([10_000, 0])
        else:
            self._content_splitter.setSizes([180, 280])

    def _build_open_button(self) -> QPushButton:
        """Hidden placeholder; global open is click-to-navigate on the tree."""
        btn = QPushButton()
        btn.setIcon(phi("arrow-square-out", color=COLOR_WHITE, size=16))
        btn.setObjectName("requestHistoryOpenButton")
        btn.setFixedSize(28, 28)
        btn.hide()
        return btn

    def _emit_entry_open(self, entry_id: int) -> None:
        """Emit :attr:`entry_open_requested` when in global mode."""
        if self._is_global_mode():
            self.entry_open_requested.emit(entry_id)

    def _global_empty_message(self) -> str:
        return "No send history yet.\n\nSend a request to record an entry here."

    def _global_context_menu_actions(self, entry_id: int) -> list[QAction]:
        host = cast(QWidget, self)
        open_action = QAction("Open", host)
        open_action.triggered.connect(lambda: self._emit_entry_open(entry_id))
        return [open_action]
