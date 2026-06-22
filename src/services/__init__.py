"""Service layer package.

Re-exports the main service classes so LLMs and IDE users can
discover the full public API from a single file read::

    from services import CollectionService, EnvironmentService

AI symbols are loaded lazily so RestrictedPython sandbox subprocesses that
import ``services.scripting`` do not pull OpenHands into every child process.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from services.ai.ai_budget_config import AiBudgetConfig, ProviderBudgetEntry
    from services.ai.ai_config import AiConfig, AiModelEntry
    from services.ai.chat import AiChatMessageDict, AiChatSessionDict, AiChatSessionService

_LAZY_AI_EXPORTS = frozenset(
    {
        "AiBudgetConfig",
        "AiChatMessageDict",
        "AiChatSessionDict",
        "AiChatSessionService",
        "AiConfig",
        "AiLlmService",
        "AiModelEntry",
        "ProviderBudgetEntry",
    }
)


def __getattr__(name: str) -> object:
    """Load AI service exports on first access."""
    if name in _LAZY_AI_EXPORTS:
        import services.ai as ai_mod

        return getattr(ai_mod, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "AiBudgetConfig",
    "AiChatMessageDict",
    "AiChatSessionDict",
    "AiChatSessionService",
    "AiConfig",
    "AiLlmService",
    "AiModelEntry",
    "CollectionService",
    "ConsoleLog",
    "EnvironmentService",
    "ImportService",
    "LocalOverride",
    "ProviderBudgetEntry",
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
