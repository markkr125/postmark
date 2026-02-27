"""Per-tab state management for the request tab bar.

Each ``TabContext`` bundles the widgets, thread, and worker that belong
to a single request tab.  The ``TabManager`` maintains the mapping from
tab indices to their contexts.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread

if TYPE_CHECKING:
    from ui.request.http_worker import HttpSendWorker

from ui.request.request_editor import RequestEditorWidget
from ui.request.response_viewer import ResponseViewerWidget

logger = logging.getLogger(__name__)

# Maximum wait (ms) when shutting down a worker thread.
_THREAD_WAIT_MS = 3000


class TabContext:
    """Bundle of per-tab state: widgets, thread lifecycle, and dirty flag.

    Attributes:
        request_id: Database PK of the loaded request, or ``None`` for
            new/unsaved requests.
        editor: The request editor widget for this tab.
        response_viewer: The response viewer widget for this tab.
        thread: The ``QThread`` running the current request, if any.
        worker: The ``HttpSendWorker`` for the current request, if any.
        is_dirty: Whether the editor has unsaved changes.
        is_sending: Whether an HTTP request is currently in flight.
        is_preview: Whether this tab is in preview mode (temporary).
    """

    def __init__(
        self,
        *,
        request_id: int | None = None,
        editor: RequestEditorWidget | None = None,
        response_viewer: ResponseViewerWidget | None = None,
        is_preview: bool = False,
    ) -> None:
        """Create a new tab context with optional pre-built widgets."""
        self.request_id = request_id
        self.editor = editor or RequestEditorWidget()
        self.response_viewer = response_viewer or ResponseViewerWidget()
        self.thread: QThread | None = None
        self.worker: HttpSendWorker | None = None
        self.is_dirty: bool = False
        self.is_sending: bool = False
        self.is_preview: bool = is_preview

    # -- Send lifecycle ------------------------------------------------

    def start_send(
        self,
        *,
        method: str,
        url: str,
        headers: str | None = None,
        body: str | None = None,
    ) -> None:
        """Create a worker and thread, then start the HTTP request.

        The caller is responsible for connecting ``worker.finished`` and
        ``worker.error`` to appropriate slots before this method returns.
        """
        # Tear down any previous send
        self.cleanup_thread()

        from ui.request.http_worker import HttpSendWorker

        worker = HttpSendWorker()
        worker.set_request(method=method, url=url, headers=headers, body=body)

        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        # Auto-quit the thread when the worker signals completion
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)

        self.thread = thread
        self.worker = worker
        self.is_sending = True

    def cancel_send(self) -> None:
        """Cancel the in-flight request and clean up the thread."""
        if self.worker is not None:
            self.worker.cancel()
        self.cleanup_thread()

    def cleanup_thread(self) -> None:
        """Stop and delete the worker thread, releasing all references.

        Follows the ``_ImportWorker._cleanup_thread`` pattern:
        ``quit()`` → ``wait(3000)`` → ``deleteLater()``.
        """
        if self.thread is not None:
            if self.thread.isRunning():
                self.thread.quit()
                self.thread.wait(_THREAD_WAIT_MS)
            self.thread.deleteLater()
            self.thread = None
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
        self.is_sending = False

    def dispose(self) -> None:
        """Release all Python references held by this context.

        Call after the widgets have been removed from their parent
        layouts and scheduled for deletion.  Clearing the Python-side
        attributes allows the garbage collector to reclaim the PySide6
        wrapper objects without waiting for ``deleteLater`` to fire.
        """
        self.cleanup_thread()
        self.editor = None  # type: ignore[assignment]
        self.response_viewer = None  # type: ignore[assignment]
        self.request_id = None
