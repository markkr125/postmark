"""Agent-facing wrappers around :func:`run_shared_send`.

Used by ``postmark_workspace_execute``.  Always passes
``acquire_agent_slot=True`` so concurrent agent HTTP is capped.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, NotRequired, TypedDict

from services.ai.chat.execution.redact_result import redact_send_result
from services.ai.chat.execution.send_core import _persist_global_changes, run_shared_send
from services.scripting import ScriptEntry, ScriptOutput

logger = logging.getLogger(__name__)


class AgentSendResult(TypedDict):
    """Observation-oriented result for workspace execute."""

    ok: bool
    error: NotRequired[str]
    message: NotRequired[str]
    summary: NotRequired[str]
    status_code: NotRequired[int | None]
    url: NotRequired[str | None]
    body_preview: NotRequired[str | None]
    test_results: NotRequired[list[Any]]
    console_logs: NotRequired[list[Any]]
    script_phase: NotRequired[str]
    ids: NotRequired[dict[str, int]]
    warnings: NotRequired[list[str]]


def _fail(error: str, message: str = "") -> AgentSendResult:
    """Build a failed agent send result."""
    out: AgentSendResult = {"ok": False, "error": error}
    if message:
        out["message"] = message
    return out


def _headers_text(raw: Any) -> str | None:
    """Normalise stored headers to the worker text format."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw or None
    if isinstance(raw, list):
        lines: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                key = str(item.get("key", "")).strip()
                if key:
                    lines.append(f"{key}: {item.get('value', '')}")
        return "\n".join(lines) if lines else None
    return str(raw) or None


def _test_language(test_scripts: list[ScriptEntry] | None) -> str:
    """Pick declarative compile language from the post-response chain."""
    if not test_scripts:
        return "javascript"
    lang = str(test_scripts[-1].get("language") or "javascript").lower()
    return lang if lang in {"javascript", "typescript", "python"} else "javascript"


def _body_preview(response: dict[str, Any], *, max_len: int = 400) -> str:
    """Short redacted body preview for the observation."""
    redacted = redact_send_result(response)
    body = str(redacted.get("body") or "")
    if len(body) <= max_len:
        return body
    return f"{body[:max_len]}… (truncated, {len(body)} chars)"


def _maybe_record_history(
    *,
    record_history: bool,
    request_id: int | None,
    request_name: str,
    method: str,
    url: str,
    response: dict[str, Any],
) -> tuple[list[str], int | None]:
    """Persist a successful agent send via :class:`RequestHistoryService`.

    Returns ``(warnings, history_entry_id)``. *history_entry_id* is set when a
    row was written so chat execute cards can deep-link to the stored response.
    """
    if not record_history:
        return [], None
    try:
        from services.history_retention_config import load_history_retention_config
        from services.request_history_service import RequestHistoryService, SendIdentityDict

        identity: SendIdentityDict = {
            "request_id": request_id,
            "request_name": request_name,
            "method": method,
            "url": url,
        }
        snapshot: dict[str, Any] = {
            "method": method,
            "url": url,
            "name": request_name,
        }
        tests = response.get("test_results")
        if isinstance(tests, list) and tests:
            snapshot["test_results"] = tests
        entry_id = RequestHistoryService.record_send(
            identity=identity,
            response=response,
            original_request=snapshot,
            settings=load_history_retention_config(),
        )
        if entry_id is None:
            return ["history_recording_failed"], None
        return [], int(entry_id)
    except Exception as exc:
        logger.exception("Agent send history recording failed")
        return [f"history_recording_failed: {exc}"], None


def _from_core(
    core: dict[str, Any],
    *,
    ids: dict[str, int],
    summary: str,
    warnings: list[str] | None = None,
    record_history: bool = False,
    request_id: int | None = None,
    request_name: str = "",
    method: str = "GET",
    url: str = "",
) -> AgentSendResult:
    """Map a :class:`SendCoreResult` into an :class:`AgentSendResult`."""
    if core.get("cancelled"):
        return _fail("cancelled", "Request cancelled")
    if not core.get("ok"):
        return _fail(str(core.get("error") or "send_failed"), str(core.get("error") or ""))
    response = core.get("response")
    if not isinstance(response, dict):
        return _fail("empty_response", "Send returned no response")
    redacted = redact_send_result(response)
    # Persist the real URL for replay; observation uses the redacted copy.
    history_url = str(response.get("request_url") or url or "")
    history_method = str(response.get("request_method") or method or "GET")
    hist_warn, hist_id = _maybe_record_history(
        record_history=record_history,
        request_id=request_id,
        request_name=request_name,
        method=history_method,
        url=history_url,
        response=response,
    )
    out_ids = dict(ids)
    if hist_id is not None:
        out_ids["history_entry_id"] = hist_id
    out: AgentSendResult = {
        "ok": True,
        "summary": summary,
        "status_code": redacted.get("status_code"),
        "url": redacted.get("request_url"),
        "body_preview": _body_preview(response),
        "test_results": list(redacted.get("test_results") or []),
        "ids": out_ids,
    }
    merged = list(warnings or []) + hist_warn
    if redacted.get("error"):
        merged.append(str(redacted["error"]))
    if merged:
        out["warnings"] = merged
    return out


