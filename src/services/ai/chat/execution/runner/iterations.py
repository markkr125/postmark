"""Agent data-driven script iterations (request test phase)."""

from __future__ import annotations

from typing import Any

from services.ai.chat.execution.agent_send import (
    AgentSendResult,
    _fail,
    _headers_text,
    _test_language,
)
from services.ai.chat.execution.send_core import _persist_global_changes
from services.assertion_service import AssertionService
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.http.header_utils import parse_header_dict
from services.script_service import ScriptService
from services.scripting.context import build_script_info, build_test_context, load_globals
from services.scripting.engine import ScriptEngine


def run_agent_iterations(
    *,
    request_id: int,
    iteration_data: list[dict[str, Any]],
    iteration_count: int | None = None,
    environment_id: int | None = None,
    persist_globals: bool = False,
    mock_response: dict[str, Any] | None = None,
) -> AgentSendResult:
    """Run request test scripts once per iteration row (mock response default)."""
    if not iteration_data:
        return _fail("iteration_data_required", "Provide a non-empty iteration_data list")

    req = CollectionService.get_request(request_id)
    if req is None:
        return _fail("request_not_found", f"No request with id={request_id}")

    _pre, test_scripts = ScriptService.build_script_chain(request_id)
    declarative = AssertionService.build_declarative_script_entry(
        request_id,
        _test_language(test_scripts),
    )
    if not test_scripts and not declarative:
        return _fail("no_test_scripts", "Request has no test scripts or assertions")

    variables = EnvironmentService.build_combined_variable_map(environment_id, request_id)
    env_name = ""
    if environment_id is not None:
        env = EnvironmentService.get_environment(environment_id)
        if env is not None:
            env_name = str(env.name or "")

    method = str(req.method or "GET")
    url = str(req.url or "")
    headers_text = _headers_text(req.headers)
    body = str(req.body) if req.body is not None else ""
    header_dict = parse_header_dict(headers_text) if headers_text else {}
    request_name = str(req.name or "")
    global_vars = load_globals()
    resp = (
        dict(mock_response)
        if mock_response
        else {
            "code": 200,
            "status": "200",
            "headers": [],
            "body": "",
            "responseTime": 0,
            "responseSize": 0,
            "status_code": 200,
            "elapsed_ms": 0,
        }
    )

    rows = list(iteration_data)
    total = max(1, iteration_count if iteration_count is not None else len(rows))
    total = max(total, len(rows))
    per_iteration: list[dict[str, Any]] = []
    all_tests: list[Any] = []
    all_console: list[Any] = []

    for idx in range(total):
        row = rows[idx] if idx < len(rows) else {}
        row_vars = {str(k): str(v) for k, v in row.items()}
        scope = {**variables, **row_vars}
        info = build_script_info(
            event_name="test",
            request_name=request_name,
            request_id=str(request_id),
            iteration=idx,
            iteration_count=total,
        )
        ctx = build_test_context(
            request_data={
                "url": EnvironmentService.substitute(url, scope),
                "method": method,
                "headers": header_dict,
                "body": body,
            },
            response_data=resp,
            variables=scope,
            environment_vars={},
            collection_vars={},
            global_vars=global_vars,
            info=info,
            iteration_data=row or None,
            environment_name=env_name,
        )
        iter_tests: list[Any] = []
        iter_console: list[Any] = []
        if test_scripts:
            script_out = ScriptEngine.run_test_scripts(test_scripts, ctx)
            iter_tests.extend(script_out.get("test_results") or [])
            iter_console.extend(script_out.get("console_logs") or [])
            changes = script_out.get("global_variable_changes")
            if changes and persist_globals:
                _persist_global_changes(changes, persist_globals=True, global_vars=global_vars)
        if declarative:
            decl_out = ScriptEngine.run_single(
                declarative.get("code", ""),
                declarative.get("language", "javascript"),
                ctx,
            )
            iter_tests.extend(decl_out.get("test_results") or [])
            iter_console.extend(decl_out.get("console_logs") or [])
        all_tests.extend(iter_tests)
        all_console.extend(iter_console)
        per_iteration.append(
            {
                "iteration": idx,
                "test_results": iter_tests,
                "console_logs": iter_console,
            }
        )

    passed = sum(
        1
        for t in all_tests
        if isinstance(t, dict)
        and (t.get("passed") is True or str(t.get("status") or "").lower() == "pass")
    )
    failed = len(all_tests) - passed
    summary = (
        f"Ran {total} iteration(s) on request #{request_id}: "
        f"{passed} passed / {failed} failed tests"
    )
    result: AgentSendResult = {
        "ok": True,
        "summary": summary,
        "ids": {"request_id": request_id},
        "script_phase": "test",
        "test_results": all_tests,
        "console_logs": all_console,
    }
    result["iterations"] = per_iteration  # type: ignore[typeddict-unknown-key]
    return result
