from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QProgressBar, QVBoxLayout, QWidget

from services.collection_service import CollectionService
from ui.collections.collection_header import CollectionHeader
from ui.collections.collection_tree import CollectionTree

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Background fetcher
# ----------------------------------------------------------------------
class _CollectionFetcher(QObject):
    finished = Signal(dict)

    @Slot()
    def run(self) -> None:
        """Fetch all collections in a blocking call and emit the result."""
        roots = CollectionService.fetch_all()
        self.finished.emit(self._collections_to_dict(roots))

    @staticmethod
    def _collections_to_dict(collections: Iterable[Any]) -> dict[str, Any]:
        """Recursively transform a list of Collection objects into the nested
        dict expected by ``CollectionWidget``."""
        result: dict[str, Any] = {}
        for collection in collections:
            children_dict = _CollectionFetcher._collections_to_dict(
                collection.children or []
            )
            for request in collection.requests or []:
                children_dict[str(request.id)] = {
                    "type": "request",
                    "id": request.id,
                    "name": request.name,
                    "method": request.method,
                }
            result[str(collection.id)] = {
                "id": collection.id,
                "name": collection.name,
                "type": "folder",
                "children": children_dict,
            }
        return result


# ----------------------------------------------------------------------
# Main widget
# ----------------------------------------------------------------------
class CollectionWidget(QWidget):
    """
    A reusable widget that shows a collection hierarchy.

    Use :meth:`set_collections` to feed it data, and it will rebuild itself.
    """

    _pending_select_id: int | None = None
    _pending_select_request_id: int | None = None

    # Forwarded signals from the tree
    item_action_triggered = Signal(str, int, str)
    item_name_changed     = Signal(str, int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._svc = CollectionService()

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        self._header = CollectionHeader(self)
        self._header.new_collection_requested.connect(self._create_new_collection)
        self._header.new_request_requested.connect(self._create_new_request)
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

        main_layout.addWidget(self._tree_widget, 1)

        # Loading bar
        self._loading_bar = QProgressBar(self)
        self._loading_bar.setRange(0, 0)
        self._loading_bar.setTextVisible(False)
        self._loading_bar.setFixedHeight(4)
        self._loading_bar.setStyleSheet(
            """
            QProgressBar { background-color: transparent; border: 0; }
            QProgressBar::chunk { background-color: #3498db; }
            """
        )
        self._loading_bar.setGeometry(0, 0, self.width(), self._loading_bar.height())
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
            self._tree_widget.select_item_by_id(
                self._pending_select_request_id, "request"
            )
            self._pending_select_request_id = None

    # ------------------------------------------------------------------
    # Service-layer slots (connected to tree signals)
    # ------------------------------------------------------------------
    @Slot(int, str)
    def _on_collection_rename(self, collection_id: int, new_name: str) -> None:
        try:
            self._svc.rename_collection(collection_id, new_name)
        except Exception as exc:
            logger.error("Failed to rename collection %s: %s", collection_id, exc)

    @Slot(int)
    def _on_collection_delete(self, collection_id: int) -> None:
        try:
            self._svc.delete_collection(collection_id)
        except Exception as exc:
            logger.error("Failed to delete collection %s: %s", collection_id, exc)

    @Slot(int, str)
    def _on_request_rename(self, request_id: int, new_name: str) -> None:
        try:
            self._svc.rename_request(request_id, new_name)
        except Exception as exc:
            logger.error("Failed to rename request %s: %s", request_id, exc)

    @Slot(int)
    def _on_request_delete(self, request_id: int) -> None:
        try:
            self._svc.delete_request(request_id)
        except Exception as exc:
            logger.error("Failed to delete request %s: %s", request_id, exc)

    @Slot(int, int)
    def _on_request_moved(self, request_id: int, new_collection_id: int) -> None:
        try:
            self._svc.move_request(request_id, new_collection_id)
        except Exception as exc:
            logger.error("Failed to move request %s: %s", request_id, exc)

    @Slot(int, object)
    def _on_collection_moved(self, collection_id: int, new_parent_id: int | None) -> None:
        try:
            self._svc.move_collection(collection_id, new_parent_id)
        except Exception as exc:
            logger.error("Failed to move collection %s: %s", collection_id, exc)

    # ------------------------------------------------------------------
    # Create helpers
    # ------------------------------------------------------------------
    def _create_new_request(self, collection_id: int | None = None) -> None:
        """Create a new request and add it to the tree."""
        if collection_id is None:
            logger.warning("Cannot create request without a collection_id")
            return
        new_request = self._svc.create_request(
            collection_id, "GET", "https://api.example.com", "New Request"
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
        self._tree_widget.select_item_by_id(new_request.id, "request")

    def _create_new_collection(self, parent_id: int | None = None) -> None:
        """Create a new collection and add it to the tree."""
        new_collection = self._svc.create_collection("New Collection", parent_id)
        self._tree_widget.add_collection(
            {"name": new_collection.name, "id": new_collection.id}, parent_id
        )
        self._tree_widget.select_item_by_id(new_collection.id, "folder")

    # ------------------------------------------------------------------
    # Qt overrides & public API
    # ------------------------------------------------------------------
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._loading_bar.setGeometry(0, 0, self.width(), self._loading_bar.height())

    def set_collections(self, data: dict[str, Any]) -> None:
        self._tree_widget.set_collections(data)