def run_agent_send_request(
    *,
    request_id: int,
    environment_id: int | None = None,
    persist_globals: bool = False,
    record_history: bool = True,
    include_scripts: bool = True,
) -> AgentSendResult:
    """Send a saved request via SharedSendCore (agent slot acquired)."""
    from services.assertion_service import AssertionService
    from services.collection_service import CollectionService
    from services.script_service import ScriptService

    req = CollectionService.get_request(request_id)
    if req is None:
        return _fail("request_not_found", f"No request with id={request_id}")

    method = str(req.method or "GET")
    url = str(req.url or "")
    if not url.strip():
        return _fail("empty_url", "Request URL is empty")

    headers = _headers_text(req.headers)
    body = str(req.body) if req.body is not None else None
    body_mode = str(req.body_mode) if getattr(req, "body_mode", None) else None
    auth_data = CollectionService.get_request_auth_chain(request_id)
    request_name = str(req.name or "")

    pre_scripts: list[ScriptEntry] | None = None
    test_scripts: list[ScriptEntry] | None = None
    declarative: ScriptEntry | None = None
    if include_scripts:
        pre_scripts, test_scripts = ScriptService.build_script_chain(request_id)
        declarative = AssertionService.build_declarative_script_entry(
            request_id,
            _test_language(test_scripts),
        )

    core = run_shared_send(
        method=method,
        url=url,
        headers=headers,
        body=body,
        body_mode=body_mode,
        request_id=request_id,
        request_name=request_name,
        env_id=environment_id,
        auth_data=auth_data,
        pre_scripts=pre_scripts,
        test_scripts=test_scripts,
        declarative_test_script=declarative,
        persist_globals=persist_globals,
        acquire_agent_slot=True,
        enforce_binary_path_policy=True,
    )
    return _from_core(
        dict(core),
        ids={"request_id": request_id},
        summary=f"Sent {method} {request_name or url}",
        record_history=record_history,
        request_id=request_id,
        request_name=request_name,
        method=method,
        url=url,
    )


def run_agent_send_draft(
    *,
    environment_id: int | None = None,
    persist_globals: bool = False,
    record_history: bool = True,
    include_scripts: bool = True,
) -> AgentSendResult:
    """Send the dirty open-tab draft from the current workspace snapshot."""
    from services.ai.chat.workspace_snapshot import get_workspace_snapshot
    from services.script_service import ScriptService

    from services.ai.ai_config import AiConfig

    session_id = str(AiConfig.get_chat_session_id() or "")
    if not session_id:
        return _fail("no_session", "No active chat session for draft send")

    snap = get_workspace_snapshot(session_id)
    if not snap:
        return _fail("no_snapshot", "No workspace snapshot for this session")

    tabs = snap.get("tabs")
    if not isinstance(tabs, list) or not tabs:
        return _fail("no_open_tabs", "No open tabs in workspace snapshot")

    active_index = snap.get("active_tab_index")
    tab: dict[str, Any] | None = None
    if isinstance(active_index, int) and 0 <= active_index < len(tabs):
        candidate = tabs[active_index]
        if isinstance(candidate, dict):
            tab = candidate
    if tab is None or not tab.get("is_dirty"):
        for item in tabs:
            if isinstance(item, dict) and item.get("is_dirty"):
                tab = item
                break
    if tab is None or not isinstance(tab.get("request_data"), dict):
        return _fail("no_draft", "No dirty draft tab with request_data")

    data = tab["request_data"]
    assert isinstance(data, dict)
    method = str(data.get("method") or "GET")
    url = str(data.get("url") or "").strip()
    if not url:
        return _fail("empty_url", "Draft URL is empty")

    headers = _headers_text(data.get("headers"))
    body_val = data.get("body")
    body = str(body_val) if body_val is not None and str(body_val) else None
    body_mode = str(data["body_mode"]) if data.get("body_mode") else None
    auth_data = data.get("auth") if isinstance(data.get("auth"), dict) else None
    request_id = tab.get("request_id") if isinstance(tab.get("request_id"), int) else None
    request_name = str(tab.get("name") or data.get("name") or "Draft")
    variable_collection_id = (
        int(tab["collection_id"]) if isinstance(tab.get("collection_id"), int) else None
    )

    pre_scripts: list[ScriptEntry] | None = None
    test_scripts: list[ScriptEntry] | None = None
    if include_scripts:
        if request_id is not None:
            pre_scripts, test_scripts = ScriptService.build_script_chain(request_id)
        else:
            scripts_data = data.get("scripts")
            if scripts_data:
                pre_scripts, test_scripts = ScriptService.build_collection_script_chain(
                    scripts_data, name=request_name
                )

    # Prefer snapshot env when the caller did not override.
    env_id = environment_id
    if env_id is None and isinstance(snap.get("current_env_id"), int):
        env_id = int(snap["current_env_id"])

    core = run_shared_send(
        method=method,
        url=url,
        headers=headers,
        body=body,
        body_mode=body_mode,
        request_id=request_id,
        request_name=request_name,
        env_id=env_id,
        variable_collection_id=variable_collection_id,
        auth_data=auth_data,
        pre_scripts=pre_scripts,
        test_scripts=test_scripts,
        persist_globals=persist_globals,
        acquire_agent_slot=True,
        enforce_binary_path_policy=True,
    )
    ids: dict[str, int] = {}
    if request_id is not None:
        ids["request_id"] = request_id
    return _from_core(
        dict(core),
        ids=ids,
        summary=f"Sent draft {method} {url}",
        record_history=record_history,
        request_id=request_id,
        request_name=request_name,
        method=method,
        url=url,
    )


