"""Reasoning-effort vocabulary and helpers for AI model metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.ai.ai_config import AiModelEntry

# Ollama boolean thinking uses off/on; LiteLLM uses none/minimal/low/medium/high/xhigh/max.
REASONING_EFFORT_ORDER: tuple[str, ...] = (
    "off",
    "on",
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)
REASONING_DEFAULT = "medium"

# Ollama Harmony (gpt-oss): leveled thinking, trace cannot be disabled.
OLLAMA_HARMONY_LEVELS: tuple[str, ...] = ("low", "medium", "high")
OLLAMA_HARMONY_DEFAULT = "medium"

# Other Ollama thinking models: boolean think true/false (default on per Ollama docs).
OLLAMA_BOOLEAN_LEVELS: tuple[str, ...] = ("off", "on")
OLLAMA_BOOLEAN_DEFAULT = "on"


def format_reasoning_effort(effort: str) -> str:
    """Human-readable label for an effort token (e.g. ``high`` -> ``High``)."""
    key = effort.strip().lower()
    if not key:
        return "—"
    if key == "off":
        return "Off"
    if key == "on":
        return "On"
    if key == "xhigh":
        return "Extra High"
    return key.capitalize()


def normalize_efforts(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Return *values* ordered and deduplicated per :data:`REASONING_EFFORT_ORDER`."""
    seen: set[str] = set()
    ordered: list[str] = []
    for token in REASONING_EFFORT_ORDER:
        if token in values and token not in seen:
            seen.add(token)
            ordered.append(token)
    return tuple(ordered)


def default_effort_for(efforts: tuple[str, ...]) -> str:
    """Pick a sensible default from *efforts* (prefer ``medium``)."""
    if not efforts:
        return REASONING_DEFAULT
    if "medium" in efforts:
        return "medium"
    if "on" in efforts:
        return "on"
    if "off" in efforts:
        return "off"
    mid = len(efforts) // 2
    return efforts[mid]


def clamp_effort(effort: str | None, efforts: tuple[str, ...], default: str) -> str:
    """Return *effort* if allowed, else *default* or :func:`default_effort_for`."""
    normalized = normalize_efforts(efforts)
    if not normalized:
        return REASONING_DEFAULT
    key = (effort or "").strip().lower()
    if key and key in normalized:
        return key
    fallback = default.strip().lower() if default else ""
    if fallback and fallback in normalized:
        return fallback
    return default_effort_for(normalized)


def ollama_thinking_from_show(data: dict[str, object]) -> tuple[bool, str]:
    """Return whether the model supports thinking and its default (``on``/``off``)."""
    caps = data.get("capabilities")
    if not isinstance(caps, list) or "thinking" not in {str(c).lower() for c in caps}:
        return False, ""
    return True, OLLAMA_BOOLEAN_DEFAULT


def ollama_reasoning_from_show(
    data: dict[str, object], raw_name: str
) -> tuple[bool, tuple[str, ...], str]:
    """Infer leveled reasoning (gpt-oss / Harmony only) from Ollama ``/api/show``."""
    caps = data.get("capabilities")
    if not isinstance(caps, list) or "thinking" not in {str(c).lower() for c in caps}:
        return False, (), ""
    low = raw_name.lower()
    if "gpt-oss" in low or "gpt_oss" in low:
        return True, OLLAMA_HARMONY_LEVELS, OLLAMA_HARMONY_DEFAULT
    return False, (), ""


def leveled_reasoning_efforts(entry: AiModelEntry | dict[str, object]) -> tuple[str, ...]:
    """Leveled reasoning efforts on *entry* (excludes boolean thinking off/on)."""
    raw = entry.get("reasoning_efforts")
    if not isinstance(raw, list):
        return ()
    levels = tuple(str(e).strip().lower() for e in raw if isinstance(e, str) and str(e).strip())
    if is_boolean_thinking_efforts(levels):
        return ()
    return levels


