"""Tests for pm.sendRequest HTTP bridge and pm.globals persistence.

Covers the ``execute_sub_request()`` function's scheme whitelist, header
parsing, body parsing, and error handling.  Also covers global variable
persistence via ``load_globals()`` / ``save_globals()`` and the globals
propagation through the script engine chain.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from services.scripting import ScriptEngine, ScriptEntry, ScriptInput
from services.scripting.context import execute_sub_request, load_globals, save_globals
from services.scripting.py_runtime import PyRuntime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    *,
    response: dict[str, Any] | None = None,
    variables: dict[str, str] | None = None,
    global_vars: dict[str, str] | None = None,
) -> ScriptInput:
    """Return a minimal ``ScriptInput`` for testing."""
    return {
        "request": {"url": "https://example.com", "method": "GET", "headers": {}, "body": ""},
        "response": response,
        "variables": variables or {},
        "environment_vars": {},
        "collection_vars": {},
        "global_vars": global_vars or {},
        "info": {"requestName": "test"},
    }


# ===================================================================
# execute_sub_request tests
# ===================================================================


class TestExecuteSubRequest:
    """Tests for the HTTP sub-request bridge function."""

    def test_rejects_file_scheme(self) -> None:
        result = execute_sub_request({"url": "file:///etc/passwd"})
        assert "error" in result
        assert "Scheme not allowed" in result["error"]

    def test_rejects_empty_scheme(self) -> None:
        result = execute_sub_request({"url": "noscheme"})
        assert "error" in result

    def test_rejects_ftp_scheme(self) -> None:
        result = execute_sub_request({"url": "ftp://example.com/file"})
        assert "error" in result
        assert "ftp" in result["error"].lower()

    def test_parses_headers_list(self) -> None:
        """Headers in list-of-dict format should be converted."""
        with patch("httpx.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.reason_phrase = "OK"
            mock_resp.headers = {}
            mock_resp.text = ""
            mock_resp.content = b""
            mock_req.return_value = mock_resp

            execute_sub_request(
                {
                    "url": "https://example.com",
                    "header": [{"key": "X-Custom", "value": "test"}],
                }
            )
            call_kwargs = mock_req.call_args
            assert call_kwargs.kwargs["headers"]["X-Custom"] == "test"

    def test_parses_headers_dict(self) -> None:
        """Headers in plain dict format should be passed through."""
        with patch("httpx.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.reason_phrase = "OK"
            mock_resp.headers = {}
            mock_resp.text = ""
            mock_resp.content = b""
            mock_req.return_value = mock_resp

            execute_sub_request(
                {
                    "url": "https://example.com",
                    "headers": {"Authorization": "Bearer tok"},
                }
            )
            call_kwargs = mock_req.call_args
            assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer tok"

    def test_parses_body_string(self) -> None:
        with patch("httpx.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.reason_phrase = "OK"
            mock_resp.headers = {}
            mock_resp.text = ""
            mock_resp.content = b""
            mock_req.return_value = mock_resp

            execute_sub_request(
                {
                    "url": "https://example.com",
                    "method": "POST",
                    "body": "hello",
                }
            )
            call_kwargs = mock_req.call_args
            assert call_kwargs.kwargs["content"] == b"hello"

    def test_parses_body_dict(self) -> None:
        with patch("httpx.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.reason_phrase = "OK"
            mock_resp.headers = {}
            mock_resp.text = ""
            mock_resp.content = b""
            mock_req.return_value = mock_resp

            execute_sub_request(
                {
                    "url": "https://example.com",
                    "method": "POST",
                    "body": {"mode": "raw", "raw": '{"key": "val"}'},
                }
            )
            call_kwargs = mock_req.call_args
            assert call_kwargs.kwargs["content"] == b'{"key": "val"}'

    def test_returns_response_fields(self) -> None:
        with patch("httpx.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.reason_phrase = "Created"
            mock_resp.headers = {"Content-Type": "application/json"}
            mock_resp.text = '{"id": 1}'
            mock_resp.content = b'{"id": 1}'
            mock_req.return_value = mock_resp

            result = execute_sub_request({"url": "https://api.example.com"})
            assert result["code"] == 201
            assert result["status"] == "Created"
            assert result["body"] == '{"id": 1}'
            assert isinstance(result["responseTime"], float)
            assert result["responseSize"] == len(b'{"id": 1}')

    def test_handles_network_error(self) -> None:
        with patch("httpx.request", side_effect=ConnectionError("refused")):
            result = execute_sub_request({"url": "https://down.example.com"})
            assert "error" in result
            assert "refused" in result["error"]

    def test_rejects_oversized_response(self) -> None:
        """Responses larger than 10 MB should be rejected."""
        with patch("httpx.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.reason_phrase = "OK"
            mock_resp.headers = {}
            mock_resp.text = "x" * 100
            mock_resp.content = b"x" * (11 * 1024 * 1024)  # 11 MB
            mock_req.return_value = mock_resp

            result = execute_sub_request({"url": "https://example.com"})
            assert "error" in result
            assert "too large" in result["error"].lower()


# ===================================================================
# Globals persistence tests
# ===================================================================


class TestGlobalsPersistence:
    """Tests for ``load_globals()`` and ``save_globals()``."""

    def test_load_empty_when_no_file(self, tmp_path: Any) -> None:
        with patch("services.scripting.context._GLOBALS_PATH", tmp_path / "missing.json"):
            assert load_globals() == {}

    def test_save_and_load_roundtrip(self, tmp_path: Any) -> None:
        path = tmp_path / "globals.json"
        with patch("services.scripting.context._GLOBALS_PATH", path):
            save_globals({"api_key": "abc123", "version": "2"})
            result = load_globals()
            assert result == {"api_key": "abc123", "version": "2"}

    def test_save_merges_with_existing(self, tmp_path: Any) -> None:
        path = tmp_path / "globals.json"
        path.write_text(json.dumps({"existing": "val"}))
        with patch("services.scripting.context._GLOBALS_PATH", path):
            save_globals({"new_key": "new_val"})
            result = load_globals()
            assert result["existing"] == "val"
            assert result["new_key"] == "new_val"

    def test_load_handles_corrupt_file(self, tmp_path: Any) -> None:
        path = tmp_path / "globals.json"
        path.write_text("not json!!")
        with patch("services.scripting.context._GLOBALS_PATH", path):
            assert load_globals() == {}


# ===================================================================
# Globals in scripting runtime
# ===================================================================


class TestGlobalsInScripts:
    """Verify pm.globals works with initial data and tracks changes."""

    def test_python_globals_set_tracked_separately(self) -> None:
        """pm.globals.set() should appear in global_variable_changes, not variable_changes."""
        result = PyRuntime.execute(
            'pm.globals.set("gkey", "gval")',
            _make_context(),
        )
        assert result.get("global_variable_changes", {}).get("gkey") == "gval"
        assert "gkey" not in result.get("variable_changes", {})

    def test_python_globals_initialized_from_context(self) -> None:
        result = PyRuntime.execute(
            'pm.test("check", lambda: pm.expect(pm.globals.get("preset")).to.equal("hello"))',
            _make_context(global_vars={"preset": "hello"}),
        )
        assert result["test_results"][0]["passed"] is True

    def test_engine_chain_propagates_globals(self) -> None:
        """Globals changes from first script should be visible in second."""
        chain: list[ScriptEntry] = [
            {
                "code": 'pm.globals.set("chain_key", "from_first")',
                "language": "python",
                "source_name": "collection",
            },
            {
                "code": (
                    'pm.test("check", lambda: '
                    'pm.expect(pm.globals.get("chain_key")).to.equal("from_first"))'
                ),
                "language": "python",
                "source_name": "request",
            },
        ]
        result = ScriptEngine.run_pre_request_scripts(chain, _make_context())
        assert result.get("global_variable_changes", {}).get("chain_key") == "from_first"
        check = [r for r in result["test_results"] if r["name"] == "check"]
        assert len(check) == 1
        assert check[0]["passed"] is True


# ===================================================================
# JS globals tests (require Deno)
# ===================================================================


class TestJSGlobals:
    """Verify pm.globals works in the JS runtime."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

    def test_js_globals_set_tracked_separately(self) -> None:
        from services.scripting.js_runtime import JSRuntime

        script = 'pm.globals.set("jskey", "jsval");'
        result = JSRuntime.execute(script, _make_context())
        assert result.get("global_variable_changes", {}).get("jskey") == "jsval"
        assert "jskey" not in result.get("variable_changes", {})

    def test_js_globals_initialized_from_context(self) -> None:
        from services.scripting.js_runtime import JSRuntime

        script = """
pm.test("check", function() {
    pm.expect(pm.globals.get("preset")).to.equal("hi");
});
"""
        result = JSRuntime.execute(script, _make_context(global_vars={"preset": "hi"}))
        assert result["test_results"][0]["passed"] is True
        assert result["test_results"][0]["passed"] is True
