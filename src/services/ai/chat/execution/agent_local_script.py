"""Agent-facing local script execution via :func:`run_local_entry`."""

from __future__ import annotations

import logging
from typing import Any

from services.ai.chat.execution.agent_send import AgentSendResult, _fail
from services.ai.chat.execution.send_core import _persist_global_changes
from services.scripting import ScriptOutput
from services.scripting.context import load_globals

logger = logging.getLogger(__name__)


def run_agent_local_script(
    *,
    local_script_id: int,
    environment_id: int | None = None,
    persist_globals: bool = False,
) -> AgentSendResult:
    """Run a persisted local script tab without opening the GUI."""
    from services.environment_service import EnvironmentService
    from services.local_script_service import LocalScriptService
    from services.scripting.context import build_pre_request_context, build_script_info
    from services.scripting.local_scripts_project.runner import run_local_entry

    load = LocalScriptService.get_script_load_dict(local_script_id)
    if load is None:
        return _fail("local_script_not_found", f"No local script with id={local_script_id}")

    content = str(load.get("content") or "")
    language = str(load.get("language") or "javascript")
    name = str(load.get("name") or f"script-{local_script_id}")

    if not content.strip():
        return {
            "ok": True,
            "summary": f"Local script {name!r} is empty",
            "test_results": [],
            "console_logs": [],
            "ids": {"local_script_id": local_script_id},
        }

    try:
        variables = EnvironmentService.build_combined_variable_map(environment_id, None)
        env_name = ""
        if environment_id is not None:
            env = EnvironmentService.get_environment(environment_id)
            if env is not None:
                env_name = str(env.name or "")

        global_vars = load_globals()
        info = build_script_info(
            event_name="prerequest",
            request_name=name,
            request_id=str(local_script_id),
        )
        info["localScriptId"] = local_script_id

        context = build_pre_request_context(
            method="GET",
            url="https://example.com",
            headers={},
            body="",
            variables=variables,
            environment_vars={},
            collection_vars={},
            global_vars=global_vars,
            info=info,
            auth=None,
            environment_name=env_name,
        )
        output: ScriptOutput | dict[str, Any] = run_local_entry(
            local_script_id,
            content,
            language,
            context,
        )
        _persist_global_changes(
            output.get("global_variable_changes"),
            persist_globals=persist_globals,
            global_vars=global_vars,
        )
    except Exception as exc:
        logger.exception("Agent local script run failed")
        return _fail("local_script_run_failed", str(exc))

    test_results = list(output.get("test_results") or [])
    console_logs = list(output.get("console_logs") or [])
    error = str(output.get("error") or "").strip()
    if error:
        return {
            "ok": False,
            "error": "script_error",
            "message": error,
            "summary": f"Local script {name!r} failed",
            "test_results": test_results,
            "console_logs": console_logs,
            "ids": {"local_script_id": local_script_id},
        }

    failed = sum(1 for t in test_results if not t.get("passed", False))
    elapsed = output.get("elapsed_ms")
    summary = (
        f"Ran local script {name!r} ({len(test_results)} tests, {failed} failed)"
        if test_results
        else f"Ran local script {name!r}"
    )
    result: AgentSendResult = {
        "ok": True,
        "summary": summary,
        "test_results": test_results,
        "console_logs": console_logs,
        "ids": {"local_script_id": local_script_id},
    }
    if isinstance(elapsed, int | float):
        result["warnings"] = [f"elapsed_ms={elapsed}"]
    return result
