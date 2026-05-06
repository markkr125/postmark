"""Background worker for running collection requests sequentially.

Runs all requests on a QThread, emitting ``progress`` after each one
and ``finished`` when the entire run completes.  Supports
``pm.execution.setNextRequest()`` / ``skipRequest()`` flow control
and data-driven iteration via CSV/JSON files.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from io import StringIO
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from services.http.http_service import HttpService
from services.script_service import ScriptService
from services.scripting import ScriptEntry
from services.scripting.context import (
    build_pre_request_context,
    build_test_context,
    load_globals,
    save_globals,
)
from services.scripting.engine import ScriptEngine

logger = logging.getLogger(__name__)

# Sentinel to distinguish "setNextRequest not called" from "set to None"
_SENTINEL = object()

# Variable substitution pattern for {{variable}}
_VAR_PATTERN = re.compile(r"\{\{(.+?)\}\}")


def _substitute(text: str, variables: dict[str, str]) -> str:
    """Replace ``{{variable}}`` placeholders in *text*."""
    if not variables or "{{" not in text:
        return text

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return variables.get(key, match.group(0))

    return _VAR_PATTERN.sub(_replace, text)


def scripts_enabled() -> bool:
    """Return ``True`` if the global scripting toggle is on."""
    from PySide6.QtCore import QSettings

    from ui.styling.theme_manager import _APP, _ORG

    val = QSettings(_ORG, _APP).value("scripting/enabled", True)
    if isinstance(val, str):
        return val.lower() not in {"0", "false", "no", "off", ""}
    return bool(val)


def parse_data_file(path: Path) -> list[dict[str, Any]]:
    """Parse a CSV or JSON file into a list of row dicts."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, list):
            return [dict(row) for row in data if isinstance(row, dict)]
        return []
    reader = csv.DictReader(StringIO(text))
    return [dict(row) for row in reader]


