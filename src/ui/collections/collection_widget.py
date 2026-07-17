from __future__ import annotations

import logging
from functools import partial
from typing import Any, TypedDict

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QMessageBox, QProgressBar, QVBoxLayout, QWidget

from services.collection_service import CollectionService
from services.local_script_service import LocalScriptService
from ui.collections.collection_header import CollectionHeader
from ui.collections.tree import CollectionTree
from ui.collections.tree.constants import ITEM_TYPE_FOLDER, ITEM_TYPE_SCRIPT
from ui.styling.theme import LEFT_NAV_PANEL_MARGIN_H_LEFT_PX, LEFT_NAV_PANEL_MARGIN_H_RIGHT_PX

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
_DEFAULT_SCRIPT_NAME = "script"
_DEFAULT_SCRIPT_FOLDER_NAME = "new_folder"


# ----------------------------------------------------------------------
# Background fetcher
# ----------------------------------------------------------------------
class _CollectionFetcher(QObject):
    """Worker that fetches collections on a background thread.

    Emits ``finished(dict, int)`` with the nested dict consumed by
    :meth:`CollectionTree.set_collections` and the fetch generation.
    """

    finished = Signal(dict, int)

    def __init__(self, *, tree_kind: str = "collections", generation: int = 0) -> None:
        super().__init__()
        self._tree_kind = tree_kind
        self._generation = generation

    @Slot()
    def run(self) -> None:
        """Initialise the DB (idempotent) then fetch tree data."""
        from database.database import init_db
        from shiboken6 import isValid

        init_db()
        # The host widget may have been destroyed while this worker ran
        # (tests / rapid restart). Emitting on a deleted QObject aborts Qt.
        if not isValid(self):
            return
        if self._tree_kind == "local_scripts":
            payload = LocalScriptService.fetch_all()
        else:
            payload = CollectionService.fetch_all()
        if isValid(self):
            self.finished.emit(payload, self._generation)


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
    script_rename_requested = Signal(
        int, str, str, str
    )  # script_id, basename, language, module_format
    run_collection_requested = Signal(int)  # collection_id

    # Emitted when the initial background fetch completes
    load_finished = Signal()
    # Emitted when a subsequent :meth:`refresh_collections` finishes
    refresh_finished = Signal()

    # Emitted when the user wants a draft (unsaved) request tab
    draft_request_requested = Signal()

    def __init__(self, parent: QWidget | None = None, *, variant: str = "collections") -> None:
        """Initialise the collection widget with header, tree, and loading bar."""
        super().__init__(parent)

        self._variant = variant
        self._tree_kind = "local_scripts" if variant == "local_scripts" else "collections"
        self._pending_select_id: int | None = None
        self._pending_select_request_id: int | None = None
        self._fetch_started = False
        self._fetch_generation = 0
        self._fetch_emits_load_finished = False
        self._thread: QThread | None = None
        self._worker: _CollectionFetcher | None = None

        self._svc: type[CollectionService] | type[LocalScriptService] = (
            LocalScriptService if self._tree_kind == "local_scripts" else CollectionService
        )

        # Main layout (horizontal inset matches left flyout nav; keeps the
        # collections|environments splitter handle full-width in the parent).
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            LEFT_NAV_PANEL_MARGIN_H_LEFT_PX,
            0,
            LEFT_NAV_PANEL_MARGIN_H_RIGHT_PX,
            6,
        )
        main_layout.setSpacing(0)

        # Header
        self._header = CollectionHeader(self, tree_kind=self._tree_kind)
        self._header.new_collection_requested.connect(self._create_new_collection)
        if self._tree_kind == "local_scripts":
            self._header.new_script_requested.connect(self._create_new_script)
        else:
            self._header.new_request_requested.connect(self._create_new_request)
        self._header.search_changed.connect(self._on_search_changed)
        if self._tree_kind == "collections":
            self._header.import_requested.connect(self._on_import_requested)
        main_layout.addWidget(self._header)

        # Tree
        self._tree_widget = CollectionTree(self, tree_kind=self._tree_kind)
        self._tree_widget.item_action_triggered.connect(self.item_action_triggered)
        self._tree_widget.item_name_changed.connect(self.item_name_changed)
        self._tree_widget.run_collection_requested.connect(self.run_collection_requested)

        # Connect tree signals → service layer
        self._tree_widget.collection_rename_requested.connect(self._on_collection_rename)
        self._tree_widget.collection_delete_requested.connect(self._on_collection_delete)
        self._tree_widget.request_rename_requested.connect(self._on_request_rename)
        if self._tree_kind == "local_scripts":
            self._tree_widget.script_rename_requested.connect(self._on_script_rename)
            self._tree_widget.script_rename_requested.connect(self.script_rename_requested.emit)
        self._tree_widget.request_delete_requested.connect(self._on_request_delete)
        if self._tree_kind == "collections":
            self._tree_widget.request_duplicate_requested.connect(self._on_request_duplicate)
        self._tree_widget.request_moved.connect(self._on_request_moved)
        self._tree_widget.collection_moved.connect(self._on_collection_moved)
        self._tree_widget.new_collection_requested.connect(self._create_new_collection)
        if self._tree_kind == "local_scripts":
            self._tree_widget.new_request_requested.connect(
                lambda parent_id: self._create_new_script(parent_id, "javascript")
            )
        else:
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
        self._loading_bar.setGeometry(0, 0, viewport.width(), 4)
        self._loading_bar.hide()

    # ------------------------------------------------------------------
    # Background fetch
    # ------------------------------------------------------------------
    def _start_fetch(self) -> None:
        """Launch the one-shot async startup fetch (no-op after the first call)."""
        if self._fetch_started:
            return
        self._fetch_started = True
        self._fetch_emits_load_finished = True
        self._fetch_generation += 1
        generation = self._fetch_generation
        self._loading_bar.show()
        self._tree_widget.show_loading()
        thread = QThread(self)
        worker = _CollectionFetcher(tree_kind=self._tree_kind, generation=generation)
        worker.moveToThread(thread)
        self._thread = thread
        self._worker = worker
        thread.started.connect(worker.run)
        # Must be QueuedConnection onto a QObject slot: a plain lambda would run
        # on the worker thread and touch QTimer / QProgressBar (timer thread errors).
        worker.finished.connect(
            self._on_fetch_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        def _clear_if_current(finished_thread: QThread = thread) -> None:
            if self._thread is finished_thread:
                self._clear_fetch_refs()

        thread.finished.connect(_clear_if_current)
        thread.start()

    @Slot(dict, int)
    def _on_fetch_finished(self, payload: dict[str, Any], generation: int) -> None:
        """GUI-thread handler for background collection fetch results."""
        self._on_collections_ready(payload, generation)

    def refresh_collections(
        self,
        *,
        select_request_id: int | None = None,
        select_collection_id: int | None = None,
    ) -> None:
        """Re-fetch the tree from the database on the GUI thread.

        Safe after the initial load (unlike :meth:`_start_fetch`). Optional
        *select_request_id* / *select_collection_id* are applied after the new
        data is installed. Emits :attr:`refresh_finished` (not
        :attr:`load_finished`) so startup session restore is not re-triggered.
        """
        if select_collection_id is not None:
            self._pending_select_id = select_collection_id
        if select_request_id is not None:
            self._pending_select_request_id = select_request_id
        self._fetch_started = True
        self._fetch_generation += 1
        generation = self._fetch_generation
        self._fetch_emits_load_finished = False
        self._loading_bar.show()
        self._tree_widget.show_loading()
        if self._tree_kind == "local_scripts":
            payload = LocalScriptService.fetch_all()
        else:
            payload = CollectionService.fetch_all()
        self._on_collections_ready(payload, generation)

    def _clear_fetch_refs(self) -> None:
        """Drop fetch worker/thread references after completion."""
        self._thread = None
        self._worker = None

    def shutdown_fetch(self) -> None:
        """Stop an in-flight initial fetch worker before widget teardown."""
        if self._thread is None:
            return
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)
        self._clear_fetch_refs()

    def _on_collections_ready(self, collection_dict: dict[str, Any], generation: int) -> None:
        """Apply fetch results when *generation* is still current."""
        if generation != self._fetch_generation:
            return
        self._loading_bar.hide()
        self._tree_widget.hide_loading()
        self._tree_widget.set_collections(collection_dict)

        if self._fetch_emits_load_finished:
            self.load_finished.emit()
        else:
            self.refresh_finished.emit()

        if self._pending_select_id is not None:
            self._tree_widget.select_item_by_id(self._pending_select_id, "folder")
            self._pending_select_id = None
            return

        if self._pending_select_request_id is not None:
            leaf = ITEM_TYPE_SCRIPT if self._tree_kind == "local_scripts" else "request"
            self._tree_widget.select_item_by_id(self._pending_select_request_id, leaf)
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
        if self._tree_kind == "local_scripts":
            self._safe_svc_call(
                "rename folder", LocalScriptService.rename_folder, collection_id, new_name
            )
            return
        self._safe_svc_call(
            "rename collection", CollectionService.rename_collection, collection_id, new_name
        )

    @Slot(int)
    def _on_collection_delete(self, collection_id: int) -> None:
        if self._tree_kind == "local_scripts":
            self._safe_svc_call("delete folder", LocalScriptService.delete_folder, collection_id)
            return
        self._safe_svc_call("delete collection", CollectionService.delete_collection, collection_id)

    @Slot(int, str)
    def _on_request_rename(self, request_id: int, new_name: str) -> None:
        self._safe_svc_call(
            "rename request", CollectionService.rename_request, request_id, new_name
        )

    @Slot(int, str, str, str)
    def _on_script_rename(
        self, script_id: int, new_name: str, language: str, module_format: str
    ) -> None:
        """Persist script basename, language, and module format from the tree editor."""
        self._safe_svc_call(
            "rename script",
            partial(
                LocalScriptService.rename_script,
                script_id,
                new_name,
                language=language,
                module_format=module_format,
            ),
        )
        self.item_name_changed.emit("script", script_id, new_name)

    @Slot(int)
    def _on_request_delete(self, request_id: int) -> None:
        if self._tree_kind == "local_scripts":
            self._safe_svc_call("delete script", LocalScriptService.delete_script, request_id)
            return
        self._safe_svc_call("delete request", CollectionService.delete_request, request_id)

    @Slot(int)
    def _on_request_duplicate(self, request_id: int) -> None:
        """Clone *request_id*, add it to the tree, and open it in a tab."""
        try:
            new_request = CollectionService.duplicate_request(request_id)
        except Exception as exc:
            logger.error("Failed to duplicate request: %s", exc)
            QMessageBox.warning(
                self,
                "Operation Failed",
                f"Failed to duplicate request:\n{exc}",
            )
            return
        self._tree_widget.add_request(
            {
                "name": new_request.name,
                "url": new_request.url,
                "id": new_request.id,
                "method": new_request.method,
            },
            new_request.collection_id,
        )
        self._tree_widget.select_item_by_id(new_request.id, "request")
        self.item_action_triggered.emit("request", new_request.id, "Open")

    @Slot(int, int)
    def _on_request_moved(self, request_id: int, new_collection_id: int) -> None:
        if self._tree_kind == "local_scripts":
            if new_collection_id is None:
                return
            self._safe_svc_call(
                "move script",
                LocalScriptService.move_script,
                request_id,
                new_collection_id,
            )
            return
        self._safe_svc_call(
            "move request", CollectionService.move_request, request_id, new_collection_id
        )

    @Slot(int, object)
    def _on_collection_moved(self, collection_id: int, new_parent_id: int | None) -> None:
        if self._tree_kind == "local_scripts":
            self._safe_svc_call(
                "move folder",
                LocalScriptService.move_folder,
                collection_id,
                new_parent_id,
            )
            return
        self._safe_svc_call(
            "move collection", CollectionService.move_collection, collection_id, new_parent_id
        )

    # ------------------------------------------------------------------
    # Create helpers
    # ------------------------------------------------------------------
    def _create_new_script(
        self,
        collection_id: int | None = None,
        language: str = "javascript",
        module_format: str = "esm",
    ) -> None:
        """Create a new local script with *language* / *module_format* and add to the tree."""
        if collection_id is None:
            folder = LocalScriptService.create_folder(_DEFAULT_SCRIPT_FOLDER_NAME, None)
            collection_id = folder.id
            self._tree_widget.add_collection(
                {"name": folder.name, "id": folder.id},
                None,
            )
        new_script = LocalScriptService.create_script(
            collection_id,
            _DEFAULT_SCRIPT_NAME,
            language=language,
            module_format=module_format,
        )
        self._tree_widget.add_script(
            {
                "name": new_script.name,
                "id": new_script.id,
                "language": language,
                "module_format": module_format,
            },
            collection_id,
        )
        self._tree_widget.start_rename_by_id(new_script.id, ITEM_TYPE_SCRIPT)

    def _create_new_request(self, collection_id: int | None = None) -> None:
        """Create a new HTTP request and add it to the tree."""
        if collection_id is None:
            self.draft_request_requested.emit()
            return
        new_request = CollectionService.create_request(
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
        """Create a new folder and add it to the tree."""
        if self._tree_kind == "local_scripts":
            folder = LocalScriptService.create_folder(_DEFAULT_SCRIPT_FOLDER_NAME, parent_id)
            self._tree_widget.add_collection({"name": folder.name, "id": folder.id}, parent_id)
            self._tree_widget.start_rename_by_id(folder.id, ITEM_TYPE_FOLDER)
            return
        new_collection = CollectionService.create_collection(_DEFAULT_COLLECTION_NAME, parent_id)
        self._tree_widget.add_collection(
            {"name": new_collection.name, "id": new_collection.id}, parent_id
        )
        self._tree_widget.start_rename_by_id(new_collection.id, ITEM_TYPE_FOLDER)

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

    def update_item_name(self, item_id: int, item_type: str, new_name: str) -> None:
        """Update the display text of a tree item without triggering signals."""
        self._tree_widget.update_item_name(item_id, item_type, new_name)

    def update_request_method(self, request_id: int, method: str) -> None:
        """Update the HTTP method badge of a request item without rebuilding."""
        self._tree_widget.update_request_method(request_id, method)

    def update_script_language(self, script_id: int, language: str) -> None:
        """Refresh language icon and extension for a script tree row."""
        self._tree_widget.update_script_language(script_id, language)

    def update_script_metadata(
        self,
        script_id: int,
        *,
        language: str | None = None,
        module_format: str | None = None,
    ) -> None:
        """Refresh language/format roles and extension display for a script row."""
        self._tree_widget.update_script_metadata(
            script_id,
            language=language,
            module_format=module_format,
        )

    def select_and_scroll_to(self, item_id: int, item_type: str) -> None:
        """Select and scroll to the item with the given ID and type."""
        self._tree_widget.select_item_by_id(item_id, item_type)

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
        dialog.import_completed.connect(self.refresh_collections)
        dialog.exec()
