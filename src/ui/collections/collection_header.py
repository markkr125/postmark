"""Header widget with search bar and action buttons for the collection sidebar."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.collections.new_item_popup import NewItemPopup
from ui.styling.icons import phi


# ----------------------------------------------------------------------
# Header management subclass
# ----------------------------------------------------------------------
class CollectionHeader(QWidget):
    """Manages the header with section label, New/Import buttons, and search."""

    # Accept any object (int or None)
    new_collection_requested = Signal(object)  # parent_id or None
    new_request_requested = Signal(object)  # same for requests
    search_changed = Signal(str)
    import_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise header bar with search field and action buttons."""
        super().__init__(parent)
        self.setFixedHeight(70)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 6, 0, 6)
        main_layout.setSpacing(6)

        # -- Row 1: section label + action buttons --------------------
        top_row = QHBoxLayout()
        top_row.setContentsMargins(8, 0, 8, 0)
        top_row.setSpacing(4)

        section_label = QLabel("Collections")
        section_label.setObjectName("sidebarSectionLabel")
        section_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(section_label)
        top_row.addStretch()

        # "New" button with icon-grid popup
        self._plus_btn = QToolButton(self)
        self._plus_btn.setText("New")
        self._plus_btn.setIcon(phi("plus"))
        self._plus_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._plus_btn.setObjectName("sidebarToolButton")
        self._plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plus_btn.setToolTip("Create new collection or request")
        top_row.addWidget(self._plus_btn)

        # Dialog (replaces the old QMenu)
        self._popup = NewItemPopup(self)
        self._popup.new_request_clicked.connect(self._on_popup_new_request)
        self._popup.new_collection_clicked.connect(lambda: self.new_collection_requested.emit(None))
        self._plus_btn.clicked.connect(lambda: self._popup.exec())

        self._selected_collection_id: int | None = None

        # "Import" button
        self._import_btn = QToolButton(self)
        self._import_btn.setText("Import")
        self._import_btn.setIcon(phi("download-simple"))
        self._import_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._import_btn.setObjectName("sidebarToolButton")
        self._import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_btn.setToolTip("Import collections or requests")
        self._import_btn.clicked.connect(lambda: self.import_requested.emit())
        top_row.addWidget(self._import_btn)

        main_layout.addLayout(top_row)

        # -- Row 2: search bar ----------------------------------------
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Search collections")
        self._search.setObjectName("sidebarSearch")
        self._search.setMinimumHeight(28)
        self._search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        magnify_icon = phi("magnifying-glass")
        self._search.addAction(magnify_icon, QLineEdit.ActionPosition.LeadingPosition)

        main_layout.addWidget(self._search)

        # Emit search signal on each keystroke
        self._search.textChanged.connect(lambda txt: self.search_changed.emit(txt))

    def set_selected_collection_id(self, collection_id: int | None) -> None:
        """Update the currently selected collection for the 'New request' action."""
        self._selected_collection_id = collection_id

    def _on_popup_new_request(self) -> None:
        """Emit ``new_request_requested`` -- ``None`` means draft (no collection)."""
        self.new_request_requested.emit(None)
