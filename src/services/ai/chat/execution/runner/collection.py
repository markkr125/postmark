"""Agent collection runner — hydrate requests and run without Qt."""

from __future__ import annotations

import logging
import time
from typing import Any

from services.ai.chat.execution.agent_send import AgentSendResult, _fail, _headers_text
from services.ai.chat.execution.send_core import run_shared_send
from services.assertion_service import AssertionService
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.run_history_service import RunHistoryService
from services.script_service import ScriptService
from services.scripting import ScriptEntry

logger = logging.getLogger(__name__)

_SENTINEL = object()


def _walk_collection_requests(collection_id: int) -> list[dict[str, Any]]:
    """Return tree-projection request nodes under *collection_id* (depth-first)."""
    tree = CollectionService.fetch_all()
    requests: list[dict[str, Any]] = []

    def _walk(node: dict[str, Any]) -> None:
        if node.get("type") == "request":
            requests.append(node)
            return
        for child in (node.get("children") or {}).values():
            _walk(child)

    def _find(node: dict[str, Any]) -> dict[str, Any] | None:
        if node.get("type") != "request" and node.get("id") == collection_id:
            return node
        for child in (node.get("children") or {}).values():
            hit = _find(child)
            if hit is not None:
                return hit
        return None

    for root in tree.values():
        target = _find(root)
        if target is not None:
            _walk(target)
            break
    return requests


def _test_language(test_scripts: list[ScriptEntry]) -> str:
    """Pick declarative compile language from the post-response chain."""
    if not test_scripts:
        return "javascript"
    lang = str(test_scripts[-1].get("language") or "javascript").lower()
    return lang if lang in {"javascript", "typescript", "python"} else "javascript"


def _count_tests(test_results: list[Any]) -> tuple[int, int, int]:
    """Return (passed, failed, skipped) from test result rows."""
    passed = failed = skipped = 0
    for row in test_results:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").lower()
        if status == "pass" or row.get("passed") is True:
            passed += 1
        elif status == "skip" or row.get("skipped") is True:
            skipped += 1
        else:
            failed += 1
    return passed, failed, skipped


def run_agent_collection(
    *,
    collection_id: int,
    request_ids: list[int] | None = None,
    environment_id: int | None = None,
    iterations: int = 1,
    delay_ms: int = 0,
    iteration_data: list[dict[str, Any]] | None = None,
    persist_globals: bool = False,
    scripts_enabled: bool = True,
) -> AgentSendResult:
    """Run a folder checklist with hydrated requests + RunHistory persistence."""
    coll = CollectionService.get_collection(collection_id)
    if coll is None:
        return _fail("collection_not_found", f"No collection with id={collection_id}")

    tree_requests = _walk_collection_requests(collection_id)
    if request_ids:
        wanted = set(request_ids)
        selected = [r for r in tree_requests if int(r.get("id") or 0) in wanted]
    else:
        selected = list(tree_requests)
    if not selected:
        return _fail("no_requests", "Collection has no requests to run")

    iter_rows = list(iteration_data or [])
    iteration_count = max(1, int(iterations))
    if iter_rows:
        iteration_count = max(iteration_count, len(iter_rows))

    env_name = ""
    if environment_id is not None:
        env = EnvironmentService.get_environment(environment_id)
        if env is not None:
            env_name = str(env.name or "")

    run_dict = RunHistoryService.create_run(
        collection_id=collection_id,
        source="agent",
        iterations=iteration_count,
        total_requests=len(selected),
    )
    run_id = int(run_dict["id"])
    started = time.monotonic()
    total_passed = total_failed = total_skipped = total_tests = 0
    elapsed_samples: list[float] = []
    request_names = {str(r.get("name") or ""): idx for idx, r in enumerate(selected)}
    progress_idx = 0
    results_summary: list[dict[str, Any]] = []

    try:
        for iteration in range(iteration_count):
            iter_data = iter_rows[iteration] if iteration < len(iter_rows) else {}
            i = 0
            while i < len(selected):
                if delay_ms > 0 and progress_idx > 0:
                    time.sleep(delay_ms / 1000.0)
                node = selected[i]
                result = _run_one_hydrated(
                    node=node,
                    environment_id=environment_id,
                    environment_name=env_name,
                    iteration=iteration,
                    iteration_count=iteration_count,
                    iter_data=iter_data if isinstance(iter_data, dict) else {},
                    persist_globals=persist_globals,
                    scripts_enabled=scripts_enabled,
                )
                progress_idx += 1
                name = str(result.get("name") or node.get("name") or "")
                method = str(result.get("method") or node.get("method") or "GET")
                status_code = int(result.get("status_code") or 0)
                elapsed_ms = float(result.get("elapsed_ms") or 0.0)
                test_results = list(result.get("test_results") or [])
                tp, tf, ts = _count_tests(test_results)
                total_passed += tp
                total_failed += tf
                total_skipped += ts
                total_tests += tp + tf + ts
                if elapsed_ms > 0:
                    elapsed_samples.append(elapsed_ms)
                error = result.get("error")
                RunHistoryService.add_result(
                    run_id,
                    request_name=name,
                    request_method=method,
                    status_code=status_code,
                    elapsed_ms=elapsed_ms,
                    test_passed=tp,
                    test_failed=tf,
                    error=str(error) if error else None,
                    iteration=iteration,
                    test_results=test_results,
                )
                results_summary.append(
                    {
                        "name": name,
                        "method": method,
                        "status_code": status_code,
                        "passed": tp,
                        "failed": tf,
                    }
                )
                next_req = result.get("_next_request", _SENTINEL)
                if next_req is not _SENTINEL:
                    if next_req is None:
                        i = len(selected)
                    elif next_req in request_names:
                        i = request_names[str(next_req)]
                    else:
                        i += 1
                else:
                    i += 1
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        RunHistoryService.finish_run(
            run_id,
            status="failed",
            duration_ms=duration_ms,
            total_tests=total_tests,
            passed=total_passed,
            failed=total_failed,
            skipped=total_skipped,
        )
        logger.exception("Agent collection run failed")
        return _fail("run_failed", str(exc))

    duration_ms = int((time.monotonic() - started) * 1000)
    avg_ms = sum(elapsed_samples) / len(elapsed_samples) if elapsed_samples else 0.0
    RunHistoryService.finish_run(
        run_id,
        status="completed",
        duration_ms=duration_ms,
        total_tests=total_tests,
        passed=total_passed,
        failed=total_failed,
        skipped=total_skipped,
        avg_response_ms=avg_ms,
    )
    summary = (
        f"Collection #{collection_id} run #{run_id}: "
        f"{len(selected)} request(s) x {iteration_count} iteration(s); "
        f"tests {total_passed} passed / {total_failed} failed"
    )
    return {
        "ok": True,
        "summary": summary,
        "ids": {"collection_id": collection_id, "run_id": run_id},
        "status_code": None,
        "url": None,
        "test_results": results_summary,
    }


