"""Shared non-Qt HTTP send orchestration (UI Send + agent execute).

Extracts the non-debug path from :class:`ui.request.http_worker.HttpSendWorker`
so both the Send button and ``postmark_workspace_execute`` share one pipeline:
variable substitution, auth, pre-request/test scripts, HTTP, and result
assembly.  Debug protocol remains worker-only.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any, NotRequired, TypedDict

from services.http.http_service import HttpResponseDict, HttpService
from services.scripting import ScriptEntry, ScriptInput, ScriptOutput

logger = logging.getLogger(__name__)

AGENT_SEND_MAX_PARALLEL = 3
AGENT_SEND_SLOT_WAIT_S = 60.0

_agent_send_semaphore = threading.Semaphore(AGENT_SEND_MAX_PARALLEL)


class SendCoreResult(TypedDict):
    """Outcome of :func:`run_shared_send`.

    On success ``ok`` is true and ``response`` holds an
    :class:`~services.http.http_service.HttpResponseDict` (plus script fields).
    Cancellation sets ``cancelled``; other failures set ``error``.
    """

    ok: bool
    cancelled: NotRequired[bool]
    error: NotRequired[str]
    response: NotRequired[dict[str, Any]]


def apply_send_auth(
    auth_data: dict | None,
    url: str,
    headers: str | None,
    variables: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, str | None]:
    """Inject auth credentials into the URL or headers.

    Substitutes environment variables in auth entry values, then
    delegates to :func:`services.http.auth_handler.apply_auth`.
    Returns the (possibly modified) ``url`` and ``headers``.
    """
    if not auth_data:
        return url, headers

    from services.environment_service import EnvironmentService
    from services.http.auth_handler import apply_auth
    from services.http.header_utils import parse_header_dict

    sub = EnvironmentService.substitute
    auth_type = auth_data.get("type", "noauth")

    entries = auth_data.get(auth_type, [])
    if entries and variables:
        substituted = dict(auth_data)
        substituted[auth_type] = [
            {**e, "value": sub(str(e.get("value", "")), variables)} if isinstance(e, dict) else e
            for e in entries
        ]
    else:
        substituted = auth_data

    hdr_dict = parse_header_dict(headers)
    url, hdr_dict = apply_auth(
        substituted,
        url,
        hdr_dict,
        method=method,
        body=body,
    )
    new_headers: str | None = (
        "\n".join(f"{k}: {v}" for k, v in hdr_dict.items()) if hdr_dict else None
    )
    return url, new_headers


def _is_cancelled(
    cancel_event: threading.Event | None,
    cancel_check: Callable[[], bool] | None,
) -> bool:
    """Return whether the caller requested cancellation."""
    if cancel_event is not None and cancel_event.is_set():
        return True
    return bool(cancel_check is not None and cancel_check())


def _cancelled_result() -> SendCoreResult:
    """Build a cancelled :class:`SendCoreResult`."""
    return {"ok": False, "cancelled": True, "error": "Request cancelled"}


def _error_result(message: str) -> SendCoreResult:
    """Build an error :class:`SendCoreResult`."""
    return {"ok": False, "error": message}


def run_shared_send(
    *,
    method: str,
    url: str,
    headers: str | None = None,
    body: str | None = None,
    body_mode: str | None = None,
    timeout: float = 30.0,
    request_id: int | None = None,
    request_name: str = "",
    env_id: int | None = None,
    variable_collection_id: int | None = None,
    local_overrides: dict[str, str] | None = None,
    auth_data: dict | None = None,
    pre_scripts: list[ScriptEntry] | None = None,
    test_scripts: list[ScriptEntry] | None = None,
    declarative_test_script: ScriptEntry | None = None,
    persist_globals: bool = False,
    cancel_event: threading.Event | None = None,
    cancel_check: Callable[[], bool] | None = None,
    acquire_agent_slot: bool = False,
    enforce_binary_path_policy: bool = False,
) -> SendCoreResult:
    """Run the shared send pipeline (no Qt, no debug protocol).

    When *acquire_agent_slot* is true, waits up to
    :data:`AGENT_SEND_SLOT_WAIT_S` for one of
    :data:`AGENT_SEND_MAX_PARALLEL` process-wide slots (agent execute only).

    *persist_globals* defaults to false (agent opt-in).  The UI Send path
    passes ``True`` to match historical HttpSendWorker behaviour.

    When *enforce_binary_path_policy* is true (agent sends) and
    *body_mode* is ``binary``, the body path must pass the Agent
    binary path allowlist before the file is read.
    """
    if acquire_agent_slot:
        acquired = _agent_send_semaphore.acquire(timeout=AGENT_SEND_SLOT_WAIT_S)
        if not acquired:
            return _error_result(
                f"Agent send slot unavailable after {AGENT_SEND_SLOT_WAIT_S:.0f}s "
                f"(max {AGENT_SEND_MAX_PARALLEL} concurrent)"
            )
        try:
            return _run_shared_send_inner(
                method=method,
                url=url,
                headers=headers,
                body=body,
                body_mode=body_mode,
                timeout=timeout,
                request_id=request_id,
                request_name=request_name,
                env_id=env_id,
                variable_collection_id=variable_collection_id,
                local_overrides=local_overrides,
                auth_data=auth_data,
                pre_scripts=pre_scripts,
                test_scripts=test_scripts,
                declarative_test_script=declarative_test_script,
                persist_globals=persist_globals,
                cancel_event=cancel_event,
                cancel_check=cancel_check,
                enforce_binary_path_policy=enforce_binary_path_policy,
            )
        finally:
            _agent_send_semaphore.release()

    return _run_shared_send_inner(
        method=method,
        url=url,
        headers=headers,
        body=body,
        body_mode=body_mode,
        timeout=timeout,
        request_id=request_id,
        request_name=request_name,
        env_id=env_id,
        variable_collection_id=variable_collection_id,
        local_overrides=local_overrides,
        auth_data=auth_data,
        pre_scripts=pre_scripts,
        test_scripts=test_scripts,
        declarative_test_script=declarative_test_script,
        persist_globals=persist_globals,
        cancel_event=cancel_event,
        cancel_check=cancel_check,
        enforce_binary_path_policy=enforce_binary_path_policy,
    )


def _run_shared_send_inner(
    *,
    method: str,
    url: str,
    headers: str | None,
    body: str | None,
    body_mode: str | None,
    timeout: float,
    request_id: int | None,
    request_name: str,
    env_id: int | None,
    variable_collection_id: int | None,
    local_overrides: dict[str, str] | None,
    auth_data: dict | None,
    pre_scripts: list[ScriptEntry] | None,
    test_scripts: list[ScriptEntry] | None,
    declarative_test_script: ScriptEntry | None,
    persist_globals: bool,
    cancel_event: threading.Event | None,
    cancel_check: Callable[[], bool] | None,
    enforce_binary_path_policy: bool = False,
) -> SendCoreResult:
    """Execute the send pipeline after optional agent-slot acquisition."""
    if _is_cancelled(cancel_event, cancel_check):
        return _cancelled_result()

    try:
        return _execute_send(
            method=method,
            url=url,
            headers=headers,
            body=body,
            body_mode=body_mode,
            timeout=timeout,
            request_id=request_id,
            request_name=request_name,
            env_id=env_id,
            variable_collection_id=variable_collection_id,
            local_overrides=local_overrides or {},
            auth_data=auth_data,
            pre_scripts=pre_scripts or [],
            test_scripts=test_scripts or [],
            declarative_test_script=declarative_test_script,
            persist_globals=persist_globals,
            cancel_event=cancel_event,
            cancel_check=cancel_check,
            enforce_binary_path_policy=enforce_binary_path_policy,
        )
    except Exception as exc:
        logger.exception("Shared send core failed")
        return _error_result(str(exc))


def _persist_global_changes(
    changes: dict[str, str] | None,
    *,
    persist_globals: bool,
    global_vars: dict[str, str],
) -> None:
    """Optionally persist global variable changes and update *global_vars*."""
    if not changes:
        return
    if persist_globals:
        from services.scripting.context import save_globals

        save_globals(changes)
    global_vars.update(changes)


def _execute_send(
    *,
    method: str,
    url: str,
    headers: str | None,
    body: str | None,
    body_mode: str | None,
    timeout: float,
    request_id: int | None,
    request_name: str,
    env_id: int | None,
    variable_collection_id: int | None,
    local_overrides: dict[str, str],
    auth_data: dict | None,
    pre_scripts: list[ScriptEntry],
    test_scripts: list[ScriptEntry],
    declarative_test_script: ScriptEntry | None,
    persist_globals: bool,
    cancel_event: threading.Event | None,
    cancel_check: Callable[[], bool] | None,
    enforce_binary_path_policy: bool = False,
) -> SendCoreResult:
    """Core send steps: vars → auth → pre → HTTP → post/declarative tests."""
    from services.environment_service import EnvironmentService
    from services.http.header_utils import parse_header_dict
    from services.scripting.context import (
        apply_request_mutations,
        apply_variable_changes,
        build_pre_request_context,
        build_script_info,
        load_globals,
    )
    from services.scripting.engine import ScriptEngine

    # 1. Resolve collection + environment variables
    variables = EnvironmentService.build_combined_variable_map(
        env_id,
        request_id,
        collection_id=variable_collection_id,
    )

    # 2. Apply per-request local overrides (highest precedence)
    if local_overrides:
        variables.update(local_overrides)

    url = EnvironmentService.substitute(url, variables)
    if headers:
        headers = EnvironmentService.substitute(headers, variables)
    if body:
        body = EnvironmentService.substitute(body, variables)

    mode = (body_mode or "").strip().casefold()
    if mode == "binary" and body and enforce_binary_path_policy:
        from services.ai.chat.execution.binary.path_policy import validate_binary_path

        _path, path_err = validate_binary_path(body)
        if path_err:
            return _error_result(path_err)

    # 3. Apply auth configuration
    if auth_data:
        url, headers = apply_send_auth(
            auth_data,
            url,
            headers,
            variables,
            method=method,
            body=body,
        )

    # 4. Run pre-request scripts (may mutate request + variables)
    env_name = ""
    if env_id is not None:
        env = EnvironmentService.get_environment(env_id)
        if env is not None:
            env_name = str(env.name or "")

    global_vars = load_globals() if (pre_scripts or test_scripts) else {}

    pre_output: ScriptOutput | dict[str, Any] | None = None
    if pre_scripts:
        header_dict = parse_header_dict(headers) if headers else {}
        pre_ctx = build_pre_request_context(
            method=method,
            url=url,
            headers=header_dict,
            body=body or "",
            variables=variables,
            environment_vars={},
            collection_vars={},
            global_vars=global_vars,
            info=build_script_info(
                event_name="prerequest",
                request_name=request_name,
                request_id=str(request_id or ""),
            ),
            auth=auth_data,
            environment_name=env_name,
        )
        pre_output = ScriptEngine.run_pre_request_scripts(pre_scripts, pre_ctx)
        _persist_global_changes(
            pre_output.get("global_variable_changes"),
            persist_globals=persist_globals,
            global_vars=global_vars,
        )
        if pre_output.get("request_mutations"):
            method, url, header_dict, body_str = apply_request_mutations(
                pre_output["request_mutations"],
                method=method,
                url=url,
                headers=header_dict,
                body=body or "",
            )
            body = body_str
            headers = "\n".join(f"{k}: {v}" for k, v in header_dict.items())
        if pre_output.get("variable_changes"):
            variables = apply_variable_changes(pre_output["variable_changes"], variables)

    if _is_cancelled(cancel_event, cancel_check):
        return _cancelled_result()

    result: HttpResponseDict = HttpService.send_request(
        method=method,
        url=url,
        headers=headers,
        body=body,
        body_mode=body_mode,
        timeout=timeout,
    )

    # 5. Check cancellation after the request completes
    if _is_cancelled(cancel_event, cancel_check):
        return _cancelled_result()

    # 6. Run test scripts + declarative assertions
    all_test_results: list[Any] = []
    all_console_logs: list[Any] = []
    all_var_changes: dict[str, str] = {}
    pre_request_errors: list[Any] = []
    pre_console_logs: list[Any] = []
    pre_var_changes: dict[str, str] = {}

    # Collect pre-request script outputs — only console logs and
    # variable changes.  Pre-request results (including runtime
    # errors) must NOT appear in the Test Results tab; runtime
    # errors are surfaced as console error entries and also
    # collected separately for the response viewer.
    if pre_output:
        for tr in pre_output.get("test_results", []):
            if tr.get("name") == "(runtime error)":
                source = tr.get("source_name", "pre-request")
                error = tr.get("error", "unknown error")
                pre_request_errors.append(tr)
                all_console_logs.append(
                    {
                        "level": "error",
                        "message": f"[{source}] {error}",
                        "timestamp": 0,
                    }
                )
        pre_console_logs = list(pre_output.get("console_logs", []))
        all_console_logs.extend(pre_console_logs)
        pre_var_changes = dict(pre_output.get("variable_changes", {}))
        all_var_changes.update(pre_var_changes)

    run_post_response = bool(test_scripts or declarative_test_script)
    test_ctx: ScriptInput | None = None
    if run_post_response:
        from services.scripting.context import build_test_context

        test_ctx = build_test_context(
            request_data={
                "url": url,
                "method": method,
                "headers": parse_header_dict(headers) if headers else {},
                "body": body or "",
            },
            response_data={
                "status_code": result.get("status_code", 0),
                "status": result.get("status_text", ""),
                "headers": {
                    h["key"]: h["value"] for h in result.get("headers", []) if isinstance(h, dict)
                },
                "body": result.get("body", ""),
                "elapsed_ms": result.get("elapsed_ms", 0),
                "size_bytes": result.get("size_bytes", 0),
            },
            variables=variables,
            environment_vars={},
            collection_vars={},
            global_vars=global_vars,
            info=build_script_info(
                event_name="test",
                request_name=request_name,
                request_id=str(request_id or ""),
            ),
            environment_name=env_name,
        )

    if test_scripts and test_ctx is not None:
        test_output: ScriptOutput | dict[str, Any] = ScriptEngine.run_test_scripts(
            test_scripts,
            test_ctx,
        )
        all_test_results.extend(test_output.get("test_results", []))
        all_console_logs.extend(test_output.get("console_logs", []))
        all_var_changes.update(test_output.get("variable_changes", {}))
        _persist_global_changes(
            test_output.get("global_variable_changes"),
            persist_globals=persist_globals,
            global_vars=global_vars,
        )

    if declarative_test_script and test_ctx is not None:
        decl_code = declarative_test_script.get("code", "")
        if decl_code.strip():
            decl_output = ScriptEngine.run_single(
                decl_code,
                declarative_test_script.get("language", "javascript"),
                test_ctx,
            )
            all_test_results.extend(decl_output.get("test_results", []))
            all_console_logs.extend(decl_output.get("console_logs", []))
            all_var_changes.update(decl_output.get("variable_changes", {}))
            _persist_global_changes(
                decl_output.get("global_variable_changes"),
                persist_globals=persist_globals,
                global_vars=global_vars,
            )

    # 7. Attach script results to the response dict
    final: dict[str, Any] = dict(result)
    if all_test_results:
        final["test_results"] = all_test_results
    if all_console_logs:
        final["console_logs"] = all_console_logs
    if all_var_changes:
        final["variable_changes"] = all_var_changes
    if pre_request_errors:
        final["pre_request_errors"] = pre_request_errors
    if pre_console_logs:
        final["pre_request_console_logs"] = pre_console_logs
    if pre_var_changes:
        final["pre_request_variable_changes"] = pre_var_changes
    if pre_scripts:
        final["has_pre_request_scripts"] = True

    return {"ok": True, "response": final}
