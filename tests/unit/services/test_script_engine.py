"""Tests for the script execution engine, context builder, and Python runtime.

JavaScript tests require **Deno** and are skipped when
``RuntimeSettings.validate_deno`` reports the binary unavailable.
"""

from __future__ import annotations

import pytest

from esprima_test_util import deno_available, deno_and_esprima_available  # type: ignore[import-not-found]

from services.scripting import ScriptEngine, ScriptEntry, ScriptInput
from services.scripting.context import (
    apply_request_mutations,
    apply_variable_changes,
    build_pre_request_context,
    build_test_context,
    mask_sensitive_value,
)
from services.scripting.py_runtime import PyRuntime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    *,
    response: dict | None = None,
    variables: dict | None = None,
) -> ScriptInput:
    """Return a minimal ``ScriptInput`` for testing."""
    return {
        "request": {"url": "https://example.com", "method": "GET", "headers": {}, "body": ""},
        "response": response,
        "variables": variables or {},
        "environment_vars": {},
        "collection_vars": {},
        "info": {"requestName": "test"},
    }


# ===================================================================
# Context builder tests
# ===================================================================


class TestBuildJsContext:
    """Tests for ``js_runtime._build_js_context`` (no Deno required)."""

    def test_maps_code_key_to_status_code(self) -> None:
        """Mock / inline UI uses ``code`` like Postman; JS must see the real status."""
        from services.scripting.js_runtime import _build_js_context

        ctx: ScriptInput = {
            "request": {"url": "https://example.com", "method": "GET", "headers": {}, "body": ""},
            "response": {
                "code": 201,
                "status": "201",
                "headers": [],
                "body": "{}",
                "responseTime": 0,
                "responseSize": 2,
            },
            "variables": {},
            "environment_vars": {},
            "collection_vars": {},
            "info": {},
        }
        js_ctx = _build_js_context(ctx)
        assert js_ctx["response"] is not None
        assert js_ctx["response"]["status_code"] == 201
        assert js_ctx["response"]["response_time"] == 0
        assert js_ctx["response"]["response_size"] == 2


class TestBuildPreRequestContext:
    """Tests for ``build_pre_request_context``."""

    def test_builds_with_none_response(self):
        ctx = build_pre_request_context(
            method="POST",
            url="https://api.example.com/users",
            headers={"Content-Type": "application/json"},
            body='{"name": "test"}',
            variables={"token": "abc"},
            environment_vars={"base_url": "https://api.example.com"},
            collection_vars={},
            info={"requestName": "Create User"},
        )
        assert ctx["response"] is None
        assert ctx["request"]["method"] == "POST"
        assert ctx["variables"]["token"] == "abc"

    def test_does_not_mutate_input_dicts(self):
        original_vars = {"a": "1"}
        ctx = build_pre_request_context(
            method="GET",
            url="https://example.com",
            headers={},
            body="",
            variables=original_vars,
            environment_vars={},
            collection_vars={},
            info={},
        )
        ctx["variables"]["b"] = "2"
        assert "b" not in original_vars


class TestBuildTestContext:
    """Tests for ``build_test_context``."""

    def test_builds_with_response(self):
        ctx = build_test_context(
            request_data={"url": "https://example.com", "method": "GET"},
            response_data={"status_code": 200, "body": "OK"},
            variables={},
            environment_vars={},
            collection_vars={},
            info={},
        )
        assert ctx["response"] is not None
        assert ctx["response"]["status_code"] == 200


