from __future__ import annotations

import logging
from typing import Any, TypedDict

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QMessageBox, QProgressBar, QVBoxLayout, QWidget

from services.collection_service import CollectionService
from ui.collections.collection_header import CollectionHeader
from ui.collections.tree import CollectionTree
from ui.theme import COLOR_ACCENT

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Interchange format between fetcher, widget, and tree
# ----------------------------------------------------------------------
class CollectionDict(TypedDict, total=False):
    """Schema for the nested dict that flows between the fetcher and the tree.

    Folders have ``type="folder"`` with a ``children`` dict keyed by
    stringified ID.  Requests have ``type="request"`` with ``method``.
    """

    id: int
    name: str
    type: str  # "folder" | "request"
    children: dict[str, CollectionDict]
    method: str  # present only when type == "request"


# ----------------------------------------------------------------------
# Default values for new items
# ----------------------------------------------------------------------
_DEFAULT_METHOD = "GET"
_DEFAULT_URL = "https://api.example.com"
_DEFAULT_REQUEST_NAME = "New Request"
_DEFAULT_COLLECTION_NAME = "New Collection"


# ----------------------------------------------------------------------
# Background fetcher
# ----------------------------------------------------------------------
class _CollectionFetcher(QObject):
    """Worker that fetches collections on a background thread.

    Emits ``finished(dict)`` with the nested dict consumed by
    :meth:`CollectionTree.set_collections`.
    """

    finished = Signal(dict)

    @Slot()
    def run(self) -> None:
        """Fetch all collections in a blocking call and emit the result."""
        self.finished.emit(CollectionService.fetch_all())