def _is_ollama_model(entry: AiModelEntry | dict[str, object]) -> bool:
    """True when *entry* targets a local Ollama model."""
    model = str(entry.get("model", "")).lower()
    provider = str(entry.get("provider", "")).lower()
    return provider == "ollama" or model.startswith("ollama/")


def is_ollama_harmony_model(entry: AiModelEntry | dict[str, object]) -> bool:
    """True for Ollama gpt-oss / Harmony models that use leveled think."""
    model = str(entry.get("model", "")).lower()
    return "gpt-oss" in model or "gpt_oss" in model


def chat_reasoning_effort_for_litellm(
    entry: AiModelEntry | dict[str, object],
    effort: str | None,
    *,
    streaming: bool = True,
) -> str | None:
    """Return a LiteLLM ``reasoning_effort`` for chat, or ``None`` to omit.

    Ollama Harmony (gpt-oss) only accepts low/medium/high. Streaming chat with
    ``think`` currently breaks some LiteLLM + Ollama combinations, so reasoning
    is omitted for Ollama models when *streaming* is True.
    """
    if not effort or not str(effort).strip():
        return None
    token = str(effort).strip().lower()
    if is_ollama_harmony_model(entry):
        if streaming:
            return None
        if token in OLLAMA_HARMONY_LEVELS:
            return token
        if token in ("xhigh", "max"):
            return "high"
        if token in ("minimal", "none", "off"):
            return "low"
        return OLLAMA_HARMONY_DEFAULT
    if _is_ollama_model(entry) and streaming:
        return None
    levels = leveled_reasoning_efforts(entry)
    if levels:
        return clamp_effort(
            token,
            levels,
            str(entry.get("reasoning_default", "")),
        )
    return token


def is_boolean_thinking_efforts(efforts: tuple[str, ...] | list[str]) -> bool:
    """True when *efforts* are only Ollama boolean thinking tokens (off/on)."""
    normalized = {str(e).strip().lower() for e in efforts if str(e).strip()}
    return bool(normalized) and normalized <= {"off", "on"}


def ollama_chat_litellm_extra_body(
    entry: AiModelEntry | dict[str, object],
    *,
    run_context_tokens: int | None = None,
    thinking_enabled: str | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, object]:
    """Build LiteLLM ``extra_body`` fields for Ollama ``/api/chat`` runs.

    ``num_ctx`` and ``think`` are passed at the top level; LiteLLM maps them into
    the Ollama request (``options.num_ctx`` and ``think`` respectively).
    """
    body: dict[str, object] = {}
    if run_context_tokens is not None and run_context_tokens > 0:
        body["num_ctx"] = run_context_tokens

    if is_ollama_harmony_model(entry):
        effort = chat_reasoning_effort_for_litellm(
            entry,
            reasoning_effort,
            streaming=False,
        )
        if effort is not None:
            body["think"] = effort
        return body

    if entry.get("thinking") and thinking_enabled is not None:
        key = str(thinking_enabled).strip().lower()
        if key == "off":
            body["think"] = False
        elif key == "on":
            body["think"] = True
    return body


__all__ = [
    "OLLAMA_BOOLEAN_DEFAULT",
    "OLLAMA_BOOLEAN_LEVELS",
    "OLLAMA_HARMONY_DEFAULT",
    "OLLAMA_HARMONY_LEVELS",
    "REASONING_DEFAULT",
    "REASONING_EFFORT_ORDER",
    "chat_reasoning_effort_for_litellm",
    "clamp_effort",
    "default_effort_for",
    "format_reasoning_effort",
    "is_boolean_thinking_efforts",
    "is_ollama_harmony_model",
    "leveled_reasoning_efforts",
    "normalize_efforts",
    "ollama_chat_litellm_extra_body",
    "ollama_reasoning_from_show",
    "ollama_thinking_from_show",
]
