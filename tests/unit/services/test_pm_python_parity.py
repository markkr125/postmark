"""Postman API parity tests for the Python sandbox (`_py_sandbox.py`).

Covers the Phases 2–10 Python work:
- HeaderList shape on pm.request.headers / pm.response.headers
- _PmUrl wrapper on pm.request.url + .query.add(...)
- Request body discriminated union (mode/raw/urlencoded/formdata)
- Response originalRequest / cookies / reason() / mime() / dataURI() / size()
- Resolved pm.variables (read-through across scopes)
- pm.test.skip(name, fn) + inline ctx.skip()
- pm.execution.location.current
- pm.cookies.jar() shape
- Legacy globals (responseBody, responseCode, responseHeaders, tests, xml2Json)
- pm.visualizer.set throws documented error
- camelCase aliases (pm.collectionVariables, pm.iterationData, pm.sendRequest, ...)
"""

from __future__ import annotations

from typing import Any

from services.scripting import ScriptInput
from services.scripting.py_runtime import PyRuntime


def _ctx(response: dict | None = None, **extra: Any) -> ScriptInput:
    base: dict[str, Any] = {
        "request": {
            "url": "https://example.com/path?q=1&q=2",
            "method": "POST",
            "headers": {"Content-Type": "application/json", "X-Trace": "abc"},
            "body": '{"hello":"world"}',
        },
        "response": response,
        "variables": {},
        "environment_vars": {},
        "collection_vars": {},
        "info": {},
    }
    base.update(extra)
    return base  # type: ignore[return-value]


def _passed(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in result["test_results"] if r["passed"]]


def _failed(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in result["test_results"] if not r["passed"]]


# ---------- Phase 2: HeaderList + Url ----------


def test_request_headers_case_insensitive_get() -> None:
    src = """
def t_fn():
    pm.expect(pm.request.headers.get("content-type")).to.eql("application/json")
    pm.expect(pm.request.headers.has("X-TRACE")).to.be.true
    pm.expect(pm.request.headers.toObject()["Content-Type"]).to.eql("application/json")
pm.test("headers", t_fn)
"""
    result = PyRuntime.execute_restricted(src, _ctx())
    assert not _failed(result), result["test_results"]


def test_request_headers_each_iterates_in_order() -> None:
    src = """
def t_fn():
    seen = []
    pm.request.headers.each(lambda h: seen.append(h["key"]))
    pm.expect(seen).to.eql(["Content-Type", "X-Trace"])
pm.test("each", t_fn)
"""
    result = PyRuntime.execute_restricted(src, _ctx())
    assert not _failed(result), result["test_results"]


def test_request_headers_mutation_in_pre_request() -> None:
    src = """
pm.request.headers.upsert({"key": "Authorization", "value": "Bearer t"})
def t_fn():
    pm.expect(pm.request.headers.get("Authorization")).to.eql("Bearer t")
pm.test("upsert", t_fn)
"""
    result = PyRuntime.execute_restricted(src, _ctx())
    assert not _failed(result), result["test_results"]


def test_response_headers_immutable_raises() -> None:
    src = """
def t_fn():
    raised = False
    try:
        pm.response.headers.add({"key": "X", "value": "y"})
    except Exception:
        raised = True
    pm.expect(raised).to.be.true
pm.test("immutable", t_fn)
"""
    result = PyRuntime.execute_restricted(src, _ctx({"code": 200, "headers": {}, "body": ""}))
    assert not _failed(result), result["test_results"]


def test_request_url_components() -> None:
    src = """
def t_fn():
    u = pm.request.url
    pm.expect(u.getHost()).to.eql("example.com")
    pm.expect(u.getPath()).to.eql("/path")
    pm.expect(u.getQueryString()).to.eql("q=1&q=2")
    pm.expect(u.protocol).to.eql("https")
    pm.expect(u.toString()).to.include("example.com")
pm.test("url", t_fn)
"""
    result = PyRuntime.execute_restricted(src, _ctx())
    assert not _failed(result), result["test_results"]


