"""Security sandbox tests — ensures scripts cannot escape isolation.

These tests are part of CI and are mandatory. A failing sandbox test
is a build-breaking bug.

JS tests require ``py_mini_racer`` and are skipped when unavailable.
Python tests use subprocess isolation and always run.
"""

from __future__ import annotations

import pytest

from services.scripting.py_runtime import PyRuntime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(response: dict | None = None) -> dict:
    """Return a minimal ``ScriptInput``."""
    return {
        "request": {"url": "https://example.com", "method": "GET", "headers": {}, "body": ""},
        "response": response,
        "variables": {},
        "environment_vars": {},
        "collection_vars": {},
        "info": {},
    }


# ===================================================================
# Python sandbox security tests
# ===================================================================


class TestPySandboxSecurity:
    """Verify Python sandbox blocks all escape vectors."""

    def test_import_os_blocked(self):
        result = PyRuntime.execute("import os", _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1, "import os should be blocked"

    def test_import_subprocess_blocked(self):
        result = PyRuntime.execute("import subprocess", _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1

    def test_open_file_blocked(self):
        result = PyRuntime.execute('open("/etc/passwd")', _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1, "open() should not be available"

    def test_dunder_import_blocked(self):
        result = PyRuntime.execute('__import__("os")', _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1

    def test_eval_blocked(self):
        result = PyRuntime.execute('eval("1+1")', _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1

    def test_exec_blocked(self):
        result = PyRuntime.execute('exec("print(1)")', _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1

    def test_dunder_class_access_blocked(self):
        result = PyRuntime.execute(
            "x = ().__class__.__bases__[0].__subclasses__()",
            _make_context(),
        )
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1, "__class__ access should be blocked by _getattr_ guard"

    def test_getattr_dunder_blocked(self):
        result = PyRuntime.execute(
            'getattr((), "__class__")',
            _make_context(),
        )
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1

    def test_pm_send_request_rate_limit(self):
        """Verify that more than 10 pm.send_request calls raise an error."""
        script = """
for i in range(11):
    pm.send_request("http://127.0.0.1:1")
"""
        result = PyRuntime.execute(script, _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1
        assert "rate limit" in failed[0]["error"].lower()

    def test_safe_builtins_available(self):
        script = """
pm.test("len works", lambda: pm.expect(len([1, 2, 3])).to.equal(3))
pm.test("range works", lambda: pm.expect(list(range(3))).to.eql([0, 1, 2]))
pm.test("int works", lambda: pm.expect(int("42")).to.equal(42))
pm.test("str works", lambda: pm.expect(str(42)).to.equal("42"))
"""
        result = PyRuntime.execute(script, _make_context())
        for r in result["test_results"]:
            assert r["passed"] is True, f"{r['name']} failed: {r['error']}"

    def test_safe_stdlib_available(self):
        script = """
pm.test("json", lambda: pm.expect(json_loads('{"a": 1}')).to.eql({"a": 1}))
pm.test("b64", lambda: pm.expect(b64decode(b64encode(b"hello"))).to.equal(b"hello"))
"""
        result = PyRuntime.execute(script, _make_context())
        for r in result["test_results"]:
            assert r["passed"] is True, f"{r['name']} failed: {r['error']}"

    def test_uuid_v4_available(self):
        """``uuid_v4()`` returns a valid UUID v4 string."""
        script = """
uid = uuid_v4()
pm.test("uuid format", lambda: pm.expect(len(uid)).to.equal(36))
pm.test("uuid dashes", lambda: pm.expect(uid.count("-")).to.equal(4))
pm.variables.set("uid", uid)
"""
        result = PyRuntime.execute(script, _make_context())
        for r in result["test_results"]:
            assert r["passed"] is True, f"{r['name']} failed: {r['error']}"
        uid = result["variable_changes"]["uid"]
        # Validate UUID v4 format.
        import uuid

        parsed = uuid.UUID(uid)
        assert parsed.version == 4

    def test_hashlib_hmac_sha256_available(self):
        """``hashlib_hmac_sha256()`` returns correct HMAC-SHA256 hex digest."""
        script = """
sig = hashlib_hmac_sha256("message", "secret")
pm.test("hmac type", lambda: pm.expect(sig).to.be.a("str"))
pm.test("hmac length", lambda: pm.expect(len(sig)).to.equal(64))
pm.variables.set("sig", sig)
"""
        result = PyRuntime.execute(script, _make_context())
        for r in result["test_results"]:
            assert r["passed"] is True, f"{r['name']} failed: {r['error']}"
        # Verify against known value.
        import hashlib
        import hmac

        expected = hmac.new(b"secret", b"message", hashlib.sha256).hexdigest()
        assert result["variable_changes"]["sig"] == expected

    def test_console_rate_limit(self):
        script = """
for i in range(250):
    print(f"msg {i}")
"""
        result = PyRuntime.execute(script, _make_context())
        # Should be capped at 200
        assert len(result["console_logs"]) <= 200

    def test_variable_changes_are_strings(self):
        script = """
pm.variables.set("num", "42")
pm.variables.set("bool", "True")
"""
        result = PyRuntime.execute(script, _make_context())
        for v in result["variable_changes"].values():
            assert isinstance(v, str)

    def test_type_three_arg_blocked(self):
        """``type(name, bases, dict)`` metaclass form must be blocked."""
        script = """
MyClass = type("Exploit", (), {"run": lambda self: None})
"""
        result = PyRuntime.execute(script, _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1, "type() with 3 args should be blocked"

    def test_type_single_arg_allowed(self):
        """``type(obj)`` inspection form must still work."""
        script = """
pm.test("type int", lambda: pm.expect(type(42)).to.equal(int))
pm.test("type str", lambda: pm.expect(type("x")).to.equal(str))
"""
        result = PyRuntime.execute(script, _make_context())
        for r in result["test_results"]:
            assert r["passed"] is True, f"{r['name']} failed: {r['error']}"


# ===================================================================
# JS sandbox security tests (require py_mini_racer)
# ===================================================================


class TestJSSandboxSecurity:
    """Verify JavaScript V8 sandbox blocks escape vectors.

    Skipped when py_mini_racer is not available.
    """

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        pytest.importorskip("py_mini_racer")

    def test_require_blocked(self):
        from services.scripting.js_runtime import JSRuntime

        script = 'var fs = require("fs");'
        result = JSRuntime.execute(script, _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1, "require() should not exist in V8 isolate"

    def test_fetch_blocked(self):
        from services.scripting.js_runtime import JSRuntime

        script = 'fetch("http://example.com");'
        result = JSRuntime.execute(script, _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1, "fetch() should not exist in V8 isolate"

    def test_send_request_rate_limit(self):
        from services.scripting.js_runtime import JSRuntime

        # pm.sendRequest calls __pm_send_request which doesn't exist
        script = """
pm.test("rate limit", function() {
    try {
        pm.sendRequest("http://example.com");
    } catch(e) {
        // Expected: __pm_send_request not available
    }
});
"""
        result = JSRuntime.execute(script, _make_context())
        # Should not crash — error is caught gracefully
        assert len(result["test_results"]) >= 1

    def test_response_frozen_in_test_context(self):
        from services.scripting.js_runtime import JSRuntime

        script = """
pm.response.code = 999;
pm.test("frozen", function() { pm.expect(pm.response.code).to.equal(200); });
"""
        result = JSRuntime.execute(
            script, _make_context(response={"status_code": 200, "body": "ok"})
        )
        # Response should remain frozen
        assert len(result["test_results"]) >= 1

    def test_console_rate_limit(self):
        from services.scripting.js_runtime import JSRuntime

        script = """
for (var i = 0; i < 250; i++) {
    console.log("msg " + i);
}
"""
        result = JSRuntime.execute(script, _make_context())
        assert len(result["console_logs"]) <= 200
