"""Background worker for inline script execution.

Runs a single script on a ``QThread`` using ``ScriptEngine.run_single()``
and emits the result (or error) via signals.  Used by the inline "Run"
button in the scripts mixin.
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from services.scripting import ScriptEngine, ScriptEntry, ScriptInput
from services.scripting.context import (
    build_pre_request_context,
    build_script_info,
    build_test_context,
)
from services.scripting.debug import DebugProtocol


def build_inline_context(
    *,
    script_type: str,
    response_data: dict[str, Any] | None = None,
    environment_vars: dict[str, str] | None = None,
    collection_vars: dict[str, str] | None = None,
    test_name_filter: str | None = None,
    iteration: int = 0,
    iteration_count: int = 1,
    iteration_data: dict[str, Any] | None = None,
    request_name: str = "(inline run)",
    request_id: str = "",
    environment_name: str = "",
    auth: dict[str, Any] | None = None,
    request_url: str | None = None,
    request_method: str | None = None,
    request_headers: dict[str, str] | None = None,
    request_body: str | None = None,
) -> ScriptInput:
    """Build a minimal ``ScriptInput`` for inline script execution.

    *script_type*: ``"pre_request"`` or ``"test"``.

    For pre-request scripts, creates a synthetic request and sets
    ``response`` to ``None``.  For test scripts, uses the supplied
    *response_data* (or a minimal empty response).
    """
    event_name = "prerequest" if script_type == "pre_request" else "test"
    info = build_script_info(
        event_name=event_name,
        request_name=request_name,
        request_id=request_id,
        iteration=iteration,
        iteration_count=iteration_count,
        test_filter=test_name_filter,
    )
    env = dict(environment_vars) if environment_vars else {}
    coll = dict(collection_vars) if collection_vars else {}

    if script_type == "test":
        resp = (
            dict(response_data)
            if response_data
            else {
                "code": 200,
                "status": "200",
                "headers": [],
                "body": "",
                "responseTime": 0,
                "responseSize": 0,
            }
        )
        request_data: dict[str, Any] = {
            "url": request_url or "https://example.com",
            "method": request_method or "GET",
            "headers": dict(request_headers) if request_headers else {},
            "body": request_body or "",
        }
        if auth is not None:
            request_data["auth"] = auth
        return build_test_context(
            request_data=request_data,
            response_data=resp,
            variables={},
            environment_vars=env,
            collection_vars=coll,
            info=info,
            iteration_data=iteration_data,
            environment_name=environment_name,
        )

    req_headers = dict(request_headers) if request_headers else {}
    return build_pre_request_context(
        method=request_method or "GET",
        url=request_url or "https://example.com",
        headers=req_headers,
        body=request_body or "",
        variables={},
        environment_vars=env,
        collection_vars=coll,
        info=info,
        iteration_data=iteration_data,
        auth=auth,
        environment_name=environment_name,
    )


class ScriptRunWorker(QObject):
    """Run a script on a background thread and emit results.

    Create, configure via ``set_params()``, move to a ``QThread``,
    connect signals, and start.  Single-use — discard after completion.

    Signals:
        finished(object, float): ``(ScriptOutput | list[ScriptOutput], elapsed_ms)``.
        iteration_finished(int, object, float): Per-row ``(index, ScriptOutput, elapsed_ms)``.
        error(str): Error message on failure.
    """

    # ``object`` avoids PySide6 converting ``dict`` via QVariantMap (nested
    # lists/structures can be lost when crossing the meta-object border).
    finished = Signal(object, float)
    iteration_finished = Signal(int, object, float)
    error = Signal(str)

    def __init__(self) -> None:
        """Initialise with empty parameters."""
        super().__init__()
        self._script: str = ""
        self._language: str = "javascript"
        self._context: ScriptInput | None = None
        self._test_name_filter: str | None = None
        self._iteration_data: list[dict[str, Any]] | None = None
        self._iteration_count: int = 1

    def set_params(
        self,
        *,
        script: str,
        language: str,
        context: ScriptInput,
        test_name_filter: str | None = None,
    ) -> None:
        """Configure the script to run.

        Must be called **before** ``moveToThread()``.
        """
        self._script = script
        self._language = language
        self._context = context
        self._test_name_filter = test_name_filter
        if test_name_filter and self._context is not None:
            ctx = dict(self._context)
            info_raw = ctx.get("info", {})
            info = dict(info_raw) if isinstance(info_raw, dict) else {}
            info["testFilter"] = test_name_filter
            ctx["info"] = info
            self._context = ctx  # type: ignore[assignment]

    def set_iteration_data(
        self,
        data: list[dict[str, Any]],
        *,
        count: int | None = None,
    ) -> None:
        """Configure data-driven iterations (call before ``moveToThread()``)."""
        self._iteration_data = list(data)
        self._iteration_count = max(1, count if count is not None else len(data))

    @Slot()
    def run(self) -> None:
        """Execute the script and emit results."""
        if self._context is None:
            self.error.emit("No script context configured")
            return

        if self._iteration_data:
            self._run_iterations()
            return

        start = time.perf_counter()
        try:
            result = ScriptEngine.run_single(
                self._script,
                self._language,
                self._context,
            )
            elapsed = (time.perf_counter() - start) * 1000.0
            self.finished.emit(result, elapsed)
        except Exception as exc:
            self.error.emit(str(exc))

    def _run_iterations(self) -> None:
        """Run the script once per data row and stream matrix updates."""
        assert self._context is not None
        assert self._iteration_data is not None

        rows = self._iteration_data
        total = max(self._iteration_count, len(rows))
        base_ctx = dict(self._context)
        info_raw = base_ctx.get("info", {})
        info_base = dict(info_raw) if isinstance(info_raw, dict) else {}
        request_name = str(info_base.get("requestName", "(inline run)"))
        request_id = str(info_base.get("requestId", ""))
        event_name = str(info_base.get("eventName", "test"))
        results: list[Any] = []
        start_all = time.perf_counter()

        try:
            for idx in range(total):
                row = rows[idx] if idx < len(rows) else {}
                ctx = dict(base_ctx)
                info = build_script_info(
                    event_name=event_name,
                    request_name=request_name,
                    request_id=request_id,
                    iteration=idx,
                    iteration_count=total,
                    test_filter=str(info_base["testFilter"])
                    if info_base.get("testFilter")
                    else None,
                )
                ctx["info"] = info
                ctx["iteration_data"] = row

                iter_start = time.perf_counter()
                result = ScriptEngine.run_single(
                    self._script,
                    self._language,
                    ctx,  # type: ignore[arg-type]
                )
                elapsed = (time.perf_counter() - iter_start) * 1000.0
                results.append(result)
                self.iteration_finished.emit(idx, result, elapsed)
        except Exception as exc:
            self.error.emit(str(exc))
            return

        total_elapsed = (time.perf_counter() - start_all) * 1000.0
        self.finished.emit(results, total_elapsed)


class ScriptChainRunWorker(QObject):
    """Run a pre-request or test script chain on a background thread.

    Mirrors :class:`ScriptRunWorker` but dispatches to
    :meth:`ScriptEngine.run_pre_request_scripts` /
    :meth:`run_test_scripts` so inherited + current scripts execute as a
    merged chain — same semantics as the live Send path.
    """

    finished = Signal(object, float)
    error = Signal(str)

    def __init__(self) -> None:
        """Initialise empty chain state (call ``set_params`` before ``run``)."""
        super().__init__()
        self._chain: list[ScriptEntry] = []
        self._script_type: str = "pre_request"
        self._context: ScriptInput | None = None

    def set_params(
        self,
        *,
        chain: list[ScriptEntry],
        script_type: str,
        context: ScriptInput,
    ) -> None:
        """Configure chain + context. Call before ``moveToThread()``."""
        self._chain = list(chain)
        self._script_type = script_type
        self._context = context

    @Slot()
    def run(self) -> None:
        """Execute the chain and emit merged results."""
        if self._context is None:
            self.error.emit("No script context configured")
            return
        start = time.perf_counter()
        try:
            if self._script_type == "test":
                result = ScriptEngine.run_test_scripts(self._chain, self._context)
            else:
                result = ScriptEngine.run_pre_request_scripts(self._chain, self._context)
            elapsed = (time.perf_counter() - start) * 1000.0
            self.finished.emit(result, elapsed)
        except Exception as exc:
            self.error.emit(str(exc))


class ScriptDebugWorker(QObject):
    """Run a single script on a background thread with :class:`DebugProtocol`.

    Mirrors the debug path in :class:`~ui.request.http_worker.HttpSendWorker`
    (``protocol.start`` then ``run_debug_chain``) so the UI can handle pauses and resume.
    """

    # ``object`` avoids PySide6 converting ``dict`` via QVariantMap (nested
    # lists/structures can be lost when crossing the meta-object border).
    finished = Signal(object, float)
    error = Signal(str)
    debug_paused = Signal(object)

    def __init__(self) -> None:
        """Initialise with empty parameters."""
        super().__init__()
        self._script: str = ""
        self._language: str = "javascript"
        self._context: ScriptInput | None = None
        self._protocol: DebugProtocol | None = None
        self._script_type: str = "pre_request"

    def set_params(
        self,
        *,
        script: str,
        language: str,
        context: ScriptInput,
        protocol: DebugProtocol,
        script_type: str,
    ) -> None:
        """Configure the script, context, and protocol. Call before ``moveToThread()``."""
        self._script = script
        self._language = language
        self._context = context
        self._protocol = protocol
        self._script_type = script_type

    @Slot()
    def run(self) -> None:
        """Execute the script in debug mode and emit results."""
        if self._context is None or self._protocol is None:
            self.error.emit("Debug worker not configured")
            return

        from services.scripting.engine import run_debug_chain

        self._protocol.start(
            on_pause=lambda info: self.debug_paused.emit(info),
        )

        entry: ScriptEntry = {
            "code": self._script,
            "language": self._language,
            "source_name": "(inline debug)",
        }
        start = time.perf_counter()
        try:
            result = run_debug_chain(
                [entry],
                self._context,
                self._protocol,
                script_type=self._script_type,
            )
            elapsed = (time.perf_counter() - start) * 1000.0
            self.finished.emit(result, elapsed)
        except Exception as exc:
            self.error.emit(str(exc))