def test_request_url_query_add() -> None:
    src = """
def t_fn():
    pm.request.url.query.add({"key": "page", "value": "2"})
    pm.expect(pm.request.url.query.get("page")).to.eql("2")
pm.test("query.add", t_fn)
"""
    result = PyRuntime.execute_restricted(src, _ctx())
    assert not _failed(result), result["test_results"]


# ---------- Phase 3: response enhancements ----------


def test_response_reason_mime_size_datauri() -> None:
    src = """
def t_fn():
    pm.expect(pm.response.reason()).to.eql("Created")
    m = pm.response.mime()
    pm.expect(m["type"]).to.eql("application/json")
    pm.expect(m["charset"]).to.eql("utf-8")
    pm.expect(pm.response.size()).to.eql(13)
    pm.expect(pm.response.dataURI()).to.include(";base64,")
pm.test("response helpers", t_fn)
"""
    resp = {
        "code": 201,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": '{"ok":true}xx',
    }
    result = PyRuntime.execute_restricted(src, _ctx(resp))
    assert not _failed(result), result["test_results"]


def test_response_original_request_present() -> None:
    src = """
def t_fn():
    orig = pm.response.originalRequest
    pm.expect(orig is not None).to.be.true
    pm.expect(orig.method).to.eql("POST")
pm.test("originalRequest", t_fn)
"""
    resp = {"code": 200, "headers": {}, "body": ""}
    result = PyRuntime.execute_restricted(src, _ctx(resp))
    assert not _failed(result), result["test_results"]


def test_response_cookies_via_response_accessor() -> None:
    src = """
def t_fn():
    pm.expect(pm.response.cookies.get("token")).to.eql("abc")
pm.test("cookies", t_fn)
"""
    resp = {
        "code": 200,
        "headers": [{"key": "Set-Cookie", "value": "token=abc; Path=/"}],
        "body": "",
    }
    result = PyRuntime.execute_restricted(src, _ctx(resp))
    assert not _failed(result), result["test_results"]


# ---------- Phase 4: request body discriminated union ----------


def test_request_body_mode_raw() -> None:
    src = """
def t_fn():
    pm.expect(pm.request.body.mode).to.eql("raw")
    pm.expect(pm.request.body.raw).to.include("hello")
pm.test("body raw", t_fn)
"""
    result = PyRuntime.execute_restricted(src, _ctx())
    assert not _failed(result), result["test_results"]


def test_request_body_mode_urlencoded() -> None:
    src = """
def t_fn():
    pm.expect(pm.request.body.mode).to.eql("urlencoded")
    pm.expect(pm.request.body.urlencoded.get("k")).to.eql("v")
pm.test("body urlencoded", t_fn)
"""
    ctx = _ctx()
    ctx["request"]["body"] = {  # type: ignore[index]
        "mode": "urlencoded",
        "urlencoded": [{"key": "k", "value": "v"}],
    }
    result = PyRuntime.execute_restricted(src, ctx)
    assert not _failed(result), result["test_results"]


# ---------- Phase 5: resolved variables + camelCase aliases ----------


def test_pm_variables_reads_environment_through() -> None:
    src = """
def t_fn():
    pm.expect(pm.variables.get("base")).to.eql("https://api.example.com")
pm.test("resolved", t_fn)
"""
    ctx = _ctx()
    ctx["environment_vars"] = {"base": "https://api.example.com"}  # type: ignore[index]
    result = PyRuntime.execute_restricted(src, ctx)
    assert not _failed(result), result["test_results"]


def test_pm_variables_local_set_hides_environment() -> None:
    src = """
pm.variables.set("k", "local")
def t_fn():
    pm.expect(pm.variables.get("k")).to.eql("local")
pm.test("local wins", t_fn)
"""
    ctx = _ctx()
    ctx["environment_vars"] = {"k": "env"}  # type: ignore[index]
    result = PyRuntime.execute_restricted(src, ctx)
    assert not _failed(result), result["test_results"]


def test_collection_variables_camelcase_alias() -> None:
    src = """
pm.collectionVariables.set("k", "v")
def t_fn():
    pm.expect(pm.collectionVariables.get("k")).to.eql("v")
    pm.expect(pm.collection_variables.get("k")).to.eql("v")
pm.test("camel alias", t_fn)
"""
    result = PyRuntime.execute_restricted(src, _ctx())
    assert not _failed(result), result["test_results"]