class TestApplyRequestMutations:
    """Tests for ``apply_request_mutations``."""

    def test_applies_method_and_url(self):
        m, u, h, b = apply_request_mutations(
            {"method": "POST", "url": "https://new.example.com"},
            method="GET",
            url="https://old.example.com",
            headers={},
            body="",
        )
        assert m == "POST"
        assert u == "https://new.example.com"

    def test_applies_headers_from_dict(self):
        _, _, h, _ = apply_request_mutations(
            {"headers": {"Authorization": "Bearer token"}},
            method="GET",
            url="https://example.com",
            headers={},
            body="",
        )
        assert h == {"Authorization": "Bearer token"}

    def test_applies_headers_from_list(self):
        _, _, h, _ = apply_request_mutations(
            {"headers": [{"key": "X-Custom", "value": "val"}]},
            method="GET",
            url="https://example.com",
            headers={},
            body="",
        )
        assert h == {"X-Custom": "val"}

    def test_ignores_invalid_mutation_types(self):
        m, u, h, b = apply_request_mutations(
            {"method": 123, "url": None},
            method="GET",
            url="https://example.com",
            headers={"Existing": "yes"},
            body="original",
        )
        assert m == "GET"
        assert u == "https://example.com"
        assert h == {"Existing": "yes"}
        assert b == "original"

    def test_returns_original_on_none(self):
        m, u, h, b = apply_request_mutations(
            None,
            method="GET",
            url="https://example.com",
            headers={},
            body="",
        )
        assert m == "GET"


class TestApplyVariableChanges:
    """Tests for ``apply_variable_changes``."""

    def test_merges_changes(self):
        result = apply_variable_changes(
            {"new_var": "value"},
            {"existing": "old"},
        )
        assert result == {"existing": "old", "new_var": "value"}

    def test_does_not_mutate_input(self):
        original = {"a": "1"}
        apply_variable_changes({"b": "2"}, original)
        assert "b" not in original

    def test_converts_to_strings(self):
        result = apply_variable_changes(
            {"num": "42"},
            {},
        )
        assert result == {"num": "42"}


class TestMaskSensitiveValue:
    """Tests for ``mask_sensitive_value``."""

    def test_masks_token(self):
        assert mask_sensitive_value("auth_token", "secret123") == "***masked***"

    def test_masks_password(self):
        assert mask_sensitive_value("password", "pass") == "***masked***"

    def test_masks_api_key(self):
        assert mask_sensitive_value("api_key", "key") == "***masked***"

    def test_does_not_mask_regular_key(self):
        assert mask_sensitive_value("username", "john") == "john"


# ===================================================================
# Python runtime tests
# ===================================================================


class TestPyRuntimeBasic:
    """Basic Python runtime execution tests."""

    def test_simple_test_assertion_pass(self):
        script = """
pm.test("Status check", lambda: pm.expect(200).to.equal(200))
"""
        result = PyRuntime.execute(script, _make_context())
        assert len(result["test_results"]) == 1
        assert result["test_results"][0]["passed"] is True
        assert result["test_results"][0]["name"] == "Status check"

    def test_simple_test_assertion_fail(self):
        script = """
pm.test("Should fail", lambda: pm.expect(200).to.equal(404))
"""
        result = PyRuntime.execute(script, _make_context())
        assert len(result["test_results"]) == 1
        assert result["test_results"][0]["passed"] is False
        assert result["test_results"][0]["error"] is not None

    def test_variable_set_and_get(self):
        script = """
pm.variables.set("my_var", "hello")
pm.test("Var set", lambda: pm.expect(pm.variables.get("my_var")).to.equal("hello"))
"""
        result = PyRuntime.execute(script, _make_context())
        assert result["variable_changes"]["my_var"] == "hello"
        assert result["test_results"][0]["passed"] is True

    def test_console_log_capture(self):
        script = 'print("Hello from script")'
        result = PyRuntime.execute(script, _make_context())
        assert len(result["console_logs"]) == 1
        assert result["console_logs"][0]["message"] == "Hello from script"
        assert result["console_logs"][0]["level"] == "log"

    def test_syntax_error_captured(self):
        script = "def foo(:"
        result = PyRuntime.execute(script, _make_context())
        assert len(result["test_results"]) >= 1
        failed = [r for r in result["test_results"] if not r["passed"]]
        assert len(failed) >= 1

    def test_multiple_tests(self):
        script = """
pm.test("Test 1", lambda: pm.expect(1).to.equal(1))
pm.test("Test 2", lambda: pm.expect(2).to.equal(2))
pm.test("Test 3", lambda: pm.expect(3).to.equal(4))
"""
        result = PyRuntime.execute(script, _make_context())
        assert len(result["test_results"]) == 3
        assert result["test_results"][0]["passed"] is True
        assert result["test_results"][1]["passed"] is True
        assert result["test_results"][2]["passed"] is False


