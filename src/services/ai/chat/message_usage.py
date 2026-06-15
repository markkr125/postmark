"""Per-message token usage deltas and cost formatting for assistant turns."""

from __future__ import annotations

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


def resolve_model_display_name(model_id: str | None, entry: AiModelEntry | None) -> str:
    """Return a human-readable model label for footer display."""
    if entry is not None:
        label = str(entry.get("label") or "").strip()
        if label:
            return label
        model = str(entry.get("model") or "").strip()
        if model:
            return model
    if model_id:
        for candidate in AiConfig.get_models():
            if candidate.get("id") == model_id:
                label = str(candidate.get("label") or "").strip()
                if label:
                    return label
                model = str(candidate.get("model") or "").strip()
                if model:
                    return model
                break
    return "Unknown model"


def format_assistant_footer_label(
    entry: AiModelEntry | None,
    model_id: str | None,
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    reasoning_tokens: int | None,
) -> str:
    """Build footer text: model name plus turn cost when pricing is known."""
    name = resolve_model_display_name(model_id, entry)
    prompt = int(prompt_tokens or 0)
    completion = int(completion_tokens or 0)
    reasoning = int(reasoning_tokens or 0)
    if prompt <= 0 and completion <= 0 and reasoning <= 0:
        return name
    cost = message_turn_cost_usd(
        entry,
        prompt_tokens=prompt,
        completion_tokens=completion,
        reasoning_tokens=reasoning,
    )
    if cost is None:
        return name
    return f"{name} · {_format_usd_amount(cost)}"


__all__ = [
    "format_assistant_footer_label",
    "message_turn_cost_usd",
    "resolve_model_display_name",
    "turn_usage_delta",
]
