"""Background worker for inline script execution.

Runs a single script on a ``QThread`` using ``ScriptEngine.run_single()``
and emits the result (or error) via signals.  Used by the inline "Run"
button in the scripts mixin.
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from services.scripting import ScriptEngine, ScriptInput
from services.scripting.context import build_pre_request_context, build_test_context


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
        finished(dict, float): ``(ScriptOutput, elapsed_ms)`` on success.
        error(str): Error message on failure.
    """

    finished = Signal(dict, float)
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
            self.error.emit(str(exc))
