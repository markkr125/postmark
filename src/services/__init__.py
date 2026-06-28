"""Service layer package.

Re-exports the main service classes so LLMs and IDE users can
discover the full public API from a single file read::

    from services import CollectionService, EnvironmentService

When ``POSTMARK_SANDBOX=1`` (RestrictedPython subprocess worker), heavy
re-exports are skipped so ``import services.scripting…`` stays lightweight.
"""

from __future__ import annotations

import os

_SANDBOX = os.environ.get("POSTMARK_SANDBOX") == "1"

__all__: list[str]

if not _SANDBOX:
    from services.ai import (
        AiBudgetConfig,
        AiChatMessageDict,
        AiChatSessionDict,
        AiChatSessionService,
        AiConfig,
        AiLlmService,
        AiModelEntry,
        ProviderBudgetEntry,
    )
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
else:
    __all__ = []
