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
from ui.collections.new_local_script_popup import NewLocalScriptItemPopup
from ui.styling.icons import phi
from ui.widgets.sidebar_section_info import (
    COLLECTIONS_INTRO,
    LOCAL_SCRIPTS_INTRO,
    SidebarSectionInfoPopup,
    make_sidebar_info_button,
    toggle_sidebar_section_info,
)


# ----------------------------------------------------------------------
# Header management subclass
# ----------------------------------------------------------------------
class CollectionHeader(QWidget):
    """Manages the header with section label, New/Import buttons, and search."""

    # Accept any object (int or None)
    new_collection_requested = Signal(object)  # parent_id or None
    new_request_requested = Signal(object)  # same for requests
    new_script_requested = Signal(object, str, str)  # parent_id, language, module_format
    search_changed = Signal(str)
    import_requested = Signal()

    def __init__(self, parent: QWidget | None = None, *, tree_kind: str = "collections") -> None:
        """Initialise header bar with search field and action buttons."""
        super().__init__(parent)
        self._tree_kind = tree_kind
        is_scripts = tree_kind == "local_scripts"
        self._info_btn: QToolButton | None = None
        self._info_popup: SidebarSectionInfoPopup | None = None
        self._info_title = "Local scripts" if is_scripts else "Collections"
        self._info_body = LOCAL_SCRIPTS_INTRO if is_scripts else COLLECTIONS_INTRO
        self._info_tooltip = "What are local scripts?" if is_scripts else "What are collections?"
        if not is_scripts:
            self.setFixedHeight(70)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 6, 0, 6)
        main_layout.setSpacing(6)

        # -- Row 1: section label + action buttons --------------------
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(4)

        section_label = QLabel("Local scripts" if is_scripts else "Collections")
        section_label.setObjectName("sidebarSectionLabel")
        section_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(section_label)

        self._info_btn = make_sidebar_info_button(
            self,
            tooltip=self._info_tooltip,
            on_toggle=self._toggle_section_info,
        )
        top_row.addWidget(self._info_btn)

        top_row.addStretch()

        # "New" button with icon-grid popup
        self._plus_btn = QToolButton(self)
        self._plus_btn.setText("New")
        self._plus_btn.setIcon(phi("plus"))
        self._plus_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._plus_btn.setObjectName("sidebarToolButton")
        self._plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plus_btn.setToolTip(
            "Create a new script or folder" if is_scripts else "Create new collection or request"
        )
        top_row.addWidget(self._plus_btn)

        # Dialog (replaces the old QMenu)
        self._popup: NewItemPopup | NewLocalScriptItemPopup
        if is_scripts:
            self._popup = NewLocalScriptItemPopup(self)
            self._popup.new_script_clicked.connect(self._on_popup_new_script_language)
            self._popup.new_folder_clicked.connect(lambda: self.new_collection_requested.emit(None))
        else:
            self._popup = NewItemPopup(self)
            self._popup.new_request_clicked.connect(self._on_popup_new_request)
            self._popup.new_collection_clicked.connect(
                lambda: self.new_collection_requested.emit(None)
            )
        self._plus_btn.clicked.connect(lambda: self._popup.exec())

        self._selected_collection_id: int | None = None

        if not is_scripts:
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
        self._search.setPlaceholderText("Search scripts" if is_scripts else "Search collections")
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

    def _on_popup_new_script_language(self, language: str, module_format: str) -> None:
        """Emit ``new_script_requested`` with folder context, language, and format."""
        self.new_script_requested.emit(self._selected_collection_id, language, module_format)

    def _toggle_section_info(self) -> None:
        """Show or hide the section help popup below the info button."""
        if self._info_btn is None:
            return
        holder = [self._info_popup]
        toggle_sidebar_section_info(
            self._info_btn,
            holder,
            title=self._info_title,
            body=self._info_body,
            parent=self,
        )
        self._info_popup = holder[0]
