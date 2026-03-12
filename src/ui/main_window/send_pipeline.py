"""HTTP send pipeline mixin for the main window.

Provides ``_SendPipelineMixin`` with background HTTP request execution,
cancel, and cleanup methods.  Mixed into ``MainWindow``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread

if TYPE_CHECKING:
    from ui.environments.environment_selector import EnvironmentSelector
    from ui.panels.history_panel import HistoryPanel
    from ui.request.http_worker import HttpSendWorker
    from ui.request.navigation.request_tab_bar import RequestTabBar
    from ui.request.navigation.tab_manager import TabContext
    from ui.request.request_editor import RequestEditorWidget
    from ui.request.response_viewer import ResponseViewerWidget

logger = logging.getLogger(__name__)


class _SendPipelineMixin:
    """Mixin that adds the HTTP send/cancel/cleanup pipeline.

    Expects the host class to provide ``_tabs``, ``_tab_bar``,
    ``_send_thread``, ``_send_worker``, ``request_widget``,
    ``response_widget``, ``_env_selector``, and ``_history_panel``.
    """

    # -- Host-class interface (declared for mypy) -----------------------
    _send_thread: QThread | None
    _send_worker: HttpSendWorker | None
    _tab_bar: RequestTabBar
    _env_selector: EnvironmentSelector
    _history_panel: HistoryPanel
    request_widget: RequestEditorWidget
    response_widget: ResponseViewerWidget

    def _current_tab_context(self) -> TabContext | None: ...

    if TYPE_CHECKING:

        def _refresh_sidebar(self, ctx: TabContext | None = None) -> None: ...

    def _on_send_request(self) -> None:
        """Send the current request on a background thread."""
        ctx: TabContext | None = self._current_tab_context()

        # Folder tabs cannot send requests
        if ctx is not None and ctx.tab_type == "folder":
            return

        # If already sending, treat as cancel
        if ctx is not None and ctx.is_sending:
            self._cancel_send()
            return
        if self._send_thread is not None and self._send_thread.isRunning():
            self._cancel_send()
            return

        # 1. Gather request data from the current editor
        editor = ctx.editor if ctx else self.request_widget
        viewer = ctx.response_viewer if ctx else self.response_widget

        method = editor._method_combo.currentText()
        url = editor._url_input.text().strip()
        if not url:
            viewer.show_error("URL is empty")
            return

        headers = editor.get_headers_text()
        body = editor.get_request_data().get("body") or None

        # 2. Gather auth (with inheritance) and env_id for worker thread
        from services.collection_service import CollectionService

        auth_data = editor._get_auth_data()
        if ctx and ctx.request_id and auth_data is None:
            inherited = CollectionService.get_request_inherited_auth(ctx.request_id)
            if inherited:
                auth_data = inherited

        env_id = self._env_selector.current_environment_id()

        request_id = ctx.request_id if ctx else None

        # 3. Tear down any previous send thread
        if ctx is not None:
            ctx.cleanup_thread()
        else:
            self._cleanup_send_thread()

        # 4. Show loading state, spinner, and toggle button to Cancel
        viewer.show_loading()
        self._set_send_button_cancel(True)
        if ctx is not None:
            idx = self._tab_bar.currentIndex()
            self._tab_bar.update_tab(idx, is_sending=True)

        # 5. Create worker — variable resolution + auth on worker thread
        from ui.request.http_worker import HttpSendWorker

        worker = HttpSendWorker()
        worker.set_request(
            method=method,
            url=url,
            headers=headers,
            body=body,
            env_id=env_id,
            request_id=request_id,
            auth_data=auth_data,
            local_overrides={k: v["value"] for k, v in ctx.local_overrides.items()}
            if ctx
            else None,
        )

        thread = QThread()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_send_finished)
        worker.error.connect(self._on_send_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)

        if ctx is not None:
            ctx.thread = thread
            ctx.worker = worker
            ctx.is_sending = True
        else:
            self._send_thread = thread
            self._send_worker = worker
        thread.start()

    def _on_send_finished(self, data: dict) -> None:
        """Handle a successful HTTP response from the worker thread."""
        ctx = self._current_tab_context()
        viewer = ctx.response_viewer if ctx else self.response_widget
        viewer.load_response(data)
        self._set_send_button_cancel(False)
        if ctx is not None:
            idx = self._tab_bar.currentIndex()
            self._tab_bar.update_tab(idx, is_sending=False)
            ctx.cleanup_thread()
        else:
            self._cleanup_send_thread()
        # Add to history panel
        editor = ctx.editor if ctx else self.request_widget
        self._history_panel.add_entry(
            editor._method_combo.currentText(),
            editor._url_input.text(),
            data.get("status_code"),
            data.get("elapsed_ms", 0),
        )
        self._refresh_sidebar()

    def _on_send_error(self, message: str) -> None:
        """Handle an error from the HTTP send worker."""
        ctx = self._current_tab_context()
        viewer = ctx.response_viewer if ctx else self.response_widget
        viewer.show_error(message)
        self._set_send_button_cancel(False)
        if ctx is not None:
            idx = self._tab_bar.currentIndex()
            self._tab_bar.update_tab(idx, is_sending=False)
            ctx.cleanup_thread()
        else:
            self._cleanup_send_thread()
        # Add error entry to history panel
        editor = ctx.editor if ctx else self.request_widget
        self._history_panel.add_entry(
            editor._method_combo.currentText(),
            editor._url_input.text(),
        )
        self._refresh_sidebar()

    def _cancel_send(self) -> None:
        """Cancel the in-flight HTTP request."""
        ctx = self._current_tab_context()
        if ctx is not None:
            ctx.cancel_send()
            ctx.response_viewer.show_error("Request cancelled")
        else:
            if self._send_worker is not None:
                self._send_worker.cancel()
            self.response_widget.show_error("Request cancelled")
            self._cleanup_send_thread()
        self._set_send_button_cancel(False)

    def _set_send_button_cancel(self, is_cancel: bool) -> None:
        """Toggle the Send button between Send and Cancel states."""
        ctx = self._current_tab_context()
        if ctx is not None and ctx.tab_type == "folder":
            return
        editor = ctx.editor if ctx else self.request_widget
        btn = editor._send_btn
        if is_cancel:
            btn.setText("Cancel")
            btn.setObjectName("dangerButton")
        else:
            btn.setText("Send")
            btn.setObjectName("primaryButton")
        # Force style recalculation after objectName change
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _cleanup_send_thread(self) -> None:
        """Clean up the background send thread and worker."""
        if self._send_thread is not None:
            if self._send_thread.isRunning():
                self._send_thread.quit()
                self._send_thread.wait(3000)
            self._send_thread.deleteLater()
            self._send_thread = None
        if self._send_worker is not None:
            self._send_worker.deleteLater()
            self._send_worker = None
