"""Tests for the TabContext per-tab state manager."""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from ui.request.request_editor import RequestEditorWidget
from ui.request.response_viewer import ResponseViewerWidget
from ui.request.tab_manager import TabContext


class TestTabContext:
    """Tests for TabContext lifecycle management."""

    def test_construction_defaults(self, qapp: QApplication, qtbot) -> None:
        """TabContext creates default widgets when none are provided."""
        ctx = TabContext()
        qtbot.addWidget(ctx.editor)
        qtbot.addWidget(ctx.response_viewer)

        assert isinstance(ctx.editor, RequestEditorWidget)
        assert isinstance(ctx.response_viewer, ResponseViewerWidget)
        assert ctx.request_id is None
        assert ctx.thread is None
        assert ctx.worker is None
        assert not ctx.is_dirty
        assert not ctx.is_sending
        assert not ctx.is_preview

    def test_construction_with_request_id(self, qapp: QApplication, qtbot) -> None:
        """TabContext accepts a request_id."""
        ctx = TabContext(request_id=42)
        qtbot.addWidget(ctx.editor)
        qtbot.addWidget(ctx.response_viewer)

        assert ctx.request_id == 42

    def test_construction_with_custom_widgets(self, qapp: QApplication, qtbot) -> None:
        """TabContext can accept pre-built widgets."""
        editor = RequestEditorWidget()
        viewer = ResponseViewerWidget()
        qtbot.addWidget(editor)
        qtbot.addWidget(viewer)

        ctx = TabContext(editor=editor, response_viewer=viewer)
        assert ctx.editor is editor
        assert ctx.response_viewer is viewer

    def test_construction_preview_mode(self, qapp: QApplication, qtbot) -> None:
        """TabContext supports preview mode flag."""
        ctx = TabContext(is_preview=True)
        qtbot.addWidget(ctx.editor)
        qtbot.addWidget(ctx.response_viewer)
        assert ctx.is_preview

    def test_cleanup_thread_with_no_thread(self, qapp: QApplication, qtbot) -> None:
        """Cleanup is safe when no thread exists."""
        ctx = TabContext()
        qtbot.addWidget(ctx.editor)
        qtbot.addWidget(ctx.response_viewer)

        ctx.cleanup_thread()  # Should not raise
        assert ctx.thread is None
        assert ctx.worker is None
        assert not ctx.is_sending

    def test_cleanup_thread_stops_running_thread(self, qapp: QApplication, qtbot) -> None:
        """Cleanup stops a running thread and releases references."""
        ctx = TabContext()
        qtbot.addWidget(ctx.editor)
        qtbot.addWidget(ctx.response_viewer)

        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True
        mock_worker = MagicMock()

        ctx.thread = mock_thread
        ctx.worker = mock_worker
        ctx.is_sending = True

        ctx.cleanup_thread()

        mock_thread.quit.assert_called_once()
        mock_thread.wait.assert_called_once_with(3000)
        mock_thread.deleteLater.assert_called_once()
        mock_worker.deleteLater.assert_called_once()
        assert ctx.thread is None
        assert ctx.worker is None
        assert not ctx.is_sending

    def test_cleanup_thread_stopped_thread(self, qapp: QApplication, qtbot) -> None:
        """Cleanup handles an already-stopped thread."""
        ctx = TabContext()
        qtbot.addWidget(ctx.editor)
        qtbot.addWidget(ctx.response_viewer)

        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = False
        mock_worker = MagicMock()

        ctx.thread = mock_thread
        ctx.worker = mock_worker

        ctx.cleanup_thread()

        mock_thread.quit.assert_not_called()
        mock_thread.deleteLater.assert_called_once()
        assert ctx.thread is None

    def test_cancel_send_cancels_worker_and_cleans_up(self, qapp: QApplication, qtbot) -> None:
        """cancel_send() calls cancel on the worker and cleans up."""
        ctx = TabContext()
        qtbot.addWidget(ctx.editor)
        qtbot.addWidget(ctx.response_viewer)

        mock_worker = MagicMock()
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True

        ctx.worker = mock_worker
        ctx.thread = mock_thread
        ctx.is_sending = True

        ctx.cancel_send()

        mock_worker.cancel.assert_called_once()
        mock_thread.quit.assert_called_once()
        assert ctx.thread is None
        assert ctx.worker is None
        assert not ctx.is_sending

    def test_start_send_creates_worker_and_thread(self, qapp: QApplication, qtbot) -> None:
        """start_send() creates a worker and thread pair."""
        ctx = TabContext()
        qtbot.addWidget(ctx.editor)
        qtbot.addWidget(ctx.response_viewer)

        ctx.start_send(method="GET", url="http://example.com")

        assert ctx.worker is not None
        assert ctx.thread is not None
        assert ctx.is_sending
        assert ctx.worker._method == "GET"
        assert ctx.worker._url == "http://example.com"

        # Clean up before test ends
        ctx.cleanup_thread()

    def test_start_send_cleans_up_previous(self, qapp: QApplication, qtbot) -> None:
        """start_send() tears down a previous worker before creating new one."""
        ctx = TabContext()
        qtbot.addWidget(ctx.editor)
        qtbot.addWidget(ctx.response_viewer)

        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True
        mock_worker = MagicMock()

        ctx.thread = mock_thread
        ctx.worker = mock_worker

        ctx.start_send(method="POST", url="http://example.com")

        # Previous thread should have been cleaned up
        mock_thread.quit.assert_called_once()
        mock_thread.deleteLater.assert_called_once()
        mock_worker.deleteLater.assert_called_once()

        # New one should be active
        assert ctx.worker is not None
        assert ctx.thread is not None
        assert ctx.is_sending

        ctx.cleanup_thread()
