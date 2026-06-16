"""AI / LLM provider configuration services.

Re-exports the public API so callers import from one place::

    from services.ai import AiConfig, AiLlmService, provider_by_key
"""

from __future__ import annotations

from services.ai.ai_budget_config import AiBudgetConfig, ProviderBudgetEntry
from services.ai.ai_config import AiConfig, AiModelEntry
from services.ai.chat import (
    AiChatMessageDict,
    AiChatSessionDict,
    AiChatSessionService,
    DEFAULT_AGENT_ID,
)
from services.ai.llm_service import AiLlmService
from services.ai.ops import fetch_provider_models, setup_provider, verify_provider_connection
from services.ai.provider_catalog import (
    PROVIDERS,
    ModelSpec,
    ProviderSpec,
    capability_text,
    probe_model_for_provider,
    provider_by_key,
)

__all__ = [
    "DEFAULT_AGENT_ID",
    "PROVIDERS",
    "AiBudgetConfig",
    "AiChatMessageDict",
    "AiChatSessionDict",
    "AiChatSessionService",
    "AiConfig",
    "AiLlmService",
    "AiModelEntry",
    "ModelSpec",
    "ProviderBudgetEntry",
    "ProviderSpec",
    "capability_text",
    "fetch_provider_models",
    "probe_model_for_provider",
    "provider_by_key",
    "setup_provider",
    "verify_provider_connection",
]
