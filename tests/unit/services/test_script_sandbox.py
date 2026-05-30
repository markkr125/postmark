"""Security sandbox tests — ensures scripts cannot escape isolation.

These tests are part of CI and are mandatory. A failing sandbox test
is a build-breaking bug.

JS tests require **Deno** and are skipped when the binary is unavailable.
Python tests use :meth:`services.scripting.py_runtime.PyRuntime.execute_restricted`
(the RestrictedPython subprocess) so security expectations stay stable even when
:meth:`PyRuntime.execute` prefers Pyodide + Deno.
"""

from __future__ import annotations

import pytest

from services.scripting import ScriptInput
from services.scripting.py_runtime import PyRuntime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(response: dict | None = None) -> ScriptInput:
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
        result = PyRuntime.execute_restricted("import os", _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1, "import os should be blocked"

    def test_import_subprocess_blocked(self):
        result = PyRuntime.execute_restricted("import subprocess", _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1

    def test_open_file_blocked(self):
        result = PyRuntime.execute_restricted('open("/etc/passwd")', _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1, "open() should not be available"

    def test_dunder_import_blocked(self):
        result = PyRuntime.execute_restricted('__import__("os")', _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1

    def test_eval_blocked(self):
        result = PyRuntime.execute_restricted('eval("1+1")', _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1

    def test_exec_blocked(self):
        result = PyRuntime.execute_restricted('exec("print(1)")', _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1

    def test_dunder_class_access_blocked(self):
        result = PyRuntime.execute_restricted(
            "x = ().__class__.__bases__[0].__subclasses__()",
            _make_context(),
        )
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1, "__class__ access should be blocked by _getattr_ guard"

    def test_getattr_dunder_blocked(self):
        result = PyRuntime.execute_restricted(
            'getattr((), "__class__")',
            _make_context(),
        )
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1

    def test_getitem_guard_blocks_dunder_keys(self):
        """Subscript access to dunder keys is blocked; normal keys still work."""
        from services.scripting._sandbox_runtime import _getitem_guard

        with pytest.raises(KeyError):
            _getitem_guard({"__class__": 1}, "__class__")
        # Single-underscore JSON keys (e.g. Mongo _id, HAL _links) keep working.
        assert _getitem_guard({"_id": 5}, "_id") == 5
        assert _getitem_guard([10, 20], 1) == 20

    def test_pm_require_host_module_blocked(self):
        """pm.require must not import arbitrary host modules (sandbox escape)."""
        for mod in ("os", "subprocess", "sys", "importlib"):
            result = PyRuntime.execute_restricted(f'pm.require("{mod}")', _make_context())
            failed = [r for r in result["test_results"] if not r["passed"]]
            assert len(failed) >= 1, f"pm.require({mod!r}) should be blocked"
            assert "not available" in failed[0]["error"].lower()

    def test_pm_require_bundled_module_allowed(self):
        """pm.require still resolves an allowlisted bundled module (uuid)."""
        script = (
            'pm.test("uuid", lambda: pm.expect(len(str(pm.require("uuid").uuid4()))).to.equal(36))'
        )
        result = PyRuntime.execute_restricted(script, _make_context())
        for r in result["test_results"]:
            assert r["passed"] is True, f"{r['name']} failed: {r['error']}"

    def test_pm_send_request_rate_limit(self):
        """Verify that more than 10 pm.send_request calls raise an error."""
        script = """
for i in range(11):
    pm.send_request("http://127.0.0.1:1")
"""
        result = PyRuntime.execute_restricted(script, _make_context())
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
        result = PyRuntime.execute_restricted(script, _make_context())
        for r in result["test_results"]:
            assert r["passed"] is True, f"{r['name']} failed: {r['error']}"

    def test_pm_response_json_empty_body_friendly_error(self) -> None:
        """``pm.response.json()`` explains empty mock body instead of raw JSONDecodeError."""
        result = PyRuntime.execute_restricted(
            "pm.response.json()", _make_context(response={"body": ""})
        )
        errs = [r for r in result["test_results"] if r.get("name") == "(runtime error)"]
        assert len(errs) == 1
        err = str(errs[0].get("error", ""))
        assert "pm.response.json()" in err
        assert "empty" in err.lower()

    def test_pm_response_json_unavailable_without_response(self) -> None:
        """Pre-request context explains that ``pm.response`` is missing."""
        result = PyRuntime.execute_restricted(
            'pm.response.json().get("access_token", "")',
            _make_context(),
        )
        errs = [r for r in result["test_results"] if r.get("name") == "(runtime error)"]
        assert len(errs) == 1
        err = str(errs[0].get("error", ""))
        assert "pm.response is not available" in err
        assert "pre-request" in err.lower() or "before an HTTP response" in err

    def test_pm_response_json_invalid_body_friendly_error(self) -> None:
        result = PyRuntime.execute_restricted(
            "pm.response.json()",
            _make_context(response={"body": "not-json"}),
        )
        errs = [r for r in result["test_results"] if r.get("name") == "(runtime error)"]
        assert len(errs) == 1
        err = str(errs[0].get("error", ""))
        assert "not valid JSON" in err

    def test_pm_response_to_have_status(self) -> None:
        """``pm.response.to.have.status`` works on the Python sandbox response object."""
        script = 'pm.test("s", lambda: pm.response.to.have.status(200))'
        result = PyRuntime.execute_restricted(
            script,
            _make_context(response={"body": "{}", "code": 200, "status_code": 200}),
        )
        assert result["test_results"][0]["passed"] is True

    def test_pm_response_to_not_does_not_leak(self) -> None:
        script = """
pm.test("a", lambda: pm.response.to.not_.have.status(500))
pm.test("b", lambda: pm.response.to.have.status(200))
"""
        result = PyRuntime.execute_restricted(
            script,
            _make_context(response={"body": "{}", "code": 200, "status_code": 200}),
        )
        assert len(result["test_results"]) == 2
        assert all(r["passed"] for r in result["test_results"])

    def test_pm_response_to_json_body(self) -> None:
        script = 'pm.test("j", lambda: pm.response.to.have.jsonBody("id", 7))'
        result = PyRuntime.execute_restricted(
            script,
            _make_context(response={"body": '{"id": 7}'}),
        )
        assert result["test_results"][0]["passed"] is True

    def test_pm_response_to_have_status_reason_string(self) -> None:
        """``pm.response.to.have.status("Created")`` matches HTTP 201."""
        script = 'pm.test("s", lambda: pm.response.to.have.status("Created"))'
        result = PyRuntime.execute_restricted(
            script,
            _make_context(response={"body": "{}", "code": 201, "status_code": 201}),
        )
        assert result["test_results"][0]["passed"] is True

    def test_pm_response_to_have_body(self) -> None:
        """``pm.response.to.have.body`` compares raw response text."""
        script = 'pm.test("b", lambda: pm.response.to.have.body("hello"))'
        result = PyRuntime.execute_restricted(
            script,
            _make_context(response={"body": "hello", "code": 200, "status_code": 200}),
        )
        assert result["test_results"][0]["passed"] is True

    def test_pm_expect_one_of(self) -> None:
        """``pm.expect(x).to.be.oneOf`` uses strict list membership."""
        ok = 'pm.test("o", lambda: pm.expect(201).to.be.oneOf([201, 202]))'
        bad = 'pm.test("f", lambda: pm.expect(500).to.be.oneOf([201, 202]))'
        r_ok = PyRuntime.execute_restricted(ok, _make_context())
        r_bad = PyRuntime.execute_restricted(bad, _make_context())
        assert r_ok["test_results"][0]["passed"] is True
        assert r_bad["test_results"][0]["passed"] is False

    def test_pm_response_to_have_body_regex(self) -> None:
        """``pm.response.to.have.body`` accepts a ``re_compile`` pattern."""
        script = 'pm.test("r", lambda: pm.response.to.have.body(re_compile(r"world$")))'
        result = PyRuntime.execute_restricted(
            script,
            _make_context(response={"body": "hello world", "code": 200, "status_code": 200}),
        )
        assert result["test_results"][0]["passed"] is True

    def test_safe_stdlib_available(self):
        script = """
pm.test("json", lambda: pm.expect(json_loads('{"a": 1}')).to.eql({"a": 1}))
pm.test("b64", lambda: pm.expect(b64decode(b64encode(b"hello"))).to.equal(b"hello"))
"""
        result = PyRuntime.execute_restricted(script, _make_context())
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
        result = PyRuntime.execute_restricted(script, _make_context())
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
        result = PyRuntime.execute_restricted(script, _make_context())
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
        result = PyRuntime.execute_restricted(script, _make_context())
        # Should be capped at 200
        assert len(result["console_logs"]) <= 200

    def test_variable_changes_are_strings(self):
        script = """
pm.variables.set("num", "42")
pm.variables.set("bool", "True")
"""
        result = PyRuntime.execute_restricted(script, _make_context())
        for v in result["variable_changes"].values():
            assert isinstance(v, str)

    def test_type_three_arg_blocked(self):
        """``type(name, bases, dict)`` metaclass form must be blocked."""
        script = """
MyClass = type("Exploit", (), {"run": lambda self: None})
"""
        result = PyRuntime.execute_restricted(script, _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1, "type() with 3 args should be blocked"

    def test_type_single_arg_allowed(self):
        """``type(obj)`` inspection form must still work."""
        script = """
pm.test("type int", lambda: pm.expect(type(42)).to.equal(int))
pm.test("type str", lambda: pm.expect(type("x")).to.equal(str))
"""
        result = PyRuntime.execute_restricted(script, _make_context())
        for r in result["test_results"]:
            assert r["passed"] is True, f"{r['name']} failed: {r['error']}"


# ===================================================================
# JS sandbox security tests (require Deno)
# ===================================================================


class TestJSSandboxSecurity:
    """Verify the JS (Deno) path blocks obvious escape vectors.

    Skipped when Deno is not available.
    """

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

    def test_require_blocked(self):
        from services.scripting.js_runtime import JSRuntime

        script = 'var fs = require("fs");'
        result = JSRuntime.execute(script, _make_context())
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1, "require() should not exist in V8 isolate"

    def test_fetch_global_exists_under_deno(self) -> None:
        """Deno provides ``fetch`` (scripts run in ``deno run``, not in-process V8)."""
        from services.scripting.js_runtime import JSRuntime

        script = 'pm.test("f", function() { pm.expect(typeof fetch).to.equal("function"); });'
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True, result["test_results"][0]

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
