"""Keep only models suitable for OpenHands-style agents (text + tool calling)."""

from __future__ import annotations

import logging

from services.ai.provider_catalog import ModelSpec

logger = logging.getLogger(__name__)

_NON_CHAT_ID_MARKERS: tuple[str, ...] = (
    "embed",
    "embedding",
    "whisper",
    "tts",
    "dall-e",
    "dalle",
    "moderation",
    "realtime",
    "transcribe",
    "ocr",
    "sora",
    "audio",
    "image-generation",
    "nomic-embed",
    "mxbai-embed",
    "bge-",
    "snowflake-arctic-embed",
)


def _id_looks_non_chat(model_id: str) -> bool:
    low = model_id.lower()
    return any(marker in low for marker in _NON_CHAT_ID_MARKERS)


def _litellm_agent_caps(model_id: str) -> tuple[bool, bool] | None:
    """Return ``(text_ok, tools_ok)`` from LiteLLM when known."""
    try:
        import litellm
    except ImportError:
        return None
    if _id_looks_non_chat(model_id):
        return False, False
    try:
        tools = bool(litellm.supports_function_calling(model=model_id))
    except Exception:
        tools = False
    # LiteLLM has no single "text-only" flag; non-chat ids are already excluded.
    return True, tools


def litellm_supports_vision(model_id: str) -> bool:
    """Whether LiteLLM marks *model_id* as vision-capable."""
    try:
        import litellm
    except ImportError:
        return False
    try:
        return bool(litellm.supports_vision(model=model_id))
    except Exception:
        return False


def _openrouter_caps(row: dict[str, object]) -> tuple[bool, bool, bool]:
    arch = row.get("architecture")
    if not isinstance(arch, dict):
        return True, False, False
    inputs = arch.get("input_modalities")
    outputs = arch.get("output_modalities")
    in_set = {str(x).lower() for x in inputs} if isinstance(inputs, list) else set()
    out_set = {str(x).lower() for x in outputs} if isinstance(outputs, list) else set()
    text_ok = "text" in in_set and "text" in out_set
    vision_ok = "image" in in_set
    params = row.get("supported_parameters")
    param_set = {str(p).lower() for p in params} if isinstance(params, list) else set()
    tools_ok = "tools" in param_set or bool(arch.get("supports_tool_calling"))
    return text_ok, tools_ok, vision_ok


def filter_agent_capable(models: tuple[ModelSpec, ...]) -> tuple[ModelSpec, ...]:
    """Drop models without text completion and tool/function calling support."""
    return tuple(m for m in models if m.text and m.tools)


def filter_settings_models(models: tuple[ModelSpec, ...]) -> tuple[ModelSpec, ...]:
    """Drop non-chat and non-tool models (OpenHands requires tool calling)."""
    chat = tuple(m for m in models if m.text and not _id_looks_non_chat(m.model))
    return filter_agent_capable(chat)


def capability_bits_for_model(model_id: str) -> tuple[int, bool, bool, bool]:
    """Return ``(context_guess, tools, vision, text)`` for display in the settings tree."""
    caps = _litellm_agent_caps(model_id)
    text_ok = caps[0] if caps else True
    tools_ok = caps[1] if caps else False
    return 0, tools_ok, False, text_ok


__all__ = [
    "capability_bits_for_model",
    "filter_agent_capable",
    "filter_settings_models",
    "litellm_supports_vision",
]
