"""Postman-style "Create New" dialog for creating new items.

Displays a centered dialog window with a tile grid offering options
like "HTTP Request" and "Collection".  Opened from the "New" button
in the collection sidebar header.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.styling.icons import phi


class _Tile(QPushButton):
    """A clickable icon tile with an icon above a label."""

    hovered = Signal()

    def __init__(
        self,
        icon_name: str,
        label: str,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise tile with a Phosphor icon and text label."""
        super().__init__(parent)
        self.setObjectName("newItemTile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(140, 110)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_label = QLabel()
        icon_label.setPixmap(phi(icon_name, size=36).pixmap(36, 36))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(icon_label)

        text_label = QLabel(label)
        text_label.setObjectName("newItemTileLabel")
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(text_label)

    def enterEvent(self, event: QEnterEvent) -> None:
        """Emit hovered signal on mouse enter."""
        super().enterEvent(event)
        self.hovered.emit()


class NewItemPopup(QDialog):
    """Centered dialog window for creating new requests or collections.

    Opened as a modal dialog from the "New" button — mirrors Postman's
    "Create New" window.
    """

    new_request_clicked = Signal()
    new_collection_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the dialog with a grid of item-type tiles."""
        super().__init__(parent)
        self.setWindowTitle("Create New")
        self.setObjectName("newItemPopup")
        self.setFixedSize(380, 260)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(4)

        # Title
        title = QLabel("What do you want to create?")
        title.setObjectName("newItemTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title)

        outer.addSpacing(12)

        # Tile grid — centered
        grid = QGridLayout()
        grid.setSpacing(16)
        grid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addLayout(grid)

        # Tiles
        http_tile = _Tile("globe", "HTTP Request", self)
        collection_tile = _Tile("folder-plus", "Collection", self)

        grid.addWidget(http_tile, 0, 0)
        grid.addWidget(collection_tile, 0, 1)

        http_tile.clicked.connect(self._on_http_clicked)
        collection_tile.clicked.connect(self._on_collection_clicked)

        # Description area at the bottom
        self._description = QLabel()
        self._description.setObjectName("newItemDescription")
        self._description.setWordWrap(True)
        self._description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._description.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._description.setFixedHeight(40)
        self._description.setText("Create a new HTTP request or collection.")
        outer.addWidget(self._description)

        http_tile.hovered.connect(
            lambda: self._description.setText("Create a new HTTP request draft tab.")
        )
        collection_tile.hovered.connect(
            lambda: self._description.setText("Create a new collection to organise your requests.")
        )

    def _on_http_clicked(self) -> None:
        """Emit signal and close dialog when HTTP tile is clicked."""
        self.new_request_clicked.emit()
        self.accept()

    def _on_collection_clicked(self) -> None:
        """Emit signal and close dialog when Collection tile is clicked."""
        self.new_collection_clicked.emit()
        self.accept()
