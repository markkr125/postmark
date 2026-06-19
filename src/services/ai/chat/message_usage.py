"""Per-message token usage deltas and cost formatting for assistant turns."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypedDict

from services.ai.ai_config import AiConfig, AiModelEntry
from services.ai.chat.context_usage import ContextUsageSdkMetrics
from services.ai.chat.session_service import AiChatMessageDict
from services.ai.provider_catalog import (
    cost_per_token_for_entry,
    format_run_context_tokens,
    provider_group_label,
)

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


def format_usd_amount(usd: float) -> str:
    """Format a small USD amount for UI labels."""
    return _format_usd_amount(usd)


def assistant_message_cost_usd(
    entry: AiModelEntry | None,
    *,
    prompt_tokens: int,
    completion_tokens: int,
    reasoning_tokens: int,
) -> float | None:
    """Return USD cost for one assistant message turn."""
    return message_turn_cost_usd(
        entry,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
    )


class ModelSpendRow(TypedDict):
    """Per-model spend rollup for one chat session."""

    model_id: str
    model_label: str
    provider_label: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cost_usd: float | None
    turn_count: int


# Backward-compatible alias — prefer ModelSpendRow for new code.
ProviderSpendRow = ModelSpendRow


class SessionSpendBreakdown(TypedDict):
    """Session-level spend rollup across assistant turns."""

    total_usd: float | None
    known_usd: float
    assistant_turns: int
    priced_turns: int
    partial: bool
    models: list[ModelSpendRow]


def pricing_model_id_for_assistant_message(
    msg: AiChatMessageDict,
    *,
    messages: list[AiChatMessageDict] | None = None,
    msg_index: int | None = None,
    session_model_id: str | None = None,
) -> str | None:
    """Resolve the configured model id used to price one assistant row."""
    mid = msg.get("model_id")
    if isinstance(mid, str) and mid.strip():
        return mid.strip()
    if messages is not None and msg_index is not None:
        for prior_index in range(msg_index - 1, -1, -1):
            prior = messages[prior_index]
            if prior.get("role") != "user":
                continue
            send_model_id = prior.get("send_model_id")
            if isinstance(send_model_id, str) and send_model_id.strip():
                return send_model_id.strip()
    if session_model_id:
        return session_model_id
    return None


def resolve_turn_model_id(
    msg: AiChatMessageDict,
    *,
    messages: list[AiChatMessageDict],
    msg_index: int,
    session_model_id: str | None = None,
) -> str | None:
    """Resolve the model id used to price one assistant turn."""
    return pricing_model_id_for_assistant_message(
        msg,
        messages=messages,
        msg_index=msg_index,
        session_model_id=session_model_id,
    )


def assistant_turn_cost_for_message(
    msg: AiChatMessageDict,
    *,
    messages: list[AiChatMessageDict],
    msg_index: int,
    session_model_id: str | None = None,
    models: list[AiModelEntry] | None = None,
) -> tuple[str | None, float | None]:
    """Return ``(pricing_model_id, usd_cost)`` for one assistant message row."""
    if msg.get("role") != "assistant" or not _assistant_turn_has_tokens(msg):
        return None, None
    model_list = list(models) if models is not None else list(AiConfig.get_models())
    model_id = pricing_model_id_for_assistant_message(
        msg,
        messages=messages,
        msg_index=msg_index,
        session_model_id=session_model_id,
    )
    stored_cost = msg.get("cost_usd")
    if isinstance(stored_cost, int | float):
        return model_id, float(stored_cost)
    entry = entry_for_model_id(model_id, extra_entries=model_list)
    cost = assistant_message_cost_usd(
        entry,
        prompt_tokens=int(msg.get("prompt_tokens") or 0),
        completion_tokens=int(msg.get("completion_tokens") or 0),
        reasoning_tokens=int(msg.get("reasoning_tokens") or 0),
    )
    return model_id, cost


def sum_assistant_turn_costs(
    messages: list[AiChatMessageDict],
    *,
    session_model_id: str | None = None,
    models: list[AiModelEntry] | None = None,
) -> float:
    """Sum priced USD for every assistant row (unrounded)."""
    total = 0.0
    for index, msg in enumerate(messages):
        _model_id, cost = assistant_turn_cost_for_message(
            msg,
            messages=messages,
            msg_index=index,
            session_model_id=session_model_id,
            models=models,
        )
        if cost is not None:
            total += cost
    return total


def _assistant_turn_has_tokens(msg: AiChatMessageDict) -> bool:
    prompt = int(msg.get("prompt_tokens") or 0)
    completion = int(msg.get("completion_tokens") or 0)
    reasoning = int(msg.get("reasoning_tokens") or 0)
    return prompt > 0 or completion > 0 or reasoning > 0


def _resolve_model_row_labels(
    model_id: str | None,
    entry: AiModelEntry | None,
    msg: AiChatMessageDict,
    *,
    extra_entries: Iterable[AiModelEntry] | None = None,
) -> tuple[str, str]:
    """Return ``(model_label, provider_label)`` for one spend table row."""
    stored = str(msg.get("model_label") or "").strip()
    if stored:
        model_label = stored
    else:
        model_label = resolve_model_display_name(model_id, entry, extra_entries=extra_entries)
    if entry is not None:
        provider_label = provider_group_label(entry)
    elif model_id:
        provider_label = model_id.split("/")[0] if "/" in model_id else "Unknown"
    else:
        provider_label = "Unknown"
    return model_label, provider_label


def session_spend_breakdown(
    messages: list[AiChatMessageDict],
    *,
    session_model_id: str | None = None,
    models: list[AiModelEntry] | None = None,
) -> SessionSpendBreakdown:
    """Roll up assistant-turn token usage and USD cost by configured model."""
    model_list = list(models) if models is not None else list(AiConfig.get_models())
    model_map: dict[str, ModelSpendRow] = {}
    assistant_turns = 0
    priced_turns = 0
    known_usd = 0.0
    has_unpriced = False

    for index, msg in enumerate(messages):
        if msg.get("role") != "assistant":
            continue
        if not _assistant_turn_has_tokens(msg):
            continue
        assistant_turns += 1
        prompt = int(msg.get("prompt_tokens") or 0)
        completion = int(msg.get("completion_tokens") or 0)
        reasoning = int(msg.get("reasoning_tokens") or 0)
        model_id, cost = assistant_turn_cost_for_message(
            msg,
            messages=messages,
            msg_index=index,
            session_model_id=session_model_id,
            models=model_list,
        )
        entry = entry_for_model_id(model_id, extra_entries=model_list)
        if cost is not None:
            priced_turns += 1
            known_usd += cost
        else:
            has_unpriced = True
        row_key = model_id or f"unknown:{index}"
        model_label, provider_label = _resolve_model_row_labels(
            model_id,
            entry,
            msg,
            extra_entries=model_list,
        )
        row = model_map.get(row_key)
        if row is None:
            row = ModelSpendRow(
                model_id=row_key,
                model_label=model_label,
                provider_label=provider_label,
                prompt_tokens=0,
                completion_tokens=0,
                reasoning_tokens=0,
                cost_usd=0.0 if cost is not None else None,
                turn_count=0,
            )
            model_map[row_key] = row
        row["prompt_tokens"] += prompt
        row["completion_tokens"] += completion
        row["reasoning_tokens"] += reasoning
        row["turn_count"] += 1
        if cost is not None:
            prior = row.get("cost_usd")
            row["cost_usd"] = (prior or 0.0) + cost
        elif row.get("cost_usd") is not None:
            row["cost_usd"] = None

    spend_models = sorted(
        model_map.values(),
        key=lambda row: (row["provider_label"].lower(), row["model_label"].lower()),
    )
    total_usd = None if assistant_turns == 0 or has_unpriced else known_usd
    partial = has_unpriced and known_usd > 0
    return SessionSpendBreakdown(
        total_usd=total_usd,
        known_usd=known_usd,
        assistant_turns=assistant_turns,
        priced_turns=priced_turns,
        partial=partial,
        models=spend_models,
    )


def format_spend_tab_label(summary: SessionSpendBreakdown) -> str:
    """Return the Spend flyout tab label (``Spend $0.38`` or ``Spend``)."""
    known = float(summary.get("known_usd") or 0.0)
    if summary.get("partial") and known > 0:
        return f"Spend {format_usd_amount(known)}+"
    if known > 0:
        return f"Spend {format_usd_amount(known)}"
    total = summary.get("total_usd")
    if total is not None and total > 0:
        return f"Spend {format_usd_amount(total)}"
    return "Spend"


def format_spend_pill_label(summary: SessionSpendBreakdown) -> str:
    """Return the USD portion for compact spend labels."""
    known = float(summary.get("known_usd") or 0.0)
    if summary.get("partial") and known > 0:
        return f"{format_usd_amount(known)}+"
    if known > 0:
        return format_usd_amount(known)
    total = summary.get("total_usd")
    if total is not None and total > 0:
        return format_usd_amount(total)
    return format_usd_amount(0.0)


def format_context_ring_tooltip(
    used_tokens: int,
    total_tokens: int,
    summary: SessionSpendBreakdown | None,
) -> str:
    """Build the context ring hover tooltip, optionally appending session spend."""
    if total_tokens <= 0:
        return "Context: —"
    pct = min(100, round(100 * used_tokens / total_tokens))
    used = format_run_context_tokens(used_tokens)
    total = format_run_context_tokens(total_tokens)
    base = f"Context: {pct}% ({used}/{total})"
    if summary is None:
        return base
    known = float(summary.get("known_usd") or 0.0)
    if known <= 0 and not summary.get("partial"):
        return base
    spend = format_spend_pill_label(summary)
    return f"{base} · Session ~{spend}"


def spend_pill_visible(summary: SessionSpendBreakdown) -> bool:
    """Return whether the Spend tab should show a USD amount."""
    known = float(summary.get("known_usd") or 0.0)
    return known > 0 or bool(summary.get("partial"))


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
    message: AiChatMessageDict | None = None,
    messages: list[AiChatMessageDict] | None = None,
    msg_index: int | None = None,
    session_model_id: str | None = None,
    cost_usd: float | None = None,
) -> str:
    """Build footer text: model name plus turn cost when pricing is known."""
    pricing_model_id = model_id
    if message is not None and messages is not None and msg_index is not None:
        pricing_model_id = pricing_model_id_for_assistant_message(
            message,
            messages=messages,
            msg_index=msg_index,
            session_model_id=session_model_id,
        )
    resolved_entry = entry_for_model_id(pricing_model_id, extra_entries=extra_entries) or entry
    name = resolve_assistant_footer_name(
        model_label=model_label,
        model_id=model_id,
        entry=resolved_entry,
        extra_entries=extra_entries,
    )
    prompt = int(prompt_tokens or 0)
    completion = int(completion_tokens or 0)
    reasoning = int(reasoning_tokens or 0)
    if cost_usd is None and message is not None:
        stored = message.get("cost_usd")
        if isinstance(stored, int | float):
            cost_usd = float(stored)
    if cost_usd is not None and cost_usd > 0:
        return f"{name} · {_format_usd_amount(cost_usd)}"
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
    "ModelSpendRow",
    "ProviderSpendRow",
    "SessionSpendBreakdown",
    "assistant_message_cost_usd",
    "assistant_turn_cost_for_message",
    "effective_assistant_model_id",
    "entry_for_model_id",
    "format_assistant_footer_label",
    "format_context_ring_tooltip",
    "format_spend_pill_label",
    "format_spend_tab_label",
    "format_usd_amount",
    "message_turn_cost_usd",
    "model_display_name_from_entry",
    "pricing_model_id_for_assistant_message",
    "resolve_assistant_footer_name",
    "resolve_model_display_name",
    "resolve_turn_model_id",
    "session_spend_breakdown",
    "spend_pill_visible",
    "sum_assistant_turn_costs",
    "turn_usage_delta",
]