class TestPyRuntimeAssertions:
    """Tests for Chai-like assertion chains in Python runtime."""

    def test_equal(self):
        script = 'pm.test("eq", lambda: pm.expect(42).to.equal(42))'
        result = PyRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_deep_equal(self):
        script = 'pm.test("deep", lambda: pm.expect({"a": 1}).to.deep_equal({"a": 1}))'
        result = PyRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_include_string(self):
        script = 'pm.test("inc", lambda: pm.expect("hello world").to.include("world"))'
        result = PyRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_include_list(self):
        script = 'pm.test("inc", lambda: pm.expect([1, 2, 3]).to.include(2))'
        result = PyRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_type_check(self):
        script = 'pm.test("type", lambda: pm.expect("hello").to.be.a("string"))'
        result = PyRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_above(self):
        script = 'pm.test("above", lambda: pm.expect(10).to.be.above(5))'
        result = PyRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_below(self):
        script = 'pm.test("below", lambda: pm.expect(3).to.be.below(10))'
        result = PyRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_length_of(self):
        script = 'pm.test("len", lambda: pm.expect([1, 2, 3]).to.have.length_of(3))'
        result = PyRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_negation(self):
        script = 'pm.test("not", lambda: pm.expect(42).not_.to.equal(43))'
        result = PyRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True


class TestPyRuntimeResponse:
    """Tests for response access in test context."""

    def test_response_code_access(self):
        ctx = _make_context(response={"status_code": 200, "status": "OK", "body": '{"id": 1}'})
        script = 'pm.test("status", lambda: pm.expect(pm.response.code).to.equal(200))'
        result = PyRuntime.execute(script, ctx)
        assert result["test_results"][0]["passed"] is True

    def test_response_json(self):
        ctx = _make_context(response={"status_code": 200, "body": '{"name": "test"}'})
        script = """
def check():
    data = pm.response.json()
    pm.expect(data["name"]).to.equal("test")
pm.test("json", check)
"""
        result = PyRuntime.execute(script, ctx)
        assert result["test_results"][0]["passed"] is True

    def test_response_text(self):
        ctx = _make_context(response={"status_code": 200, "body": "plain text"})
        script = 'pm.test("text", lambda: pm.expect(pm.response.text()).to.include("plain"))'
        result = PyRuntime.execute(script, ctx)
        assert result["test_results"][0]["passed"] is True


class TestPyRuntimeCookies:
    """Tests for ``pm.cookies`` parsed from response Set-Cookie headers."""

    def test_cookie_get_from_list_headers(self):
        ctx = _make_context(
            response={
                "status_code": 200,
                "body": "",
                "headers": [
                    {"key": "Set-Cookie", "value": "sid=abc123; Path=/; HttpOnly"},
                    {"key": "Set-Cookie", "value": "lang=en; Max-Age=3600"},
                ],
            },
        )
        script = """
pm.test("sid", lambda: pm.expect(pm.cookies.get("sid")).to.equal("abc123"))
pm.test("lang", lambda: pm.expect(pm.cookies.get("lang")).to.equal("en"))
pm.test("missing", lambda: pm.expect(pm.cookies.get("nope")).to.be.none)
"""
        result = PyRuntime.execute(script, ctx)
        assert all(r["passed"] for r in result["test_results"]), result["test_results"]

    def test_cookie_get_from_dict_headers(self):
        ctx = _make_context(
            response={
                "status_code": 200,
                "body": "",
                "headers": {"set-cookie": "token=xyz; Secure"},
            },
        )
        script = 'pm.test("tok", lambda: pm.expect(pm.cookies.get("token")).to.equal("xyz"))'
        result = PyRuntime.execute(script, ctx)
        assert result["test_results"][0]["passed"] is True

    def test_cookie_get_all(self):
        ctx = _make_context(
            response={
                "status_code": 200,
                "body": "",
                "headers": [
                    {"key": "Set-Cookie", "value": "a=1"},
                    {"key": "Set-Cookie", "value": "b=2"},
                ],
            },
        )
        script = """
cookies = pm.cookies.get_all()
pm.test("count", lambda: pm.expect(len(cookies)).to.equal(2))
"""
        result = PyRuntime.execute(script, ctx)
        assert result["test_results"][0]["passed"] is True

    def test_cookies_empty_without_response(self):
        ctx = _make_context()  # No response
        script = 'pm.test("empty", lambda: pm.expect(pm.cookies.get("x")).to.be.none)'
        result = PyRuntime.execute(script, ctx)
        assert result["test_results"][0]["passed"] is True