def run_agent_replay_history(
    *,
    history_entry_id: int,
    environment_id: int | None = None,
    persist_globals: bool = False,
    record_history: bool = True,
    include_scripts: bool = True,
) -> AgentSendResult:
    """Replay a history entry through SharedSendCore."""
    from services.assertion_service import AssertionService
    from services.collection_service import CollectionService
    from services.request_history_service import (
        build_send_payload_from_entry,
        entry_for_replay,
    )
    from services.script_service import ScriptService

    entry = entry_for_replay(history_entry_id)
    if entry is None:
        return _fail("history_not_found", f"No replayable entry id={history_entry_id}")

    payload = build_send_payload_from_entry(entry)
    if payload is None:
        return _fail("history_payload_unavailable", "History entry has no send payload")

    request_id = entry.get("request_id")
    request_name = str(entry.get("request_name") or "")
    auth_data = None
    pre_scripts: list[ScriptEntry] | None = None
    test_scripts: list[ScriptEntry] | None = None
    declarative: ScriptEntry | None = None
    if include_scripts and isinstance(request_id, int):
        auth_data = CollectionService.get_request_auth_chain(request_id)
        pre_scripts, test_scripts = ScriptService.build_script_chain(request_id)
        declarative = AssertionService.build_declarative_script_entry(
            request_id,
            _test_language(test_scripts),
        )

    snap = payload.get("history_snapshot")
    body_mode: str | None = None
    if isinstance(snap, dict) and snap.get("body_mode"):
        body_mode = str(snap["body_mode"])

    core = run_shared_send(
        method=payload["method"],
        url=payload["url"],
        headers=payload["headers"],
        body=payload["body"],
        body_mode=body_mode,
        request_id=request_id if isinstance(request_id, int) else None,
        request_name=request_name,
        env_id=environment_id,
        auth_data=auth_data,
        pre_scripts=pre_scripts,
        test_scripts=test_scripts,
        declarative_test_script=declarative,
        persist_globals=persist_globals,
        acquire_agent_slot=True,
        enforce_binary_path_policy=True,
    )
    ids: dict[str, int] = {"history_entry_id": history_entry_id}
    if isinstance(request_id, int):
        ids["request_id"] = request_id
    return _from_core(
        dict(core),
        ids=ids,
        summary=f"Replayed history #{history_entry_id} {payload['method']} {payload['url']}",
        record_history=record_history,
        request_id=request_id if isinstance(request_id, int) else None,
        request_name=request_name,
        method=str(payload["method"]),
        url=str(payload["url"]),
    )


