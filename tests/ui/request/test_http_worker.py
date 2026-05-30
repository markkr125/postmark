"""Tests for HttpSendWorker signal emission and cancellation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from ui.request.http_worker import HttpSendWorker

# Minimal valid response dict matching the new HttpResponseDict schema.
_SAMPLE_RESPONSE: dict = {
    "status_code": 200,
    "status_text": "OK",
    "headers": [],
    "body": "ok",
    "elapsed_ms": 10.0,
    "size_bytes": 2,
    "timing": {
        "dns_ms": 1.0,
        "tcp_ms": 2.0,
        "tls_ms": 0.0,
        "ttfb_ms": 3.0,
        "download_ms": 1.0,
        "process_ms": 3.0,
    },
    "request_headers_size": 0,
    "request_body_size": 0,
    "response_headers_size": 0,
    "network": {
        "http_version": "HTTP/1.1",
        "remote_address": "93.184.216.34:80",
        "local_address": "192.168.1.10:54321",
        "tls_protocol": None,
        "cipher_name": None,
        "certificate_cn": None,
        "issuer_cn": None,
        "valid_until": None,
    },
}

# Minimal empty response for cancel-after-request tests.
_EMPTY_RESPONSE: dict = {
    "status_code": 200,
    "status_text": "OK",
    "headers": [],
    "body": "",
    "elapsed_ms": 5.0,
    "size_bytes": 0,
    "timing": {
        "dns_ms": 0.0,
        "tcp_ms": 0.0,
        "tls_ms": 0.0,
        "ttfb_ms": 0.0,
        "download_ms": 0.0,
        "process_ms": 5.0,
    },
    "request_headers_size": 0,
    "request_body_size": 0,
    "response_headers_size": 0,
    "network": {
        "http_version": "HTTP/1.1",
        "remote_address": "",
        "local_address": "",
        "tls_protocol": None,
        "cipher_name": None,
        "certificate_cn": None,
        "issuer_cn": None,
        "valid_until": None,
    },
}


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

    def test_set_request_with_request_id(self, qapp: QApplication) -> None:
        """Setting request_id stores it for variable chain resolution."""
        worker = HttpSendWorker()
        worker.set_request(
            method="GET",
            url="http://example.com",
            request_id=42,
        )
        assert worker._request_id == 42

    def test_set_request_with_local_overrides(self, qapp: QApplication) -> None:
        """Local overrides dict is stored on the worker."""
        worker = HttpSendWorker()
        overrides = {"base_url": "http://localhost:3000"}
        worker.set_request(
            method="GET",
            url="http://example.com",
            local_overrides=overrides,
        )
        assert worker._local_overrides == overrides

    def test_set_request_local_overrides_defaults_empty(self, qapp: QApplication) -> None:
        """Local overrides default to empty dict when not provided."""
        worker = HttpSendWorker()
        worker.set_request(method="GET", url="http://example.com")
        assert worker._local_overrides == {}

    def test_request_id_defaults_to_none(self, qapp: QApplication) -> None:
        """request_id defaults to None when not provided."""
        worker = HttpSendWorker()
        worker.set_request(method="GET", url="http://example.com")
        assert worker._request_id is None

    @patch("ui.request.http_worker.HttpService.send_request")
    def test_run_emits_finished(self, mock_send: MagicMock, qapp: QApplication) -> None:
        """Successful run emits the finished signal with response data."""
        mock_send.return_value = _SAMPLE_RESPONSE

        worker = HttpSendWorker()
        worker.set_request(method="GET", url="http://example.com")

        received: list[dict] = []
        worker.finished.connect(received.append)

        worker.run()

        assert len(received) == 1
        assert received[0]["status_code"] == 200

    @patch("ui.request.http_worker.HttpService.send_request")
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

    @patch("ui.request.http_worker.HttpService.send_request")
    def test_run_cancelled_after_request(self, mock_send: MagicMock, qapp: QApplication) -> None:
        """Worker emits error if cancelled after the HTTP call returns."""
        mock_send.return_value = _EMPTY_RESPONSE

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

    @patch("services.environment_service.EnvironmentService.build_combined_variable_map")
    @patch("ui.request.http_worker.HttpService.send_request")
    def test_run_applies_local_overrides(
        self, mock_send: MagicMock, mock_vars: MagicMock, qapp: QApplication
    ) -> None:
        """Local overrides take precedence over environment variables."""
        mock_vars.return_value = {"base_url": "https://prod.example.com", "token": "abc"}
        mock_send.return_value = _SAMPLE_RESPONSE

        worker = HttpSendWorker()
        worker.set_request(
            method="GET",
            url="{{base_url}}/api",
            local_overrides={"base_url": "http://localhost:3000"},
        )

        received: list[dict] = []
        worker.finished.connect(received.append)
        worker.run()

        assert len(received) == 1
        # The send_request call should have received the locally-overridden URL
        call_kwargs = mock_send.call_args[1]
        assert "localhost:3000" in call_kwargs["url"]


class TestPreRequestErrorRouting:
    """Pre-request runtime errors go to console_logs, not test_results."""

    @patch("services.scripting.engine.ScriptEngine.run_pre_request_scripts")
    @patch("ui.request.http_worker.HttpService.send_request")
    def test_pre_request_runtime_error_routed_to_console(
        self, mock_send: MagicMock, mock_pre: MagicMock, qapp: QApplication
    ) -> None:
        """A runtime error from a pre-request script appears in console_logs."""
        mock_send.return_value = _SAMPLE_RESPONSE
        mock_pre.return_value = {
            "test_results": [
                {
                    "name": "(runtime error)",
                    "passed": False,
                    "error": "n is not defined",
                    "source_name": "Hyperguest",
                    "duration_ms": 0,
                }
            ],
            "console_logs": [],
            "variable_changes": {},
        }

        worker = HttpSendWorker()
        worker.set_request(
            method="GET",
            url="http://example.com",
            pre_scripts=[
                {"code": "const x=n", "language": "javascript", "source_name": "Hyperguest"}
            ],
        )

        received: list[dict] = []
        worker.finished.connect(received.append)
        worker.run()

        assert len(received) == 1
        resp = received[0]
        # Runtime error must NOT appear in test_results
        assert resp.get("test_results", []) == []
        # Runtime error must appear as an error-level console log
        console = resp.get("console_logs", [])
        assert len(console) == 1
        assert console[0]["level"] == "error"
        assert "[Hyperguest]" in console[0]["message"]
        assert "n is not defined" in console[0]["message"]
        # Runtime error must also appear in pre_request_errors
        pre_errs = resp.get("pre_request_errors", [])
        assert len(pre_errs) == 1
        assert pre_errs[0]["source_name"] == "Hyperguest"
        # Pre-request console logs should be separated
        pre_console = resp.get("pre_request_console_logs", [])
        assert pre_console == []  # no normal logs, only the error
        # has_pre_request_scripts flag must be set
        assert resp.get("has_pre_request_scripts") is True

    @patch("services.scripting.engine.ScriptEngine.run_pre_request_scripts")
    @patch("ui.request.http_worker.HttpService.send_request")
    def test_pre_request_console_logs_preserved(
        self, mock_send: MagicMock, mock_pre: MagicMock, qapp: QApplication
    ) -> None:
        """Normal console.log output from pre-request scripts is preserved."""
        mock_send.return_value = _SAMPLE_RESPONSE
        mock_pre.return_value = {
            "test_results": [],
            "console_logs": [{"level": "log", "message": "hello", "timestamp": 0}],
            "variable_changes": {},
        }

        worker = HttpSendWorker()
        worker.set_request(
            method="GET",
            url="http://example.com",
            pre_scripts=[
                {"code": "console.log('hello')", "language": "javascript", "source_name": ""}
            ],
        )

        received: list[dict] = []
        worker.finished.connect(received.append)
        worker.run()

        assert len(received) == 1
        console = received[0].get("console_logs", [])
        assert any(c["message"] == "hello" for c in console)
        # Pre-request console logs must also be separated
        pre_console = received[0].get("pre_request_console_logs", [])
        assert len(pre_console) == 1
        assert pre_console[0]["message"] == "hello"
