"""Click-triggered help popups for left-sidebar section headers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from ui.styling.icons import phi
from ui.widgets.info_popup import InfoPopup

COLLECTIONS_INTRO = (
    "Organize HTTP requests in folders and collections. Create requests, group them "
    "by API or feature, import from common formats, and open any item in a tab to "
    "edit and send."
)

ENVIRONMENTS_INTRO = (
    "Store variables as key-value sets for development, staging, production, or "
    "any context. Use {{variable}} in URLs, headers, and bodies. The active "
    "environment applies across open request tabs until you change or clear it."
)

LOCAL_SCRIPTS_INTRO = (
    "Reusable JavaScript, TypeScript, and Python modules for your workspace. "
    "Organize scripts in folders, edit them here, and reuse shared helpers "
    "across collection, folder, and request scripts."
)


class SidebarSectionInfoPopup(InfoPopup):
    """Stylish explainer shown below a sidebar section info button."""

    def __init__(self, title: str, body: str, parent: QWidget | None = None) -> None:
        """Build a titled popup with wrapped *body* text."""
        super().__init__(parent)
        self.setMinimumWidth(260)
        self.setMaximumWidth(320)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("infoPopupTitle")
        header.addWidget(title_label, 1)

        close_btn = QToolButton(self)
        close_btn.setObjectName("infoPopupCloseButton")
        close_btn.setIcon(phi("x", size=14))
        close_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        close_btn.setAutoRaise(True)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close")
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)

        header_host = QWidget(self)
        header_host.setLayout(header)
        self.content_layout.addWidget(header_host)

        body_label = QLabel(body)
        body_label.setWordWrap(True)
        body_label.setObjectName("mutedLabel")
        self.content_layout.addWidget(body_label)


def make_sidebar_info_button(
    parent: QWidget,
    *,
    tooltip: str,
    on_toggle: object,
) -> QToolButton:
    """Return a compact (i) button wired to *on_toggle*."""
    btn = QToolButton(parent)
    btn.setIcon(phi("info"))
    btn.setObjectName("sidebarSectionInfoButton")
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(tooltip)
    btn.setAutoRaise(True)
    btn.clicked.connect(on_toggle)  # type: ignore[arg-type]
    return btn


def toggle_sidebar_section_info(
    anchor: QToolButton,
    popup_holder: list[SidebarSectionInfoPopup | None],
    *,
    title: str,
    body: str,
    parent: QWidget,
) -> None:
    """Show, hide, or recreate the section help popup for *anchor*.

    *popup_holder* is a single-element list so callers can keep a nullable popup
    without nonlocal declarations in nested scopes.
    """
    popup = popup_holder[0]
    if popup is not None and popup.isVisible():
        popup.close()
        return
    if popup is None:
        popup = SidebarSectionInfoPopup(title, body, parent)
        popup_holder[0] = popup
    popup.show_below(anchor)