def run_agent_scripts(
    *,
    request_id: int,
    phase: Literal["pre", "test", "both"] = "both",
    environment_id: int | None = None,
    persist_globals: bool = False,
) -> AgentSendResult:
    """Run pre/test/both scripts for a saved request without sending HTTP."""
    from services.assertion_service import AssertionService
    from services.collection_service import CollectionService
    from services.environment_service import EnvironmentService
    from services.http.header_utils import parse_header_dict
    from services.script_service import ScriptService
    from services.scripting.context import (
        apply_request_mutations,
        apply_variable_changes,
        build_pre_request_context,
        build_script_info,
        build_test_context,
        load_globals,
    )
    from services.scripting.engine import ScriptEngine

    req = CollectionService.get_request(request_id)
    if req is None:
        return _fail("request_not_found", f"No request with id={request_id}")

    method = str(req.method or "GET")
    url = str(req.url or "")
    headers = _headers_text(req.headers)
    body = str(req.body) if req.body is not None else None
    request_name = str(req.name or "")
    auth_data = CollectionService.get_request_auth_chain(request_id)

    run_pre = phase in {"pre", "both"}
    run_test = phase in {"test", "both"}
    pre_scripts: list[ScriptEntry] = []
    test_scripts: list[ScriptEntry] = []
    declarative: ScriptEntry | None = None
    chain_pre, chain_test = ScriptService.build_script_chain(request_id)
    if run_pre:
        pre_scripts = list(chain_pre)
    if run_test:
        test_scripts = list(chain_test)
        declarative = AssertionService.build_declarative_script_entry(
            request_id,
            _test_language(test_scripts),
        )

    if not pre_scripts and not test_scripts and not declarative:
        return {
            "ok": True,
            "summary": f"No scripts to run (phase={phase})",
            "test_results": [],
            "console_logs": [],
            "script_phase": phase,
            "ids": {"request_id": request_id},
        }

    try:
        variables = EnvironmentService.build_combined_variable_map(
            environment_id,
            request_id,
        )
        url = EnvironmentService.substitute(url, variables)
        if headers:
            headers = EnvironmentService.substitute(headers, variables)
        if body:
            body = EnvironmentService.substitute(body, variables)

        env_name = ""
        if environment_id is not None:
            env = EnvironmentService.get_environment(environment_id)
            if env is not None:
                env_name = str(env.name or "")

        global_vars = load_globals()
        all_test_results: list[Any] = []
        all_console_logs: list[Any] = []
        header_dict = parse_header_dict(headers) if headers else {}

        if pre_scripts:
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
                    request_id=str(request_id),
                ),
                auth=auth_data,
                environment_name=env_name,
            )
            pre_output: ScriptOutput | dict[str, Any] = ScriptEngine.run_pre_request_scripts(
                pre_scripts,
                pre_ctx,
            )
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
            if pre_output.get("variable_changes"):
                variables = apply_variable_changes(pre_output["variable_changes"], variables)
            all_console_logs.extend(pre_output.get("console_logs") or [])
            for tr in pre_output.get("test_results", []):
                # Match SharedSendCore: pre-request (runtime error) stays out of
                # Test Results for standalone run_scripts as well.
                if tr.get("name") == "(runtime error)":
                    continue
                all_test_results.append(tr)

        if test_scripts or declarative:
            test_ctx = build_test_context(
                request_data={
                    "url": url,
                    "method": method,
                    "headers": header_dict,
                    "body": body or "",
                },
                response_data={
                    "status_code": 0,
                    "status": "",
                    "headers": {},
                    "body": "",
                    "elapsed_ms": 0,
                    "size_bytes": 0,
                },
                variables=variables,
                environment_vars={},
                collection_vars={},
                global_vars=global_vars,
                info=build_script_info(
                    event_name="test",
                    request_name=request_name,
                    request_id=str(request_id),
                ),
                environment_name=env_name,
            )
            if test_scripts:
                test_output: ScriptOutput | dict[str, Any] = ScriptEngine.run_test_scripts(
                    test_scripts,
                    test_ctx,
                )
                all_test_results.extend(test_output.get("test_results", []))
                all_console_logs.extend(test_output.get("console_logs") or [])
                _persist_global_changes(
                    test_output.get("global_variable_changes"),
                    persist_globals=persist_globals,
                    global_vars=global_vars,
                )
            if declarative:
                decl_code = declarative.get("code", "")
                if decl_code.strip():
                    decl_output = ScriptEngine.run_single(
                        decl_code,
                        declarative.get("language", "javascript"),
                        test_ctx,
                    )
                    all_test_results.extend(decl_output.get("test_results", []))
                    all_console_logs.extend(decl_output.get("console_logs") or [])
                    _persist_global_changes(
                        decl_output.get("global_variable_changes"),
                        persist_globals=persist_globals,
                        global_vars=global_vars,
                    )
    except Exception as exc:
        logger.exception("Agent script-only run failed")
        return _fail("script_run_failed", str(exc))

    failed = sum(1 for t in all_test_results if not t.get("passed", False))
    return {
        "ok": True,
        "summary": (
            f"Ran scripts phase={phase} for {request_name or request_id} "
            f"({len(all_test_results)} tests, {failed} failed)"
        ),
        "test_results": all_test_results,
        "console_logs": all_console_logs,
        "script_phase": phase,
        "ids": {"request_id": request_id},
    }
