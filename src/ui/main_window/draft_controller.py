"""Draft request tab lifecycle mixin for the main window.

Provides ``_DraftControllerMixin`` with methods to open an unsaved
("draft") request tab and to save it via the save-to-collection dialog.
Mixed into ``MainWindow``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from services.collection_service import CollectionService, RequestLoadDict
from ui.request.navigation.tab_manager import TabContext
from ui.request.request_editor import RequestEditorWidget
from ui.request.response_viewer import ResponseViewerWidget

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPushButton, QStackedWidget, QWidget

    from ui.collections.collection_widget import CollectionWidget
    from ui.request.navigation.breadcrumb_bar import BreadcrumbBar
    from ui.request.navigation.request_tab_bar import RequestTabBar

logger = logging.getLogger(__name__)

# Default label for unsaved request tabs
_DRAFT_TAB_NAME = "Untitled Request"


class _DraftControllerMixin:
    """Mixin that manages draft (unsaved) request tab lifecycle.

    Expects the host class to provide ``_tabs``, ``_tab_bar``,
    ``_editor_stack``, ``_response_stack``, ``_breadcrumb_bar``,
    ``_save_btn``, ``collection_widget``, and the signal helper
    methods from ``_TabControllerMixin``.
    """

    if TYPE_CHECKING:
        _tabs: dict[int, TabContext]
        _tab_bar: RequestTabBar
        _editor_stack: QStackedWidget
        _response_stack: QStackedWidget
        _breadcrumb_bar: BreadcrumbBar
        _save_btn: QPushButton
        request_widget: RequestEditorWidget
        response_widget: ResponseViewerWidget
        collection_widget: CollectionWidget

        def _on_send_request(self) -> None: ...
        def _on_save_request(self) -> None: ...
        def _on_save_response(self, data: dict) -> None: ...
        def _sync_save_btn(self, dirty: bool) -> None: ...
        def _on_editor_dirty_changed(self, dirty: bool) -> None: ...
        def _on_tab_changed(self, index: int) -> None: ...
        def _enforce_tab_limit_before_open(self) -> bool: ...
        def _next_tab_open_order(self) -> int: ...
        def _next_tab_insert_index(self) -> int: ...
        def _shift_tabs_for_insert(self, index: int) -> None: ...
        def _request_full_path(self, request_id: int) -> str | None: ...

    # ------------------------------------------------------------------
    # Open a new draft request tab
    # ------------------------------------------------------------------
    def _open_draft_request(self) -> None:
        """Open a new draft request tab that is not yet persisted to the DB.

        The tab has ``request_id=None`` and is marked dirty immediately so
        the Save button is enabled.  Saving triggers the save-to-collection
        dialog.
        """
        if not self._enforce_tab_limit_before_open():
            return

        data: RequestLoadDict = {
            "name": _DRAFT_TAB_NAME,
            "method": "GET",
            "url": "",
        }

        editor = RequestEditorWidget()
        viewer = ResponseViewerWidget()

        self._editor_stack.addWidget(editor)
        self._response_stack.addWidget(viewer)

        ctx = TabContext(
            request_id=None,
            editor=editor,
            response_viewer=viewer,
            opened_order=self._next_tab_open_order(),
        )

        insert_index = self._next_tab_insert_index()
        self._shift_tabs_for_insert(insert_index)

        self._tab_bar.blockSignals(True)
        try:
            idx = self._tab_bar.add_request_tab(
                "GET",
                _DRAFT_TAB_NAME,
                path=_DRAFT_TAB_NAME,
                index=insert_index,
            )
        finally:
            self._tab_bar.blockSignals(False)

        ctx.draft_name = _DRAFT_TAB_NAME
        self._tabs[idx] = ctx

        editor.load_request(data, request_id=None)
        editor.send_requested.connect(self._on_send_request)
        editor.save_requested.connect(self._on_save_request)
        editor.dirty_changed.connect(self._sync_save_btn)
        editor.dirty_changed.connect(self._on_editor_dirty_changed)
        viewer.save_response_requested.connect(self._on_save_response)

        # Mark as dirty so Save button is enabled for the new draft
        editor._set_dirty(True)

        self._tab_bar.setCurrentIndex(idx)
        self._on_tab_changed(idx)
        self._persist_open_tabs()  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Save draft request → save-to-collection dialog
    # ------------------------------------------------------------------
    def _save_draft_request(self, ctx: TabContext | None, editor: RequestEditorWidget) -> None:
        """Open the save-to-collection dialog for a draft (unsaved) request.

        On accept, creates the request in the DB and upgrades the tab
        from draft to a normal persisted request.
        """
        from ui.dialogs.save_request_dialog import SaveRequestDialog

        # Prefer the user-chosen draft name (set via breadcrumb rename),
        # then the URL text, then the default placeholder.
        idx = self._tab_bar.currentIndex()
        draft_ctx = self._tabs.get(idx)
        draft_label = draft_ctx.draft_name if draft_ctx is not None else None
        url_text = editor._url_input.text().strip()
        default_name = url_text or draft_label or _DRAFT_TAB_NAME
        dialog = SaveRequestDialog(default_name=default_name, parent=cast("QWidget", self))
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        request_name = dialog.request_name()
        collection_id = dialog.selected_collection_id()
        if collection_id is None:
            return

        data = editor.get_request_data()
        method = data.get("method", "GET")
        url = data.get("url", "")
        try:
            new_request = CollectionService.create_request(
                collection_id,
                method,
                url,
                request_name,
                body=data.get("body"),
                request_parameters=data.get("request_parameters"),
                headers=data.get("headers"),
                scripts=data.get("scripts"),
            )
        except Exception:
            logger.exception("Failed to create request in collection %s", collection_id)
            return

        # Upgrade draft tab to a persisted request
        editor._request_id = new_request.id
        editor._set_dirty(False)

        if ctx is not None:
            ctx.request_id = new_request.id
            idx = self._tab_bar.currentIndex()
            display_name = url if url else request_name
            self._tab_bar.update_tab(
                idx,
                method=method,
                name=display_name,
                path=self._request_full_path(new_request.id),
                is_dirty=False,
            )
            # Refresh breadcrumb
            crumbs = CollectionService.get_request_breadcrumb(new_request.id)
            self._breadcrumb_bar.set_path(crumbs)

        # Add the request to the tree sidebar
        self.collection_widget._tree_widget.add_request(
            {
                "name": new_request.name,
                "url": new_request.url,
                "id": new_request.id,
                "method": new_request.method,
            },
            collection_id,
        )
        self.collection_widget.select_and_scroll_to(new_request.id, "request")
        logger.info("Draft saved as request id=%s in collection=%s", new_request.id, collection_id)
