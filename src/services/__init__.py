"""Service layer package.

Re-exports the main service classes so LLMs and IDE users can
discover the full public API from a single file read::

    from services import CollectionService, EnvironmentService
"""

from __future__ import annotations

from services.collection_service import CollectionService, RequestLoadDict
from services.environment_service import EnvironmentService, LocalOverride, VariableDetail
from services.import_service import ImportService
from services.request_history_service import (
    RequestHistoryEntryDict,
    RequestHistoryService,
    SendIdentityDict,
)
from services.run_history_service import RunHistoryService
from services.script_service import ScriptService
from services.script_version_service import ScriptVersionService
from services.scripting import (
    ConsoleLog,
    ScriptEngine,
    ScriptEntry,
    ScriptInput,
    ScriptOutput,
    TestResult,
)

__all__ = [
    "CollectionService",
    "ConsoleLog",
    "EnvironmentService",
    "ImportService",
    "LocalOverride",
    "RequestHistoryEntryDict",
    "RequestHistoryService",
    "RequestLoadDict",
    "RunHistoryService",
    "ScriptEngine",
    "ScriptEntry",
    "ScriptInput",
    "ScriptOutput",
    "ScriptService",
    "ScriptVersionService",
    "SendIdentityDict",
    "TestResult",
    "VariableDetail",
]
