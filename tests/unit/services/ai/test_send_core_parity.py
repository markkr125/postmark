"""Parity tests for SharedSendCore vs historical HttpSendWorker behaviour."""

from __future__ import annotations

import hashlib
import threading
from typing import Any
from unittest.mock import MagicMock, patch

from services.ai.chat.execution.redact_result import redact_send_result
from services.ai.chat.execution.send_core import run_shared_send
from services.scripting import ScriptEntry

_SAMPLE_RESPONSE: dict[str, Any] = {
    "status_code": 200,
    "status_text": "OK",
    "headers": [{"key": "Content-Type", "value": "application/json"}],
    "body": '{"ok": true, "token": "super-secret-token"}',
    "elapsed_ms": 10.0,
    "size_bytes": 40,
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


def _body_hash(body: str) -> str:
    """Stable hash for non-secret body comparison."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class TestSendCoreParity:
    """Enumerated SharedSendCore behaviours required by Phase 1."""

    @patch("services.ai.chat.execution.send_core.HttpService.send_request")
    def test_status_and_body_shape(self, mock_send: MagicMock) -> None:
        """Final HTTP status and body are returned on success."""
        mock_send.return_value = dict(_SAMPLE_RESPONSE)

        result = run_shared_send(method="GET", url="http://example.com")

        assert result["ok"] is True
        response = result["response"]
        assert response["status_code"] == 200
        assert response["body"] == _SAMPLE_RESPONSE["body"]
        assert _body_hash(response["body"]) == _body_hash(_SAMPLE_RESPONSE["body"])

    @patch("services.scripting.engine.ScriptEngine.run_pre_request_scripts")
    @patch("services.ai.chat.execution.send_core.HttpService.send_request")
    def test_pre_request_runtime_error_excluded_from_test_results(
        self, mock_send: MagicMock, mock_pre: MagicMock
    ) -> None:
        """Pre-request ``(runtime error)`` stays out of Test Results."""
        mock_send.return_value = dict(_SAMPLE_RESPONSE)
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

        result = run_shared_send(
            method="GET",
            url="http://example.com",
            pre_scripts=[
                {"code": "const x=n", "language": "javascript", "source_name": "Hyperguest"}
            ],
        )

        assert result["ok"] is True
        response = result["response"]
        assert response.get("test_results", []) == []
        console = response.get("console_logs", [])
        assert len(console) == 1
        assert console[0]["level"] == "error"
        assert "[Hyperguest]" in console[0]["message"]
        pre_errs = response.get("pre_request_errors", [])
        assert len(pre_errs) == 1
        assert pre_errs[0]["source_name"] == "Hyperguest"
        assert response.get("has_pre_request_scripts") is True

    @patch("services.scripting.engine.ScriptEngine.run_single")
    @patch("services.ai.chat.execution.send_core.HttpService.send_request")
    def test_declarative_tests_included(self, mock_send: MagicMock, mock_decl: MagicMock) -> None:
        """Declarative test script results appear in ``test_results``."""
        mock_send.return_value = dict(_SAMPLE_RESPONSE)
        mock_decl.return_value = {
            "test_results": [
                {
                    "name": "Status is 200",
                    "passed": True,
                    "error": None,
                    "duration_ms": 1.0,
                    "source_name": "declarative",
                }
            ],
            "console_logs": [],
            "variable_changes": {},
        }

        result = run_shared_send(
            method="GET",
            url="http://example.com",
            declarative_test_script={
                "code": 'pm.test("Status is 200", () => {});',
                "language": "javascript",
                "source_name": "declarative",
            },
        )

        assert result["ok"] is True
        tests = result["response"].get("test_results", [])
        assert len(tests) == 1
        assert tests[0]["name"] == "Status is 200"
        assert tests[0]["passed"] is True
        mock_decl.assert_called_once()

    @patch("services.environment_service.EnvironmentService.build_combined_variable_map")
    @patch("services.ai.chat.execution.send_core.HttpService.send_request")
    def test_local_overrides_win(self, mock_send: MagicMock, mock_vars: MagicMock) -> None:
        """Local overrides take precedence over env/collection variables."""
        mock_vars.return_value = {"base_url": "https://prod.example.com", "token": "abc"}
        mock_send.return_value = dict(_SAMPLE_RESPONSE)

        result = run_shared_send(
            method="GET",
            url="{{base_url}}/api",
            local_overrides={"base_url": "http://localhost:3000"},
        )

        assert result["ok"] is True
        call_kwargs = mock_send.call_args[1]
        assert "localhost:3000" in call_kwargs["url"]
        assert "prod.example.com" not in call_kwargs["url"]

    @patch("services.scripting.context.save_globals")
    @patch("services.scripting.context.load_globals", return_value={})
    @patch("services.scripting.engine.ScriptEngine.run_test_scripts")
    @patch("services.ai.chat.execution.send_core.HttpService.send_request")
    def test_persist_globals_opt_in(
        self,
        mock_send: MagicMock,
        mock_test: MagicMock,
        _mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Globals are saved only when ``persist_globals`` is true."""
        mock_send.return_value = dict(_SAMPLE_RESPONSE)
        mock_test.return_value = {
            "test_results": [],
            "console_logs": [],
            "variable_changes": {},
            "global_variable_changes": {"g1": "v1"},
        }
        scripts: list[ScriptEntry] = [
            {"code": "pm.globals.set('g1','v1')", "language": "javascript", "source_name": ""}
        ]

        skipped = run_shared_send(
            method="GET",
            url="http://example.com",
            test_scripts=scripts,
            persist_globals=False,
        )
        assert skipped["ok"] is True
        mock_save.assert_not_called()

        saved = run_shared_send(
            method="GET",
            url="http://example.com",
            test_scripts=scripts,
            persist_globals=True,
        )
        assert saved["ok"] is True
        mock_save.assert_called_once_with({"g1": "v1"})

    def test_cancel_event_before_send(self) -> None:
        """Cancel event set before start returns cancelled result."""
        event = threading.Event()
        event.set()
        result = run_shared_send(method="GET", url="http://example.com", cancel_event=event)
        assert result["ok"] is False
        assert result.get("cancelled") is True

    @patch("services.ai.chat.execution.send_core.HttpService.send_request")
    def test_agent_slot_acquire_releases(self, mock_send: MagicMock) -> None:
        """Agent slot is released after a successful send."""
        mock_send.return_value = dict(_SAMPLE_RESPONSE)
        result = run_shared_send(
            method="GET",
            url="http://example.com",
            acquire_agent_slot=True,
        )
        assert result["ok"] is True
        # A second acquire must succeed (previous slot released).
        result2 = run_shared_send(
            method="GET",
            url="http://example.com",
            acquire_agent_slot=True,
        )
        assert result2["ok"] is True


class TestRedactSendResult:
    """Agent observation redaction for send responses."""

    def test_redacts_secret_body_and_auth_header(self) -> None:
        """Sensitive header and JSON body secrets are masked."""
        raw: dict[str, Any] = {
            "status_code": 200,
            "headers": [
                {"key": "Authorization", "value": "Bearer secret-token"},
                {"key": "Content-Type", "value": "application/json"},
            ],
            "body": '{"access_token": "abc123", "name": "ok"}',
            "variable_changes": {"api_key": "plain-secret", "host": "api.example.com"},
            "console_logs": [{"level": "log", "message": "token=abc123", "timestamp": 0}],
        }
        redacted = redact_send_result(raw)
        headers = redacted["headers"]
        assert isinstance(headers, list)
        auth = next(h for h in headers if isinstance(h, dict) and h.get("key") == "Authorization")
        assert "secret-token" not in str(auth.get("value", ""))
        assert "abc123" not in str(redacted["body"])
        assert "ok" in str(redacted["body"])
        var_changes = redacted["variable_changes"]
        assert isinstance(var_changes, dict)
        assert var_changes["api_key"] != "plain-secret"
        assert var_changes["host"] == "api.example.com"
        console_logs = redacted["console_logs"]
        assert isinstance(console_logs, list)
        first_log = console_logs[0]
        assert isinstance(first_log, dict)
        assert "abc123" not in str(first_log.get("message", ""))
        # Original untouched
        orig_headers = raw["headers"]
        assert isinstance(orig_headers, list)
        assert isinstance(orig_headers[0], dict)
        assert orig_headers[0]["value"] == "Bearer secret-token"

    def test_redacts_test_results_errors(self) -> None:
        """Test result error strings must not leak Bearer secrets into observations."""
        raw: dict[str, Any] = {
            "status_code": 200,
            "test_results": [
                {
                    "name": "auth check",
                    "passed": False,
                    "error": "Expected Bearer SECRET_TOKEN_XYZ in response",
                }
            ],
        }
        redacted = redact_send_result(raw)
        tests = redacted["test_results"]
        assert isinstance(tests, list)
        err = str(tests[0].get("error", ""))
        assert "SECRET_TOKEN_XYZ" not in err
