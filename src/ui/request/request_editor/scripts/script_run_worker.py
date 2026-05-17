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
from services.scripting.context import build_pre_request_context, build_test_context
from services.scripting.debug import DebugProtocol


def build_inline_context(
    *,
    script_type: str,
    response_data: dict[str, Any] | None = None,
    environment_vars: dict[str, str] | None = None,
    collection_vars: dict[str, str] | None = None,
) -> ScriptInput:
    """Build a minimal ``ScriptInput`` for inline script execution.

    *script_type*: ``"pre_request"`` or ``"test"``.

    For pre-request scripts, creates a synthetic request and sets
    ``response`` to ``None``.  For test scripts, uses the supplied
    *response_data* (or a minimal empty response).
    """
    info: dict[str, Any] = {"requestName": "(inline run)", "iteration": 1}
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
            "url": "https://example.com",
            "method": "GET",
            "headers": {},
            "body": "",
        }
        return build_test_context(
            request_data=request_data,
            response_data=resp,
            variables={},
            environment_vars=env,
            collection_vars=coll,
            info=info,
        )

    return build_pre_request_context(
        method="GET",
        url="https://example.com",
        headers={},
        body="",
        variables={},
        environment_vars=env,
        collection_vars=coll,
        info=info,
    )


class ScriptRunWorker(QObject):
    """Run a script on a background thread and emit results.

    Create, configure via ``set_params()``, move to a ``QThread``,
    connect signals, and start.  Single-use — discard after completion.

    Signals:
        finished(object, float): ``(ScriptOutput, elapsed_ms)`` on success.
        error(str): Error message on failure.
    """

    # ``object`` avoids PySide6 converting ``dict`` via QVariantMap (nested
    # lists/structures can be lost when crossing the meta-object border).
    finished = Signal(object, float)
    error = Signal(str)

    def __init__(self) -> None:
        """Initialise with empty parameters."""
        super().__init__()
        self._script: str = ""
        self._language: str = "javascript"
        self._context: ScriptInput | None = None

    def set_params(
        self,
        *,
        script: str,
        language: str,
        context: ScriptInput,
    ) -> None:
        """Configure the script to run.

        Must be called **before** ``moveToThread()``.
        """
        self._script = script
        self._language = language
        self._context = context

    @Slot()
    def run(self) -> None:
        """Execute the script and emit results."""
        if self._context is None:
            self.error.emit("No script context configured")
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
            self.error.emit(str(exc))