def _run_one_hydrated(
    *,
    node: dict[str, Any],
    environment_id: int | None,
    environment_name: str,
    iteration: int,
    iteration_count: int,
    iter_data: dict[str, Any],
    persist_globals: bool,
    scripts_enabled: bool,
) -> dict[str, Any]:
    """Hydrate a tree node via CollectionService and run shared send."""
    request_id = int(node.get("id") or 0)
    req = CollectionService.get_request(request_id) if request_id > 0 else None
    if req is None:
        return {
            "name": str(node.get("name") or ""),
            "method": str(node.get("method") or "GET"),
            "error": "request_not_found",
            "status_code": 0,
            "elapsed_ms": 0,
            "test_results": [],
        }

    method = str(req.method or "GET")
    url = str(req.url or "")
    headers = _headers_text(req.headers)
    body = str(req.body) if req.body is not None else None
    body_mode = str(req.body_mode) if getattr(req, "body_mode", None) else None
    name = str(req.name or "")
    auth_data = CollectionService.get_request_auth_chain(request_id)

    # Merge iteration row into substitution via local_overrides-like env map.
    base_vars = EnvironmentService.build_combined_variable_map(environment_id, request_id)
    if iter_data:
        for key, value in iter_data.items():
            base_vars[str(key)] = str(value)

    pre_scripts: list[ScriptEntry] = []
    test_scripts: list[ScriptEntry] = []
    declarative: ScriptEntry | None = None
    if scripts_enabled:
        pre_scripts, test_scripts = ScriptService.build_script_chain(request_id)
        declarative = AssertionService.build_declarative_script_entry(
            request_id,
            _test_language(test_scripts),
        )

    # Apply iteration substitution before shared send (shared send also substitutes).
    url = EnvironmentService.substitute(url, base_vars)
    if headers:
        headers = EnvironmentService.substitute(headers, base_vars)
    if body:
        body = EnvironmentService.substitute(body, base_vars)

    core = run_shared_send(
        method=method,
        url=url,
        headers=headers,
        body=body,
        body_mode=body_mode,
        request_id=request_id,
        request_name=name,
        env_id=environment_id,
        auth_data=auth_data,
        pre_scripts=pre_scripts or None,
        test_scripts=test_scripts or None,
        declarative_test_script=declarative,
        persist_globals=persist_globals,
        acquire_agent_slot=True,
        enforce_binary_path_policy=True,
        local_overrides={str(k): str(v) for k, v in iter_data.items()} if iter_data else None,
    )
    del environment_name  # reserved for future pm.environment.name parity
    del iteration
    del iteration_count
    if not core.get("ok"):
        return {
            "name": name,
            "method": method,
            "error": core.get("error") or "send_failed",
            "status_code": 0,
            "elapsed_ms": 0,
            "test_results": [],
        }
    response = dict(core.get("response") or {})
    response["name"] = name
    response["method"] = method
    if "next_request" in response:
        response["_next_request"] = response.get("next_request")
    return response
