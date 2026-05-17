"""Resizable sidebar panel listing environments with per-row activation controls."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from services.environment_service import EnvironmentService
from ui.styling.icons import phi
from ui.styling.theme import TREE_ROW_HEIGHT
from ui.widgets.info_popup import ClickableLabel

# Inset between the QSS list frame and the scroll document (avoids hover under the border).
_ENV_LIST_FRAME_SHIM_PX = 1
# Extra horizontal inset inside the frame shim (keeps row :hover off the inner edge).
_ENV_LIST_BODY_PAD_H_PX = 3
_ENV_LIST_ROWS_BOTTOM_MARGIN_PX = 4
# Bottom margin for the whole panel (air above the splitter / next UI).
_ENV_PANEL_ROOT_BOTTOM_MARGIN_PX = 14
# Space between the "Environments" header row and the bordered list below.
_ENV_PANEL_HEADER_LIST_GAP_PX = 6
_ENV_ROW_ICON_PX = 14
_ENV_ROW_ICON_CELL_PX = 16
_ENV_ROW_ICON_NAME_GAP_PX = 6

_ENV_ROW_BUTTON_WIDTH_PX = 76
_ENV_ROW_BUTTON_V_PAD_PX = 12


class EnvironmentSidebarPanel(QWidget):
    """List environments with **Set active** / **Clear** actions (mutually exclusive).

    Each row shows a globe icon, the environment name, and one compact action button.
    At most one environment is **active** at a time; that ID is the global active
    environment. The active row shows **Clear** to disable selection; other rows show
    **Set active**. When the list is empty, a short message and a clickable hint emit
    the same signal as **Manage** (open the environments editor tab).

    Signals:
        environment_changed: Emitted with ``int`` environment id or ``None``.
        manage_requested: Emitted when the user clicks **Manage**.
    """

    environment_changed = Signal(object)  # int | None
    manage_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the section header, manage control, and scrollable row list."""
        super().__init__(parent)
        self.setObjectName("environmentSidebarPanel")
        self.setMinimumHeight(96)
        self._active_env_id: int | None = None
        self._last_envs: list[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, _ENV_PANEL_ROOT_BOTTOM_MARGIN_PX)
        root.setSpacing(_ENV_PANEL_HEADER_LIST_GAP_PX)

        header = QHBoxLayout()
        header.setContentsMargins(8, 6, 8, 0)
        header.setSpacing(4)
        title = QLabel("Environments")
        title.setObjectName("sidebarSectionLabel")
        header.addWidget(title)
        header.addStretch()

        self._manage_btn = QToolButton(self)
        self._manage_btn.setText("Manage")
        self._manage_btn.setIcon(phi("gear", size=14))
        self._manage_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._manage_btn.setObjectName("sidebarToolButton")
        self._manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._manage_btn.setToolTip("Manage environments")
        self._manage_btn.clicked.connect(self.manage_requested.emit)
        header.addWidget(self._manage_btn)
        root.addLayout(header)

        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("environmentSidebarScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._list_host = QWidget()
        self._list_host.setObjectName("environmentSidebarList")
        # Keeps QSS border/background and child geometry consistent (avoids hover bleeding
        # under the list frame on some styles).
        self._list_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        _list_outer = QVBoxLayout(self._list_host)
        _list_outer.setContentsMargins(
            _ENV_LIST_FRAME_SHIM_PX,
            _ENV_LIST_FRAME_SHIM_PX,
            _ENV_LIST_FRAME_SHIM_PX,
            _ENV_LIST_FRAME_SHIM_PX,
        )
        _list_outer.setSpacing(0)

        self._list_body = QWidget(self._list_host)
        self._list_body.setObjectName("environmentSidebarListBody")
        _list_outer.addWidget(self._list_body, 1)

        self._rows_layout = QVBoxLayout(self._list_body)
        self._rows_layout.setContentsMargins(
            _ENV_LIST_BODY_PAD_H_PX,
            0,
            _ENV_LIST_BODY_PAD_H_PX,
            _ENV_LIST_ROWS_BOTTOM_MARGIN_PX,
        )
        self._rows_layout.setSpacing(0)

        self._scroll.setWidget(self._list_host)
        root.addWidget(self._scroll, 1)

    def current_environment_id(self) -> int | None:
        """Return the globally active environment id, or ``None``."""
        return self._active_env_id

    def refresh(self) -> None:
        """Reload rows from ``EnvironmentService.fetch_all()``."""
        envs = EnvironmentService.fetch_all()
        self._rebuild_rows(envs)

    def _clear_rows(self) -> None:
        """Remove all row widgets and trailing stretch from the list layout."""
        while self._rows_layout.count() > 0:
            item = self._rows_layout.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _rebuild_rows(self, envs: list[dict[str, Any]], emit_if_changed: bool = True) -> None:
        """Replace row widgets from *envs* while preserving a valid active id."""
        prev = self._active_env_id
        self._last_envs = list(envs)
        ids = {int(e["id"]) for e in envs}
        if prev is not None and prev not in ids:
            self._active_env_id = None

        self._clear_rows()
        if not envs:
            empty_host = QWidget(self._list_body)
            empty_lay = QVBoxLayout(empty_host)
            empty_lay.setContentsMargins(8, 14, 8, 10)
            empty_lay.setSpacing(8)

            msg = QLabel("No environments yet.")
            msg.setObjectName("emptyStateLabel")
            msg.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            msg.setWordWrap(True)
            empty_lay.addWidget(msg)

            hint = ClickableLabel("Click here to add one.")
            hint.setObjectName("environmentSidebarEmptyHint")
            hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            hint.setWordWrap(True)
            hint.clicked.connect(self.manage_requested.emit)
            empty_lay.addWidget(hint)

            self._rows_layout.addWidget(empty_host, 0)
            self._rows_layout.addStretch(1)

            if emit_if_changed and prev != self._active_env_id:
                self.environment_changed.emit(self._active_env_id)
            return

        btn_h = max(18, TREE_ROW_HEIGHT - _ENV_ROW_BUTTON_V_PAD_PX)
        for env in envs:
            eid = int(env["id"])
            name = str(env.get("name", ""))

            row = QWidget(self._list_body)
            row.setObjectName("environmentSidebarRow")
            row.setFixedHeight(TREE_ROW_HEIGHT)
            row_lay = QHBoxLayout(row)
            row_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            # No extra left margin: list host horizontal gutter + icon + small gap only.
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(_ENV_ROW_ICON_NAME_GAP_PX)

            icon_lbl = QLabel(row)
            icon_lbl.setObjectName("environmentSidebarRowIcon")
            icon_lbl.setPixmap(
                phi("globe", size=_ENV_ROW_ICON_PX).pixmap(
                    QSize(_ENV_ROW_ICON_PX, _ENV_ROW_ICON_PX)
                )
            )
            icon_lbl.setFixedSize(_ENV_ROW_ICON_CELL_PX, _ENV_ROW_ICON_CELL_PX)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_lay.addWidget(icon_lbl, 0)

            name_lbl = QLabel(name)
            name_lbl.setObjectName("environmentSidebarNameLabel")
            name_lbl.setWordWrap(False)
            name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            row_lay.addWidget(name_lbl, 1)

            if self._active_env_id == eid:
                action = QPushButton("Clear", row)
                action.setObjectName("environmentSidebarClearButton")
                action.setFixedWidth(_ENV_ROW_BUTTON_WIDTH_PX)
                action.setFixedHeight(btn_h)
                action.setCursor(Qt.CursorShape.PointingHandCursor)
                action.setToolTip("Stop using this environment for requests")
                action.clicked.connect(self._clear_active)
            else:
                action = QPushButton("Set active", row)
                action.setObjectName("environmentSidebarSetActiveButton")
                action.setFixedWidth(_ENV_ROW_BUTTON_WIDTH_PX)
                action.setFixedHeight(btn_h)
                action.setCursor(Qt.CursorShape.PointingHandCursor)
                action.setToolTip("Use this environment for variable substitution")
                action.clicked.connect(lambda *_a, env_id=eid: self._activate_env(env_id))
            row_lay.addWidget(action, 0)

            self._rows_layout.addWidget(row)

        self._rows_layout.addStretch(1)

        if emit_if_changed and prev != self._active_env_id:
            self.environment_changed.emit(self._active_env_id)

    def _activate_env(self, env_id: int) -> None:
        """Make *env_id* the sole active environment and notify listeners."""
        if self._active_env_id == env_id:
            return
        self._active_env_id = env_id
        self._rebuild_rows(self._last_envs, emit_if_changed=False)
        self.environment_changed.emit(env_id)

    def _clear_active(self) -> None:
        """Clear global active environment and notify listeners."""
        if self._active_env_id is None:
            return
        self._active_env_id = None
        self._rebuild_rows(self._last_envs, emit_if_changed=False)
        self.environment_changed.emit(None)
