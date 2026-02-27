"""Header widget with search bar and action buttons for the collection sidebar."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


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
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(6)

        # -- Row 1: section label + action buttons --------------------
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        section_label = QLabel("Collections")
        section_label.setObjectName("sidebarSectionLabel")
        section_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(section_label)
        top_row.addStretch()

        # "New" button with dropdown menu
        self._plus_btn = QToolButton(self)
        self._plus_btn.setText("New")
        self._plus_btn.setObjectName("sidebarToolButton")
        self._plus_btn.setToolTip("Create new collection or request")
        top_row.addWidget(self._plus_btn)

        # Plus-menu
        self._plus_menu = QMenu(self)
        new_coll_act = QAction("New collection", self)
        self._plus_menu.addAction(new_coll_act)
        self._new_req_act = QAction("New request", self)
        self._new_req_act.setEnabled(False)
        self._plus_menu.addAction(self._new_req_act)

        self._plus_btn.clicked.connect(
            lambda: self._plus_menu.exec(
                self._plus_btn.mapToGlobal(self._plus_btn.rect().bottomLeft())
            )
        )
        new_coll_act.triggered.connect(lambda: self.new_collection_requested.emit(None))

        self._selected_collection_id: int | None = None
        self._new_req_act.triggered.connect(self._on_new_request_clicked)

        # "Import" button
        self._import_btn = QToolButton(self)
        self._import_btn.setText("Import")
        self._import_btn.setObjectName("sidebarToolButton")
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

        magnify_icon = QIcon.fromTheme("search")
        if magnify_icon.isNull():
            magnify_icon = QIcon(":/icons/magnifier.svg")
        self._search.addAction(magnify_icon, QLineEdit.ActionPosition.LeadingPosition)

        main_layout.addWidget(self._search)

        # Emit search signal on each keystroke
        self._search.textChanged.connect(lambda txt: self.search_changed.emit(txt))

    def set_selected_collection_id(self, collection_id: int | None) -> None:
        """Update the currently selected collection for the 'New request' action."""
        self._selected_collection_id = collection_id
        self._new_req_act.setEnabled(collection_id is not None)

    def _on_new_request_clicked(self) -> None:
        """Emit ``new_request_requested`` with the currently selected collection."""
        if self._selected_collection_id is not None:
            self.new_request_requested.emit(self._selected_collection_id)