class TestPyRuntimePreRequest:
    """Tests for request mutation in pre-request context."""

    def test_request_mutation_captured(self):
        ctx = _make_context()  # no response = pre-request
        script = """
pm.request.url = "https://mutated.example.com"
pm.request.method = "POST"
"""
        result = PyRuntime.execute(script, ctx)
        assert result["request_mutations"] is not None
        assert result["request_mutations"]["url"] == "https://mutated.example.com"
        assert result["request_mutations"]["method"] == "POST"

    def test_no_mutations_in_test_context(self):
        ctx = _make_context(response={"status_code": 200, "body": ""})
        script = 'pm.request.url = "should be ignored"'
        result = PyRuntime.execute(script, ctx)
        # In test context, request_mutations should be None
        assert result["request_mutations"] is None


# ===================================================================
# Engine tests
# ===================================================================


class TestScriptEngine:
    """Tests for the ScriptEngine orchestrator."""

    def test_run_single_empty_script(self):
        result = ScriptEngine.run_single("", "python", _make_context())
        assert result["test_results"] == []
        assert result["console_logs"] == []

    def test_run_single_python(self):
        result = ScriptEngine.run_single(
            'pm.test("ok", lambda: pm.expect(1).to.equal(1))',
            "python",
            _make_context(),
        )
        assert len(result["test_results"]) == 1
        assert result["test_results"][0]["passed"] is True

    @pytest.mark.skipif(
        not deno_available(),
        reason="Deno required for TypeScript execution",
    )
    def test_run_single_typescript(self):
        """TypeScript runs on the Deno path with type stripping."""
        result = ScriptEngine.run_single(
            "const x: number = 1; pm.test('ok', () => pm.expect(x).to.equal(1));",
            "typescript",
            _make_context(
                response={
                    "status_code": 200,
                    "body": "",
                    "headers": {},
                },
            ),
        )
        assert len(result["test_results"]) == 1
        assert result["test_results"][0]["passed"] is True

    def test_run_chain_merges_results(self):
        chain: list[ScriptEntry] = [
            {
                "code": 'pm.test("first", lambda: pm.expect(1).to.equal(1))',
                "language": "python",
                "source_name": "collection",
            },
            {
                "code": 'pm.test("second", lambda: pm.expect(2).to.equal(2))',
                "language": "python",
                "source_name": "request",
            },
        ]
        result = ScriptEngine.run_pre_request_scripts(chain, _make_context())
        assert len(result["test_results"]) == 2
        assert all(r["passed"] for r in result["test_results"])

    def test_chain_propagates_variables(self):
        chain: list[ScriptEntry] = [
            {
                "code": 'pm.variables.set("from_first", "hello")',
                "language": "python",
                "source_name": "collection",
            },
            {
                "code": 'pm.test("check", lambda: pm.expect(pm.variables.get("from_first")).to.equal("hello"))',
                "language": "python",
                "source_name": "request",
            },
        ]
        result = ScriptEngine.run_pre_request_scripts(chain, _make_context())
        assert result["variable_changes"]["from_first"] == "hello"
        # Second script's test should pass because variable was propagated
        check_result = [r for r in result["test_results"] if r["name"] == "check"]
        assert len(check_result) == 1
        assert check_result[0]["passed"] is True

    def test_chain_skips_empty_scripts(self):
        chain: list[ScriptEntry] = [
            {"code": "", "language": "python", "source_name": "empty"},
            {
                "code": 'pm.test("ok", lambda: pm.expect(True).to.be.true)',
                "language": "python",
                "source_name": "request",
            },
        ]
        result = ScriptEngine.run_test_scripts(chain, _make_context())
        assert len(result["test_results"]) == 1

    def test_chain_tags_runtime_errors_with_source(self):
        """Runtime errors should include the source_name of the failing script."""
        chain: list[ScriptEntry] = [
            {
                "code": "const x =n",  # intentionally broken
                "language": "javascript",
                "source_name": "Hyperguest",
            },
        ]
        result = ScriptEngine.run_pre_request_scripts(chain, _make_context())
        errs = [r for r in result["test_results"] if r.get("name") == "(runtime error)"]
        assert len(errs) == 1
        assert errs[0]["source_name"] == "Hyperguest"