def test_pm_iteration_data_camelcase_alias() -> None:
    src = """
def t_fn():
    pm.expect(pm.iterationData.get("name")).to.eql("alice")
pm.test("iterationData", t_fn)
"""
    ctx = _ctx()
    ctx["iteration_data"] = {"name": "alice"}  # type: ignore[index]
    result = PyRuntime.execute_restricted(src, ctx)
    assert not _failed(result), result["test_results"]


def test_environment_clear_empties_scope() -> None:
    src = """
pm.environment.clear()
def t_fn():
    pm.expect(pm.environment.get("k") is None).to.be.true
pm.test("clear", t_fn)
"""
    ctx = _ctx()
    ctx["environment_vars"] = {"k": "v"}  # type: ignore[index]
    result = PyRuntime.execute_restricted(src, ctx)
    assert not _failed(result), result["test_results"]


# ---------- Phase 6: pm.test.skip + execution.location ----------


def test_pm_test_skip_records_skipped_result() -> None:
    src = """
pm.test.skip("manual skip", lambda: None)
"""
    result = PyRuntime.execute_restricted(src, _ctx())
    assert result["test_results"] == [
        {
            "name": "manual skip",
            "passed": True,
            "skipped": True,
            "error": None,
            "duration_ms": 0.0,
        }
    ]


def test_pm_execution_location_current() -> None:
    src = """
def t_fn():
    pm.expect(pm.execution.location.current).to.eql("Collection / Folder / Req")
pm.test("location", t_fn)
"""
    ctx = _ctx()
    ctx["execution_location"] = {"current": "Collection / Folder / Req"}  # type: ignore[index]
    result = PyRuntime.execute_restricted(src, ctx)
    assert not _failed(result), result["test_results"]


# ---------- Phase 7: jsonBody bracket paths ----------


def test_json_body_bracket_path() -> None:
    src = """
def t_fn():
    pm.expect(pm.response).to.have.jsonBody("items[1].name", "b")
pm.test("bracket path", t_fn)
"""
    resp = {
        "code": 200,
        "headers": {},
        "body": '{"items":[{"name":"a"},{"name":"b"}]}',
    }
    result = PyRuntime.execute_restricted(src, _ctx(resp))
    assert not _failed(result), result["test_results"]


# ---------- Phase 9: pm.cookies.jar() ----------


def test_pm_cookies_jar_get_all_returns_known_cookies() -> None:
    src = """
def t_fn():
    jar = pm.cookies.jar()
    cookies = jar.getAll("https://example.com")
    pm.expect(cookies[0]["name"]).to.eql("token")
pm.test("jar.getAll", t_fn)
"""
    resp = {
        "code": 200,
        "headers": [{"key": "Set-Cookie", "value": "token=abc"}],
        "body": "",
    }
    result = PyRuntime.execute_restricted(src, _ctx(resp))
    assert not _failed(result), result["test_results"]


def test_pm_cookies_jar_set_raises() -> None:
    src = """
def t_fn():
    raised = False
    try:
        pm.cookies.jar().set("https://example.com", "k", "v")
    except Exception:
        raised = True
    pm.expect(raised).to.be.true
pm.test("jar.set raises", t_fn)
"""
    result = PyRuntime.execute_restricted(src, _ctx())
    assert not _failed(result), result["test_results"]


# ---------- Phase 10: legacy globals + visualizer stub ----------


def test_legacy_response_globals_present() -> None:
    src = """
def t_fn():
    pm.expect(responseBody).to.eql("hello")
    pm.expect(responseCode["code"]).to.eql(200)
    pm.expect(responseCode["name"]).to.eql("OK")
    pm.expect(responseHeaders["Content-Type"]).to.eql("text/plain")
pm.test("legacy globals", t_fn)
"""
    resp = {"code": 200, "headers": {"Content-Type": "text/plain"}, "body": "hello"}
    result = PyRuntime.execute_restricted(src, _ctx(resp))
    assert not _failed(result), result["test_results"]