# ----------------------------------------------------------------------
# Main widget
# ----------------------------------------------------------------------
class CollectionWidget(QWidget):
    """A reusable widget that shows a collection hierarchy.

    Use :meth:`set_collections` to feed it data, and it will rebuild itself.
    """

    # Forwarded signals from the tree
    item_action_triggered = Signal(str, int, str)
    item_name_changed = Signal(str, int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the collection widget with header, tree, and loading bar."""
        super().__init__(parent)

        self._pending_select_id: int | None = None
        self._pending_select_request_id: int | None = None

        self._svc = CollectionService()

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        self._header = CollectionHeader(self)
        self._header.new_collection_requested.connect(self._create_new_collection)
        self._header.new_request_requested.connect(self._create_new_request)
        self._header.search_changed.connect(self._on_search_changed)
        self._header.import_requested.connect(self._on_import_requested)
        main_layout.addWidget(self._header)

        # Tree
        self._tree_widget = CollectionTree(self)
        self._tree_widget.item_action_triggered.connect(self.item_action_triggered)
        self._tree_widget.item_name_changed.connect(self.item_name_changed)

        # Connect tree signals → service layer
        self._tree_widget.collection_rename_requested.connect(self._on_collection_rename)
        self._tree_widget.collection_delete_requested.connect(self._on_collection_delete)
        self._tree_widget.request_rename_requested.connect(self._on_request_rename)
        self._tree_widget.request_delete_requested.connect(self._on_request_delete)
        self._tree_widget.request_moved.connect(self._on_request_moved)
        self._tree_widget.collection_moved.connect(self._on_collection_moved)
        self._tree_widget.new_collection_requested.connect(self._create_new_collection)
        self._tree_widget.new_request_requested.connect(self._create_new_request)
        self._tree_widget.selected_collection_changed.connect(
            self._header.set_selected_collection_id
        )

        main_layout.addWidget(self._tree_widget, 1)

        # Loading bar — overlaid at the top of the tree viewport
        viewport = self._tree_widget._tree.viewport()
        self._loading_bar = QProgressBar(viewport)
        self._loading_bar.setRange(0, 0)
        self._loading_bar.setTextVisible(False)
        self._loading_bar.setFixedHeight(4)
        self._loading_bar.setStyleSheet(
            f"""
            QProgressBar {{ background-color: transparent; border: 0; }}
            QProgressBar::chunk {{ background-color: {COLOR_ACCENT}; }}
            """
        )
        self._loading_bar.setGeometry(0, 0, viewport.width(), 4)
        self._loading_bar.hide()

        self._start_fetch()

    # ------------------------------------------------------------------
    # Background fetch
    # ------------------------------------------------------------------
    def _start_fetch(self) -> None:
        """Launch the worker thread and show the loading bar."""
        self._loading_bar.show()
        self._thread = QThread(self)
        self._worker = _CollectionFetcher()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_collections_ready)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    @Slot(dict)
    def _on_collections_ready(self, collection_dict: dict[str, Any]) -> None:
        """Called once the background fetch finishes."""
        self._loading_bar.hide()
        self._tree_widget.set_collections(collection_dict)

        if self._pending_select_id is not None:
            self._tree_widget.select_item_by_id(self._pending_select_id, "folder")
            self._pending_select_id = None
            return

        if self._pending_select_request_id is not None:
            self._tree_widget.select_item_by_id(self._pending_select_request_id, "request")
            self._pending_select_request_id = None

    # ------------------------------------------------------------------
    # Service-layer slots (connected to tree signals)
    # ------------------------------------------------------------------
    def _safe_svc_call(self, description: str, func: Any, *args: Any) -> bool:
        """Call *func* with *args*, showing a warning dialog on failure.

        Returns ``True`` on success, ``False`` on failure.
        """
        try:
            func(*args)
            return True
        except Exception as exc:
            logger.error("Failed to %s: %s", description, exc)
            QMessageBox.warning(
                self,
                "Operation Failed",
                f"Failed to {description}:\n{exc}",
            )
            return False

    @Slot(int, str)
    def _on_collection_rename(self, collection_id: int, new_name: str) -> None:
        self._safe_svc_call(
            "rename collection", self._svc.rename_collection, collection_id, new_name
        )

    @Slot(int)
    def _on_collection_delete(self, collection_id: int) -> None:
        self._safe_svc_call("delete collection", self._svc.delete_collection, collection_id)

    @Slot(int, str)
    def _on_request_rename(self, request_id: int, new_name: str) -> None:
        self._safe_svc_call("rename request", self._svc.rename_request, request_id, new_name)

    @Slot(int)
    def _on_request_delete(self, request_id: int) -> None:
        self._safe_svc_call("delete request", self._svc.delete_request, request_id)

    @Slot(int, int)
    def _on_request_moved(self, request_id: int, new_collection_id: int) -> None:
        self._safe_svc_call("move request", self._svc.move_request, request_id, new_collection_id)

    @Slot(int, object)
    def _on_collection_moved(self, collection_id: int, new_parent_id: int | None) -> None:
        self._safe_svc_call(
            "move collection", self._svc.move_collection, collection_id, new_parent_id
        )

    # ------------------------------------------------------------------
    # Create helpers
    # ------------------------------------------------------------------
    def _create_new_request(self, collection_id: int | None = None) -> None:
        """Create a new request and add it to the tree."""
        if collection_id is None:
            logger.warning("Cannot create request without a collection_id")
            return
        new_request = self._svc.create_request(
            collection_id, _DEFAULT_METHOD, _DEFAULT_URL, _DEFAULT_REQUEST_NAME
        )
        self._tree_widget.add_request(
            {
                "name": new_request.name,
                "url": new_request.url,
                "id": new_request.id,
                "method": new_request.method,
            },
            collection_id,
        )
        self._tree_widget.start_rename_by_id(new_request.id, "request")

    def _create_new_collection(self, parent_id: int | None = None) -> None:
        """Create a new collection and add it to the tree."""
        new_collection = self._svc.create_collection(_DEFAULT_COLLECTION_NAME, parent_id)
        self._tree_widget.add_collection(
            {"name": new_collection.name, "id": new_collection.id}, parent_id
        )
        self._tree_widget.start_rename_by_id(new_collection.id, "folder")

    # ------------------------------------------------------------------
    # Qt overrides & public API
    # ------------------------------------------------------------------
    def resizeEvent(self, event) -> None:
        """Reposition the loading bar on widget resize."""
        super().resizeEvent(event)
        viewport = self._tree_widget._tree.viewport()
        self._loading_bar.setGeometry(0, 0, viewport.width(), 4)

    def set_collections(self, data: dict[str, Any]) -> None:
        """Replace the displayed collection data with *data*."""
        self._tree_widget.set_collections(data)

    def selected_collection_id(self) -> int | None:
        """Return the ID of the currently selected collection, or ``None``."""
        return self._header._selected_collection_id

    @Slot(str)
    def _on_search_changed(self, text: str) -> None:
        """Filter tree items based on the search text."""
        self._tree_widget.filter_items(text)

    def _on_import_requested(self) -> None:
        """Open the import dialog and refresh the tree on success."""
        from ui.dialogs.import_dialog import ImportDialog

        dialog = ImportDialog(self)
        dialog.import_completed.connect(self._start_fetch)
        dialog.exec()
