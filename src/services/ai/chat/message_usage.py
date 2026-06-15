"""Per-message token usage deltas and cost formatting for assistant turns."""

from __future__ import annotations

from collections.abc import Iterable

from services.ai.ai_config import AiConfig, AiModelEntry
from services.ai.chat.context_usage import ContextUsageSdkMetrics
from services.ai.provider_catalog import cost_per_token_for_entry

_ZERO_USAGE: ContextUsageSdkMetrics = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "reasoning_tokens": 0,
}


def _usage_int(metrics: ContextUsageSdkMetrics | dict[str, int] | None, key: str) -> int:
    """Return one non-negative usage counter from a metrics dict."""
    if metrics is None:
        return 0
    raw = metrics.get(key)  # type: ignore[union-attr]
    if isinstance(raw, int) and raw > 0:
        return raw
    return 0


def turn_usage_delta(
    sdk: ContextUsageSdkMetrics,
    previous_cumulative: ContextUsageSdkMetrics | dict[str, int] | None,
) -> ContextUsageSdkMetrics:
    """Subtract prior assistant turn totals from SDK cumulative session usage."""
    prev = previous_cumulative or _ZERO_USAGE
    prompt = max(0, _usage_int(sdk, "prompt_tokens") - _usage_int(prev, "prompt_tokens"))
    completion = max(
        0,
        _usage_int(sdk, "completion_tokens") - _usage_int(prev, "completion_tokens"),
    )
    reasoning = max(
        0,
        _usage_int(sdk, "reasoning_tokens") - _usage_int(prev, "reasoning_tokens"),
    )
    return ContextUsageSdkMetrics(
        prompt_tokens=prompt,
        completion_tokens=completion,
        reasoning_tokens=reasoning,
    )


def message_turn_cost_usd(
    entry: AiModelEntry | None,
    *,
    prompt_tokens: int,
    completion_tokens: int,
    reasoning_tokens: int,
) -> float | None:
    """Return USD cost for one assistant turn, or ``None`` when pricing is unknown."""
    if entry is None:
        return None
    inp, out = cost_per_token_for_entry(entry)
    if inp <= 0 and out <= 0:
        return None
    total = prompt_tokens * inp + (completion_tokens + reasoning_tokens) * out
    if total <= 0:
        return None
    return total


def _format_usd_amount(usd: float) -> str:
    """Format a small USD amount for the assistant footer."""
    if usd >= 0.01:
        text = f"{usd:.3f}"
    elif usd >= 0.001:
        text = f"{usd:.4f}"
    else:
        text = f"{usd:.5f}"
    return f"${text.rstrip('0').rstrip('.')}"


def effective_assistant_model_id(
    message_model_id: str | None,
    session_model_id: str | None = None,
) -> str | None:
    """Return the model id to display for an assistant row."""
    if message_model_id:
        return message_model_id
    return session_model_id


def entry_for_model_id(
    model_id: str | None,
    *,
    extra_entries: Iterable[AiModelEntry] | None = None,
) -> AiModelEntry | None:
    """Return the configured model entry for *model_id*, if present."""
    if not model_id:
        return None
    seen: set[str] = set()
    for candidate in (*tuple(extra_entries or ()), *AiConfig.get_models()):
        row_id = str(candidate.get("id") or "")
        if not row_id or row_id in seen:
            continue
        seen.add(row_id)
        if row_id == model_id:
            return candidate
    return None


def model_display_name_from_entry(entry: AiModelEntry | None) -> str | None:
    """Return the human-readable model label from a model entry."""
    if entry is None:
        return None
    label = str(entry.get("label") or "").strip()
    if label:
        return label
    model = str(entry.get("model") or "").strip()
    return model or None


def resolve_model_display_name(
    model_id: str | None,
    entry: AiModelEntry | None,
    *,
    extra_entries: Iterable[AiModelEntry] | None = None,
) -> str:
    """Return a human-readable model label for footer display."""
    resolved = entry_for_model_id(model_id, extra_entries=extra_entries) or entry
    if resolved is not None:
        name = model_display_name_from_entry(resolved)
        if name:
            return name
    if model_id:
        return model_id
    return "Unknown model"


def resolve_assistant_footer_name(
    *,
    model_label: str | None,
    model_id: str | None,
    entry: AiModelEntry | None = None,
    extra_entries: Iterable[AiModelEntry] | None = None,
) -> str:
    """Resolve footer model text from persisted label and/or model id."""
    stored = str(model_label or "").strip()
    if stored:
        return stored
    return resolve_model_display_name(model_id, entry, extra_entries=extra_entries)


def format_assistant_footer_label(
    entry: AiModelEntry | None,
    model_id: str | None,
    *,
    model_label: str | None = None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    reasoning_tokens: int | None,
    extra_entries: Iterable[AiModelEntry] | None = None,
) -> str:
    """Build footer text: model name plus turn cost when pricing is known."""
    resolved_entry = entry_for_model_id(model_id, extra_entries=extra_entries) or entry
    name = resolve_assistant_footer_name(
        model_label=model_label,
        model_id=model_id,
        entry=resolved_entry,
        extra_entries=extra_entries,
    )
    prompt = int(prompt_tokens or 0)
    completion = int(completion_tokens or 0)
    reasoning = int(reasoning_tokens or 0)
    if prompt <= 0 and completion <= 0 and reasoning <= 0:
        return name
    cost = message_turn_cost_usd(
        resolved_entry,
        prompt_tokens=prompt,
        completion_tokens=completion,
        reasoning_tokens=reasoning,
    )
    if cost is None:
        return name
    return f"{name} · {_format_usd_amount(cost)}"


__all__ = [
    "effective_assistant_model_id",
    "entry_for_model_id",
    "format_assistant_footer_label",
    "message_turn_cost_usd",
    "model_display_name_from_entry",
    "resolve_assistant_footer_name",
    "resolve_model_display_name",
    "turn_usage_delta",
]