class TestFindPmTests:
    """Tests for :func:`services.scripting.engine.find_pm_tests`."""

    def test_find_python_pm_test_calls(self) -> None:
        """AST path lists each ``pm.test("name", ...)`` with 1-based lines."""
        from services.scripting.engine import find_pm_tests

        src = 'pm.test("a", lambda: None)\n\npm.test("b", lambda: None)\n'
        out = find_pm_tests(src, "python")
        assert [x["name"] for x in out] == ["a", "b"]
        assert [x["line"] for x in out] == [1, 3]

    def test_find_javascript_pm_test_regex_fallback(self) -> None:
        """JavaScript path finds tests (regex when parse is unavailable)."""
        from services.scripting.engine import find_pm_tests

        src = "pm.test('x', function() { pm.expect(1).to.equal(1); });"
        out = find_pm_tests(src, "javascript")
        assert any(t.get("name") == "x" for t in out)


class TestFindTopLevelStatementLines:
    """Tests for :func:`services.scripting.engine.find_top_level_statement_lines`."""

    def test_python_includes_nested_statement_lines(self) -> None:
        """Recursive walk: nested statements (function bodies, ``try`` bodies)
        are reachable too — both runtimes pause inside callbacks."""
        from services.scripting.engine import find_top_level_statement_lines

        src = "a = 1\ndef f():\n    x = 2\n"
        lines = find_top_level_statement_lines(src, "python")
        assert lines == {0, 1, 2}

    def test_python_breakpoints_inside_try_render_reachable(self) -> None:
        """Regression: ``try``-wrapped script must not mute every body line."""
        from services.scripting.engine import find_top_level_statement_lines

        src = "try:\n    x = 1\n    y = 2\nexcept Exception as e:\n    print(e)\n"
        lines = find_top_level_statement_lines(src, "python")
        # ``try``, both body assigns, ``except`` header, and the print body.
        assert {0, 1, 2, 3, 4} <= lines

    @pytest.mark.skipif(
        not deno_and_esprima_available(),
        reason="Deno + Esprima required for JS top-level line scan",
    )
    def test_javascript_includes_callback_statement_lines(self) -> None:
        """Esprima walk: statements inside ``pm.test`` callbacks are reachable."""
        from services.scripting.engine import find_top_level_statement_lines

        src = "pm.test('x', function() {\n  var y = 1;\n});\n"
        lines = find_top_level_statement_lines(src, "javascript")
        assert {0, 1} <= lines

    def test_unsupported_or_empty_returns_empty(self) -> None:
        from services.scripting.engine import find_top_level_statement_lines

        assert find_top_level_statement_lines("", "javascript") == set()
        assert find_top_level_statement_lines(" ", "rust") == set()


