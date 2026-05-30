"""Left flyout placeholder for user-defined local scripts (empty list shell)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.styling.theme import LEFT_NAV_PANEL_MARGIN_H_LEFT_PX, LEFT_NAV_PANEL_MARGIN_H_RIGHT_PX

# Inset between the QSS list frame and the scroll document (matches environments).
_LIST_FRAME_SHIM_PX = 1
_LIST_BODY_PAD_H_PX = 3
_LIST_ROWS_BOTTOM_MARGIN_PX = 4
_PANEL_ROOT_BOTTOM_MARGIN_PX = 14
_PANEL_HEADER_LIST_GAP_PX = 6


class LocalScriptsSidebarPanel(QWidget):
    """Header plus bordered scroll region styled like the environments list (empty).

    Populated later; for now shows a single empty-state message inside the list
    frame so layout matches :class:`EnvironmentSidebarPanel`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the section header and empty list shell."""
        super().__init__(parent)
        self.setObjectName("localScriptsSidebarPanel")
        self.setMinimumHeight(96)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            LEFT_NAV_PANEL_MARGIN_H_LEFT_PX,
            0,
            LEFT_NAV_PANEL_MARGIN_H_RIGHT_PX,
            _PANEL_ROOT_BOTTOM_MARGIN_PX,
        )
        root.setSpacing(_PANEL_HEADER_LIST_GAP_PX)

        header = QHBoxLayout()
        header.setContentsMargins(0, 6, 0, 0)
        header.setSpacing(4)
        title = QLabel("Local scripts")
        title.setObjectName("sidebarSectionLabel")
        header.addWidget(title)
        header.addStretch()
        root.addLayout(header)

        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("localScriptsSidebarScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._list_host = QWidget()
        self._list_host.setObjectName("localScriptsSidebarList")
        self._list_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        list_outer = QVBoxLayout(self._list_host)
        list_outer.setContentsMargins(
            _LIST_FRAME_SHIM_PX,
            _LIST_FRAME_SHIM_PX,
            _LIST_FRAME_SHIM_PX,
            _LIST_FRAME_SHIM_PX,
        )
        list_outer.setSpacing(0)

        self._list_body = QWidget(self._list_host)
        self._list_body.setObjectName("localScriptsSidebarListBody")
        list_outer.addWidget(self._list_body, 1)

        body_layout = QVBoxLayout(self._list_body)
        body_layout.setContentsMargins(
            _LIST_BODY_PAD_H_PX,
            0,
            _LIST_BODY_PAD_H_PX,
            _LIST_ROWS_BOTTOM_MARGIN_PX,
        )
        body_layout.setSpacing(0)

        empty = QLabel("No local scripts yet.")
        empty.setObjectName("emptyStateLabel")
        empty.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        empty.setWordWrap(True)
        body_layout.addWidget(empty)
        body_layout.addStretch(1)

        self._scroll.setWidget(self._list_host)
        root.addWidget(self._scroll, 1)