def test_xml2_json_global_parses() -> None:
    src = """
def t_fn():
    obj = xml2Json("<root><a>1</a><b>2</b></root>")
    pm.expect(obj["root"]["a"]).to.eql("1")
pm.test("xml2Json", t_fn)
"""
    result = PyRuntime.execute_restricted(src, _ctx())
    assert not _failed(result), result["test_results"]


def test_pm_visualizer_set_raises_documented_error() -> None:
    src = """
def t_fn():
    raised = False
    try:
        pm.visualizer.set("<h1>x</h1>", {})
    except Exception as err:
        raised = "not supported in postmark" in str(err)
    pm.expect(raised).to.be.true
pm.test("visualizer", t_fn)
"""
    result = PyRuntime.execute_restricted(src, _ctx())
    assert not _failed(result), result["test_results"]


# ---------- Wrapped-type ``__repr__`` for ``print(...)`` ergonomics ----------


def test_pm_response_repr_is_user_friendly() -> None:
    """``print(response)`` must not surface ``<_PmResponse object at 0x…>``."""
    from services.scripting._py_sandbox import _PmResponse

    r = _PmResponse(
        {"code": 201, "status": "Created", "body": '{"id":42}', "headers": {}},
        original_request=None,
    )
    text = repr(r)
    assert "<PmResponse" in text
    assert "code=201" in text
    assert "id" in text and "42" in text
    assert "object at 0x" not in text
    assert str(r) == text


def test_pm_response_repr_truncates_long_body() -> None:
    from services.scripting._py_sandbox import _PmResponse

    body = "x" * 500
    r = _PmResponse({"code": 200, "status": "OK", "body": body, "headers": {}})
    text = repr(r)
    assert text.endswith("…'>")
    assert len(text) < 200


def test_pm_request_repr_shows_method_and_url() -> None:
    from services.scripting._py_sandbox import _PmRequest

    r = _PmRequest(
        {"method": "POST", "url": "https://api/x", "headers": {}, "body": "{}"},
    )
    text = repr(r)
    assert "<PmRequest POST" in text
    assert "https://api/x" in text
    assert "object at 0x" not in text


def test_header_list_repr_shows_items() -> None:
    from services.scripting._py_sandbox import _HeaderList

    h = _HeaderList({"X-Foo": "1", "X-Bar": "2"}, mutable=False)
    text = repr(h)
    assert "HeaderList" in text
    assert "X-Foo" in text
    assert "X-Bar" in text
    assert "object at 0x" not in text


def test_pm_response_body_is_public_attribute() -> None:
    """``response.body`` mirrors JS ``pm.response.body`` (public string)."""
    from services.scripting._py_sandbox import _PmResponse

    r = _PmResponse({"code": 200, "status": "OK", "body": '{"x":1}', "headers": {}})
    assert r.body == '{"x":1}'


def test_pm_response_is_dict_subclass_for_isinstance_check() -> None:
    """Postman scripts ported to Python often gate on ``isinstance(response, dict)``;
    the wrapped response must satisfy it so ``response.get(...)`` is reached.
    """
    from services.scripting._py_sandbox import _PmResponse

    r = _PmResponse({"code": 201, "status": "Created", "body": "ok", "headers": {}})
    assert isinstance(r, dict)
    assert r.get("body", "") == "ok"
    assert r.get("code") == 201
    assert r.get("missing", "fallback") == "fallback"
    assert r["status"] == "Created"
    assert "body" in r
    assert "missing" not in r


def test_pm_response_repr_when_printed_from_user_script() -> None:
    """End-to-end: ``print(pm.response)`` lands as a console log with the friendly repr."""
    src = """
print(pm.response)
pm.test('printed', lambda: None)
"""
    result = PyRuntime.execute_restricted(
        src, _ctx({"code": 200, "status": "OK", "body": '{"ok":true}', "headers": {}})
    )
    logs = [log["message"] for log in result.get("console_logs", [])]
    assert any("PmResponse" in log and "code=200" in log for log in logs), logs
