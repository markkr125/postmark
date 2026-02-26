"""Tests for HttpSendWorker signal emission and cancellation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from ui.http_worker import HttpSendWorker


class TestHttpSendWorker:
    """Tests for the HTTP send worker."""

    def test_construction(self, qapp: QApplication) -> None:
        """Worker can be instantiated without errors."""
        worker = HttpSendWorker()
        assert worker is not None
        assert not worker.is_cancelled

    def test_set_request(self, qapp: QApplication) -> None:
        """Setting request parameters stores them internally."""
        worker = HttpSendWorker()
        worker.set_request(method="POST", url="http://example.com", body="data")
        assert worker._method == "POST"
        assert worker._url == "http://example.com"
        assert worker._body == "data"

    @patch("ui.http_worker.HttpService.send_request")
    def test_run_emits_finished(self, mock_send: MagicMock, qapp: QApplication) -> None:
        """Successful run emits the finished signal with response data."""
        mock_send.return_value = {
            "status_code": 200,
            "status_text": "OK",
            "headers": [],
            "body": "ok",
            "elapsed_ms": 10.0,
            "size_bytes": 2,
        }

        worker = HttpSendWorker()
        worker.set_request(method="GET", url="http://example.com")

        received: list[dict] = []
        worker.finished.connect(received.append)

        worker.run()

        assert len(received) == 1
        assert received[0]["status_code"] == 200

    @patch("ui.http_worker.HttpService.send_request")
    def test_run_emits_error_on_exception(self, mock_send: MagicMock, qapp: QApplication) -> None:
        """Worker emits error signal when HttpService raises."""
        mock_send.side_effect = RuntimeError("boom")

        worker = HttpSendWorker()
        worker.set_request(method="GET", url="http://example.com")

        errors: list[str] = []
        worker.error.connect(errors.append)

        worker.run()

        assert len(errors) == 1
        assert "boom" in errors[0]

    def test_cancel_sets_flag(self, qapp: QApplication) -> None:
        """Calling cancel() sets the cancellation flag."""
        worker = HttpSendWorker()
        assert not worker.is_cancelled
        worker.cancel()
        assert worker.is_cancelled

    def test_run_cancelled_before_request(self, qapp: QApplication) -> None:
        """Worker emits error if cancelled before run() starts."""
        worker = HttpSendWorker()
        worker.set_request(method="GET", url="http://example.com")
        worker.cancel()

        errors: list[str] = []
        worker.error.connect(errors.append)

        worker.run()

        assert len(errors) == 1
        assert "cancelled" in errors[0].lower()

    @patch("ui.http_worker.HttpService.send_request")
    def test_run_cancelled_after_request(self, mock_send: MagicMock, qapp: QApplication) -> None:
        """Worker emits error if cancelled after the HTTP call returns."""
        mock_send.return_value = {
            "status_code": 200,
            "status_text": "OK",
            "headers": [],
            "body": "",
            "elapsed_ms": 5.0,
            "size_bytes": 0,
        }

        worker = HttpSendWorker()
        worker.set_request(method="GET", url="http://example.com")

        # Cancel during the send (simulate by setting the flag in the mock)
        def cancel_side_effect(**kwargs):
            worker.cancel()
            return mock_send.return_value

        mock_send.side_effect = cancel_side_effect

        errors: list[str] = []
        finished: list[dict] = []
        worker.error.connect(errors.append)
        worker.finished.connect(finished.append)

        worker.run()

        assert len(errors) == 1
        assert "cancelled" in errors[0].lower()
        assert len(finished) == 0
