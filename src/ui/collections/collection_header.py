"""Header widget with search bar and action buttons for the collection sidebar."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import COLOR_BORDER, COLOR_HOVER_BG, COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_WHITE


# ----------------------------------------------------------------------
# Header management subclass
# ----------------------------------------------------------------------
class CollectionHeader(QWidget):
    """Manages the header with add button and search."""

    # Accept any object (int or None)
    new_collection_requested = Signal(object)  # parent_id or None
    new_request_requested = Signal(object)  # same for requests
    search_changed = Signal(str)
    import_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise header bar with search field and action buttons."""
        super().__init__(parent)
        self.setFixedHeight(75)
        self.setStyleSheet("background: transparent;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 10)
        main_layout.setSpacing(8)

        # Top row: import button aligned to right
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        top_row.addStretch()

        # Import button (small, aligned to right)
        self._import_btn = QToolButton(self)
        self._import_btn.setStyleSheet(f"background: {COLOR_WHITE};")
        self._import_btn.setText("Import")
        self._import_btn.setToolTip("Import collections/requests")
        self._import_btn.clicked.connect(lambda: self.import_requested.emit())
        # TODO: set icon once a bundled asset is available
        top_row.addWidget(self._import_btn)

        main_layout.addLayout(top_row)

        # Bottom row: + button and search
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        # "+" button
        self._plus_btn = QToolButton(self)
        self._plus_btn.setStyleSheet(f"background: {COLOR_WHITE};")
        self._plus_btn.setIcon(QIcon.fromTheme("list-add"))
        self._plus_btn.setToolTip("Add new collection")
        bottom_row.addWidget(self._plus_btn)

        # Plus-menu
        self._plus_menu = QMenu(self)
        new_act = QAction("New collection", self)
        self._plus_menu.addAction(new_act)
        self._plus_menu.setStyleSheet(
            f"""
    QMenu {{
        background: {COLOR_WHITE};
        border: 1px solid {COLOR_BORDER};
    }}
    QMenu::item {{
        padding: 4px 12px;
        color: {COLOR_TEXT};
        font-weight: bold;
    }}
    QMenu::item:selected:enabled {{
        background-color: {COLOR_HOVER_BG};
        color: {COLOR_WHITE};
    }}
        """
        )

        self._plus_btn.clicked.connect(
            lambda: self._plus_menu.exec(
                self._plus_btn.mapToGlobal(self._plus_btn.rect().bottomLeft())
            )
        )
        new_act.triggered.connect(lambda: self.new_collection_requested.emit(None))

        # Search box that expands
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Search collections")
        self._search.setStyleSheet(
            f"""
            background: {COLOR_WHITE};
            placeholder-text-color: {COLOR_TEXT_MUTED};
        """
        )
        self._search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Use a theme icon if available; fall back to a bundled SVG/PNG if needed.
        magnify_icon = QIcon.fromTheme("search")  # typical theme name
        if magnify_icon.isNull():
            # e.g. use a local SVG file shipped with the app:
            magnify_icon = QIcon(":/icons/magnifier.svg")

        # Add the icon as an action positioned *leading* (left) inside the QLineEdit
        self._search.addAction(magnify_icon, QLineEdit.ActionPosition.LeadingPosition)

        bottom_row.addWidget(self._search)
        main_layout.addLayout(bottom_row)

        # Emit search signal on each keystroke
        self._search.textChanged.connect(lambda txt: self.search_changed.emit(txt))