class RunnerWorker(QObject):
    """Background worker that runs requests sequentially.

    Supports ``pm.execution.setNextRequest()`` for flow control and
    ``pm.execution.skipRequest()`` to skip individual requests.

    Signals
    -------
    progress(int, dict)
        Emitted after each request with ``(index, result_dict)``.
    finished(list)
        Emitted when all requests are done.
    error(str)
        Emitted on fatal error.
    """

    progress = Signal(int, dict)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self) -> None:
        """Initialise with an empty request list."""
        super().__init__()
        self._requests: list[dict[str, Any]] = []
        self._iteration_data: list[dict[str, Any]] = []
        self._iteration_count: int = 1
        self._delay_ms: int = 0
        self._environment_vars: dict[str, str] = {}
        self._cancelled = False

    def set_requests(self, requests: list[dict[str, Any]]) -> None:
        """Set the list of request dicts to execute."""
        self._requests = requests

    def set_iteration_data(
        self,
        data: list[dict[str, Any]],
        count: int = 1,
    ) -> None:
        """Configure data-driven iterations."""
        self._iteration_data = data
        self._iteration_count = max(1, count)

    def set_delay(self, delay_ms: int) -> None:
        """Set the delay between requests in milliseconds."""
        self._delay_ms = max(0, delay_ms)

    def set_environment_vars(self, env_vars: dict[str, str]) -> None:
        """Set the environment variables for variable substitution."""
        self._environment_vars = dict(env_vars)

    def cancel(self) -> None:
        """Cancel the runner."""
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        """Execute all requests sequentially with script support."""
        import time

        results: list[dict[str, Any]] = []
        request_names = {r.get("name", ""): idx for idx, r in enumerate(self._requests)}
        iterations = self._iteration_count
        if self._iteration_data:
            iterations = max(iterations, len(self._iteration_data))
        progress_idx = 0

        for iteration in range(iterations):
            iter_data: dict[str, Any] = (
                self._iteration_data[iteration] if iteration < len(self._iteration_data) else {}
            )
            i = 0
            while i < len(self._requests):
                if self._cancelled:
                    self.error.emit("Runner cancelled")
                    return

                if self._delay_ms > 0 and progress_idx > 0:
                    time.sleep(self._delay_ms / 1000.0)

                req = self._requests[i]
                result_dict = self._run_one(req, iteration, iterations, iter_data)
                results.append(result_dict)
                self.progress.emit(progress_idx, result_dict)
                progress_idx += 1

                next_req = result_dict.get("_next_request", _SENTINEL)
                if next_req is not _SENTINEL:
                    if next_req is None:
                        i = len(self._requests)
                    elif next_req in request_names:
                        i = request_names[next_req]
                    else:
                        i += 1
                else:
                    i += 1

        self.finished.emit(results)

    def _run_one(
        self,
        req: dict[str, Any],
        iteration: int,
        iteration_count: int,
        iter_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Run a single request with scripts and return the result dict."""
        try:
            return self._execute_request(req, iteration, iteration_count, iter_data)
        except Exception as exc:
            return {
                "name": req.get("name", ""),
                "method": req.get("method", "GET"),
                "error": str(exc),
                "status_code": 0,
                "elapsed_ms": 0,
                "test_results": [],
            }

    def _execute_request(
        self,
        req: dict[str, Any],
        iteration: int,
        iteration_count: int,
        iter_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Core request execution logic with pre/test scripts."""
        request_id = req.get("id")
        variables = req.get("_variables", {})

        pre_scripts: list[ScriptEntry] = []
        test_scripts: list[ScriptEntry] = []
        if request_id is not None and scripts_enabled():
            pre_scripts, test_scripts = ScriptService.build_script_chain(int(request_id))

        method: str = req.get("method", "GET")
        url: str = req.get("url", "")
        headers: dict[str, str] = req.get("headers") or {}
        body: str = req.get("body") or ""

        # Build substitution scope: data-file row first, env vars override on key clash.
        env = self._environment_vars
        scope: dict[str, str] = {}
        if iter_data:
            scope.update({str(k): str(v) for k, v in iter_data.items()})
        if env:
            scope.update(env)
        if scope:
            url = _substitute(url, scope)
            headers = {_substitute(k, scope): _substitute(v, scope) for k, v in headers.items()}
            body = _substitute(body, scope)

        info: dict[str, Any] = {
            "requestName": req.get("name", ""),
            "requestId": str(request_id or ""),
            "iteration": iteration,
            "iterationCount": iteration_count,
        }
        all_console: list[Any] = []
        pre_request_errors: list[Any] = []
        pre_console_logs: list[Any] = []
        pre_var_changes: dict[str, str] = {}
        skip_request = False
        global_vars = load_globals() if (pre_scripts or test_scripts) else {}

        if pre_scripts:
            ctx = build_pre_request_context(
                method=method,
                url=url,
                headers=headers,
                body=body,
                variables=variables,
                environment_vars=self._environment_vars,
                collection_vars={},
                global_vars=global_vars,
                info=info,
                iteration_data=iter_data or None,
            )
            pre_out = ScriptEngine.run_pre_request_scripts(pre_scripts, ctx)
            pre_console_logs = list(pre_out.get("console_logs", []))
            all_console.extend(pre_console_logs)
            # Pre-request runtime errors go to console + separate list.
            for tr in pre_out.get("test_results", []):
                if tr.get("name") == "(runtime error)":
                    source = tr.get("source_name", "pre-request")
                    error = tr.get("error", "unknown error")
                    pre_request_errors.append(tr)
                    all_console.append(
                        {
                            "level": "error",
                            "message": f"[{source}] {error}",
                            "timestamp": 0,
                        }
                    )
            mutations = pre_out.get("request_mutations")
            if mutations:
                url = mutations.get("url", url)
                method = mutations.get("method", method)
                headers = mutations.get("headers", headers)
                body = mutations.get("body", body)
            if pre_out.get("global_variable_changes"):
                save_globals(pre_out["global_variable_changes"])
                global_vars.update(pre_out["global_variable_changes"])
            if pre_out.get("variable_changes"):
                pre_var_changes = dict(pre_out["variable_changes"])
            if pre_out.get("skip_request"):
                skip_request = True

        if skip_request:
            result_dict: dict[str, Any] = {
                "name": req.get("name", ""),
                "method": method,
                "status_code": 0,
                "elapsed_ms": 0,
                "body": "",
                "headers": [],
                "_skipped": True,
            }
        else:
            headers_str: str | None = (
                "\n".join(f"{k}: {v}" for k, v in headers.items()) if headers else None
            )
            result = HttpService.send_request(
                method=method,
                url=url,
                headers=headers_str,
                body=body or None,
            )
            result_dict = dict(result)
            result_dict["name"] = req.get("name", "")
            result_dict["method"] = method

        all_test_results: list[Any] = []
        next_request: Any = _SENTINEL
        if test_scripts and not skip_request:
            test_ctx = build_test_context(
                request_data={
                    "url": url,
                    "method": method,
                    "headers": headers,
                    "body": body,
                },
                response_data=result_dict,
                variables=variables,
                environment_vars=self._environment_vars,
                collection_vars={},
                global_vars=global_vars,
                info=info,
                iteration_data=iter_data or None,
            )
            test_out = ScriptEngine.run_test_scripts(test_scripts, test_ctx)
            all_test_results.extend(test_out.get("test_results", []))
            all_console.extend(test_out.get("console_logs", []))
            if test_out.get("global_variable_changes"):
                save_globals(test_out["global_variable_changes"])
            if "next_request" in test_out:
                next_request = test_out.get("next_request")

        result_dict["test_results"] = all_test_results
        result_dict["console_logs"] = all_console
        if pre_request_errors:
            result_dict["pre_request_errors"] = pre_request_errors
        if pre_console_logs:
            result_dict["pre_request_console_logs"] = pre_console_logs
        if pre_var_changes:
            result_dict["pre_request_variable_changes"] = pre_var_changes
        if pre_scripts:
            result_dict["has_pre_request_scripts"] = True
        if next_request is not _SENTINEL:
            result_dict["_next_request"] = next_request
        return result_dict
