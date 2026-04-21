"""Script execution engine package.

Re-exports public TypedDicts and runtime classes so callers can import
from a single location::

    from services.scripting import ScriptEngine, TestResult, ScriptOutput
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from services.scripting.deno_manager import DenoManager
from services.scripting.engine import ScriptEngine, ScriptLinter
from services.scripting.feature_detect import (
    FEATURE_ASYNC,
    FEATURE_NPM,
    detect_advanced_features,
)


class TestResult(TypedDict):
    """Single test assertion result from ``pm.test()``."""

    name: str
    passed: bool
    error: str | None
    duration_ms: float
    source_name: NotRequired[str]


class ConsoleLog(TypedDict):
    """Single console output line captured from script execution."""

    level: str  # "log", "warn", "error", "info"
    message: str
    timestamp: float


class ScriptInput(TypedDict):
    """Data injected into the script runtime before execution."""

    request: dict[str, Any]
    response: dict[str, Any] | None
    variables: dict[str, str]
    environment_vars: dict[str, str]
    collection_vars: dict[str, str]
    global_vars: NotRequired[dict[str, str]]
    info: dict[str, Any]
    iteration_data: NotRequired[dict[str, Any]]


class ScriptOutput(TypedDict):
    """Accumulated results extracted from the script runtime after execution."""

    test_results: list[TestResult]
    console_logs: list[ConsoleLog]
    variable_changes: dict[str, str]
    global_variable_changes: NotRequired[dict[str, str]]
    request_mutations: dict[str, Any] | None
    next_request: NotRequired[str | None]
    skip_request: NotRequired[bool]


class ScriptEntry(TypedDict):
    """Single script in an inheritance chain."""

    code: str
    language: str
    source_name: str


__all__ = [
    "FEATURE_ASYNC",
    "FEATURE_NPM",
    "ConsoleLog",
    "DenoManager",
    "ScriptEngine",
    "ScriptEntry",
    "ScriptInput",
    "ScriptLinter",
    "ScriptOutput",
    "TestResult",
    "detect_advanced_features",
]