# ===================================================================
# JS runtime tests (require Deno for DenoRuntime / JSRuntime.execute)
# ===================================================================


class TestJSRuntime:
    """Tests for the JavaScript runtime (Deno subprocess via ``JSRuntime``).

    Skipped when Deno is not available.
    """

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

    def test_simple_test_pass(self):
        from services.scripting.js_runtime import JSRuntime

        script = 'pm.test("Status is 200", function() { pm.expect(200).to.equal(200); });'
        result = JSRuntime.execute(script, _make_context())
        assert len(result["test_results"]) == 1
        assert result["test_results"][0]["passed"] is True

    def test_simple_test_fail(self):
        from services.scripting.js_runtime import JSRuntime

        script = 'pm.test("Should fail", function() { pm.expect(200).to.equal(404); });'
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is False

    def test_variable_set(self):
        from services.scripting.js_runtime import JSRuntime

        script = 'pm.variables.set("key", "value");'
        result = JSRuntime.execute(script, _make_context())
        assert result["variable_changes"]["key"] == "value"

    def test_console_log(self):
        from services.scripting.js_runtime import JSRuntime

        script = 'console.log("hello");'
        result = JSRuntime.execute(script, _make_context())
        assert len(result["console_logs"]) >= 1
        assert result["console_logs"][0]["message"] == "hello"

    def test_console_log_without_trailing_semicolon(self):
        """Omitting ``;`` on the last line must not let ASI join the drain IIFE."""
        from services.scripting.js_runtime import JSRuntime

        result = JSRuntime.execute("console.log('asi-ok')", _make_context())
        assert not any(t.get("name") == "(runtime error)" for t in result.get("test_results", []))
        assert any("asi-ok" in (e.get("message", "") or "") for e in result.get("console_logs", []))

    def test_cookies_parsed_from_response(self):
        from services.scripting.js_runtime import JSRuntime

        ctx = _make_context(
            response={
                "status_code": 200,
                "body": "",
                "headers": [
                    {"key": "Set-Cookie", "value": "sid=abc; Path=/"},
                    {"key": "Set-Cookie", "value": "lang=en"},
                ],
            },
        )
        script = """
pm.test("sid", function() { pm.expect(pm.cookies.get("sid")).to.equal("abc"); });
pm.test("lang", function() { pm.expect(pm.cookies.get("lang")).to.equal("en"); });
pm.test("missing", function() { pm.expect(pm.cookies.get("nope")).to.be.undefined; });
"""
        result = JSRuntime.execute(script, ctx)
        assert all(r["passed"] for r in result["test_results"]), result["test_results"]

    def test_cookies_get_all(self):
        from services.scripting.js_runtime import JSRuntime

        ctx = _make_context(
            response={
                "status_code": 200,
                "body": "",
                "headers": [
                    {"key": "Set-Cookie", "value": "a=1"},
                    {"key": "Set-Cookie", "value": "b=2"},
                ],
            },
        )
        script = """
var all = pm.cookies.getAll();
pm.test("count", function() { pm.expect(all.length).to.equal(2); });
"""
        result = JSRuntime.execute(script, ctx)
        assert result["test_results"][0]["passed"] is True

    def test_pm_response_to_have_status_passes(self) -> None:
        from services.scripting.js_runtime import JSRuntime

        ctx = _make_context(
            response={"status_code": 200, "body": "{}", "headers": []},
        )
        script = 'pm.test("s", function() { pm.response.to.have.status(200); });'
        result = JSRuntime.execute(script, ctx)
        assert result["test_results"][0]["passed"] is True

    def test_pm_response_to_have_status_fails(self) -> None:
        from services.scripting.js_runtime import JSRuntime

        ctx = _make_context(
            response={"status_code": 200, "body": "{}", "headers": []},
        )
        script = 'pm.test("s", function() { pm.response.to.have.status(404); });'
        result = JSRuntime.execute(script, ctx)
        assert result["test_results"][0]["passed"] is False

    def test_pm_response_to_not_does_not_leak_negation(self) -> None:
        """``to`` returns a fresh ``__Expectation`` so ``.not`` does not affect the next chain."""
        from services.scripting.js_runtime import JSRuntime

        ctx = _make_context(
            response={"status_code": 200, "body": "{}", "headers": []},
        )
        script = """
pm.test("a", function() { pm.response.to.not.have.status(500); });
pm.test("b", function() { pm.response.to.have.status(200); });
"""
        result = JSRuntime.execute(script, ctx)
        assert len(result["test_results"]) == 2
        assert all(r["passed"] for r in result["test_results"])

    def test_pm_response_to_have_header(self) -> None:
        from services.scripting.js_runtime import JSRuntime

        ctx = _make_context(
            response={
                "status_code": 200,
                "body": "{}",
                "headers": [
                    {"key": "Content-Type", "value": "application/json"},
                ],
            },
        )
        script = """
pm.test("h", function() {
    pm.response.to.have.header("Content-Type", "application/json");
});
"""
        result = JSRuntime.execute(script, ctx)
        assert result["test_results"][0]["passed"] is True

    def test_pm_response_to_have_json_body(self) -> None:
        from services.scripting.js_runtime import JSRuntime

        ctx = _make_context(
            response={"status_code": 200, "body": '{"id": 7, "a": {"b": 1}}', "headers": []},
        )
        script = """
pm.test("id", function() { pm.response.to.have.jsonBody("id", 7); });
pm.test("path", function() { pm.response.to.have.jsonBody("a.b", 1); });
"""
        result = JSRuntime.execute(script, ctx)
        assert len(result["test_results"]) == 2
        assert all(r["passed"] for r in result["test_results"])

    def test_pm_response_to_have_status_reason_string_js(self) -> None:
        """``pm.response.to.have.status("Created")`` matches HTTP 201 in JS."""
        from services.scripting.js_runtime import JSRuntime

        ctx = _make_context(
            response={"status_code": 201, "body": "{}", "headers": []},
        )
        script = 'pm.test("s", function() { pm.response.to.have.status("Created"); });'
        result = JSRuntime.execute(script, ctx)
        assert result["test_results"][0]["passed"] is True

    def test_pm_response_to_have_body_js(self) -> None:
        """``pm.response.to.have.body`` compares response text in JS."""
        from services.scripting.js_runtime import JSRuntime

        ctx = _make_context(
            response={"status_code": 200, "body": "hello", "headers": []},
        )
        script = 'pm.test("b", function() { pm.response.to.have.body("hello"); });'
        result = JSRuntime.execute(script, ctx)
        assert result["test_results"][0]["passed"] is True

    def test_pm_expect_one_of_js(self) -> None:
        """``pm.expect(x).to.be.oneOf`` uses strict ``===`` membership in JS."""
        from services.scripting.js_runtime import JSRuntime

        ctx = _make_context(
            response={"status_code": 200, "body": "{}", "headers": []},
        )
        ok = 'pm.test("o", function() { pm.expect(201).to.be.oneOf([201, 202]); });'
        bad = 'pm.test("f", function() { pm.expect(500).to.be.oneOf([201, 202]); });'
        assert JSRuntime.execute(ok, ctx)["test_results"][0]["passed"] is True
        assert JSRuntime.execute(bad, ctx)["test_results"][0]["passed"] is False

    def test_pm_response_to_have_body_regex_js(self) -> None:
        """``pm.response.to.have.body`` accepts a ``RegExp`` in JS."""
        from services.scripting.js_runtime import JSRuntime

        ctx = _make_context(
            response={"status_code": 200, "body": "hello world", "headers": []},
        )
        ok = 'pm.test("r", function() { pm.response.to.have.body(/world$/); });'
        bad = 'pm.test("f", function() { pm.response.to.have.body(/^nope/); });'
        assert JSRuntime.execute(ok, ctx)["test_results"][0]["passed"] is True
        assert JSRuntime.execute(bad, ctx)["test_results"][0]["passed"] is False
