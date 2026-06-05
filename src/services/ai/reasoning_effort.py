"""Reasoning-effort vocabulary and helpers for AI model metadata."""

from __future__ import annotations

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


def is_boolean_thinking_efforts(efforts: tuple[str, ...] | list[str]) -> bool:
    """True when *efforts* are only Ollama boolean thinking tokens (off/on)."""
    normalized = {str(e).strip().lower() for e in efforts if str(e).strip()}
    return bool(normalized) and normalized <= {"off", "on"}


__all__ = [
    "OLLAMA_BOOLEAN_DEFAULT",
    "OLLAMA_BOOLEAN_LEVELS",
    "OLLAMA_HARMONY_DEFAULT",
    "OLLAMA_HARMONY_LEVELS",
    "REASONING_DEFAULT",
    "REASONING_EFFORT_ORDER",
    "clamp_effort",
    "default_effort_for",
    "format_reasoning_effort",
    "is_boolean_thinking_efforts",
    "normalize_efforts",
    "ollama_reasoning_from_show",
    "ollama_thinking_from_show",
]
