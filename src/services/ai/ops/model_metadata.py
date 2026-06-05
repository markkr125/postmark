"""Resolve per-model context windows and capabilities from provider APIs or LiteLLM."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urljoin

import httpx

from services.ai.ai_logging import log as ai_log
from services.ai.ops.model_filters import (
    _id_looks_non_chat,
    _litellm_agent_caps,
    _openrouter_caps,
    litellm_supports_vision,
)
from services.ai.provider_catalog import ModelSpec, litellm_context_tier_thresholds
from services.ai.reasoning_effort import (
    default_effort_for,
    normalize_efforts,
    ollama_reasoning_from_show,
    ollama_thinking_from_show,
)

logger = logging.getLogger(__name__)

_OLLAMA_ENRICH_WORKERS = 6


def _positive_float(val: object) -> float:
    if isinstance(val, int | float) and float(val) > 0:
        return float(val)
    return 0.0


def _cost_from_mapping(data: dict[str, Any]) -> tuple[float, float]:
    """Extract input/output USD-per-token from a LiteLLM cost row."""
    return (
        _positive_float(data.get("input_cost_per_token")),
        _positive_float(data.get("output_cost_per_token")),
    )


def litellm_cost_per_token(model_id: str) -> tuple[float, float]:
    """Look up USD per token via LiteLLM ``get_model_info`` / ``model_cost``."""
    try:
        from litellm import get_model_info

        info_raw: object = get_model_info(model=model_id)
        if isinstance(info_raw, dict):
            inp, out = _cost_from_mapping(info_raw)
            if inp > 0 or out > 0:
                return inp, out
    except Exception as exc:
        logger.debug("get_model_info cost(%s): %s", model_id, exc)
    try:
        import litellm

        bare = model_id.split("/", 1)[-1]
        candidates: tuple[str, ...] = (model_id, bare)
        if "/" in model_id:
            candidates = (model_id, bare, f"{model_id.split('/', 1)[0]}/{bare}")
        for key in candidates:
            row = litellm.model_cost.get(key)
            if isinstance(row, dict):
                inp, out = _cost_from_mapping(row)
                if inp > 0 or out > 0:
                    return inp, out
    except Exception as exc:
        logger.debug("model_cost pricing(%s): %s", model_id, exc)
    return 0.0, 0.0


def _openrouter_costs(row: dict[str, object]) -> tuple[float, float]:
    pricing = row.get("pricing")
    if not isinstance(pricing, dict):
        return 0.0, 0.0
    return _positive_float(pricing.get("prompt")), _positive_float(pricing.get("completion"))


def _resolve_spec_costs(spec: ModelSpec, inp: float, out: float) -> tuple[float, float]:
    """Prefer explicit *inp*/*out*, then spec fields, then LiteLLM."""
    in_t = inp if inp > 0 else spec.input_cost_per_token
    out_t = out if out > 0 else spec.output_cost_per_token
    if in_t <= 0 and out_t <= 0:
        return litellm_cost_per_token(spec.model)
    return in_t, out_t


def _pick_context_from_mapping(data: dict[str, Any]) -> int:
    """Extract the best available context size from a LiteLLM or provider dict."""
    max_input = data.get("max_input_tokens")
    if isinstance(max_input, int) and max_input > 0:
        return max_input
    for key in ("context_window", "context_length", "max_sequence_length"):
        val = data.get(key)
        if isinstance(val, int) and val > 0:
            return val
    max_tokens = data.get("max_tokens")
    if isinstance(max_tokens, int) and max_tokens > 0:
        return max_tokens
    return 0


def litellm_context_tokens(model_id: str) -> int:
    """Look up context window via LiteLLM ``get_model_info`` / ``model_cost``."""
    try:
        from litellm import get_model_info

        info_raw: object = get_model_info(model=model_id)
        if isinstance(info_raw, dict):
            ctx = _pick_context_from_mapping(info_raw)
            if ctx:
                return ctx
    except Exception as exc:
        logger.debug("get_model_info(%s): %s", model_id, exc)
    try:
        import litellm

        bare = model_id.split("/", 1)[-1]
        candidates: tuple[str, ...] = (model_id, bare)
        if "/" in model_id:
            candidates = (model_id, bare, f"{model_id.split('/', 1)[0]}/{bare}")
        for key in candidates:
            row = litellm.model_cost.get(key)
            if isinstance(row, dict):
                ctx = _pick_context_from_mapping(row)
                if ctx:
                    return ctx
    except Exception as exc:
        logger.debug("model_cost(%s): %s", model_id, exc)
    return 0


def litellm_reasoning(model_id: str) -> tuple[bool, tuple[str, ...], str]:
    """Return ``(supports, efforts, default)`` via LiteLLM metadata."""
    try:
        import litellm
    except ImportError:
        return False, (), ""
    try:
        supports = bool(litellm.supports_reasoning(model=model_id))
    except Exception as exc:
        logger.debug("supports_reasoning(%s): %s", model_id, exc)
        return False, (), ""
    if not supports:
        return False, (), ""
    efforts: list[str] = []
    try:
        from litellm import get_model_info

        info_raw: object = get_model_info(model=model_id)
        if isinstance(info_raw, dict):
            for level in ("none", "minimal", "low", "high", "xhigh", "max"):
                key = f"supports_{level}_reasoning_effort"
                if info_raw.get(key) is True:
                    efforts.append(level)
    except Exception as exc:
        logger.debug("get_model_info reasoning(%s): %s", model_id, exc)
    if supports and "medium" not in efforts:
        efforts.append("medium")
    normalized = normalize_efforts(tuple(efforts))
    default = default_effort_for(normalized) if normalized else "medium"
    return True, normalized, default


def _spec_with_reasoning(
    spec: ModelSpec,
    *,
    context: int | None = None,
    tools: bool | None = None,
    vision: bool | None = None,
    text: bool | None = None,
    insert: bool | None = None,
    reasoning: bool,
    reasoning_efforts: tuple[str, ...],
    reasoning_default: str,
    thinking: bool = False,
    thinking_default: str = "",
    context_tiers: tuple[int, ...] | None = None,
    input_cost_per_token: float | None = None,
    output_cost_per_token: float | None = None,
) -> ModelSpec:
    """Rebuild *spec* with optional field overrides and agent metadata."""
    return ModelSpec(
        spec.model,
        spec.label,
        context if context is not None else spec.context,
        tools if tools is not None else spec.tools,
        vision if vision is not None else spec.vision,
        text if text is not None else spec.text,
        insert if insert is not None else spec.insert,
        reasoning=reasoning,
        reasoning_efforts=reasoning_efforts,
        reasoning_default=reasoning_default,
        thinking=thinking,
        thinking_default=thinking_default,
        context_tiers=context_tiers if context_tiers is not None else spec.context_tiers,
        input_cost_per_token=(
            input_cost_per_token if input_cost_per_token is not None else spec.input_cost_per_token
        ),
        output_cost_per_token=(
            output_cost_per_token
            if output_cost_per_token is not None
            else spec.output_cost_per_token
        ),
    )


def _ollama_show_json(
    base_url: str, ollama_name: str, api_key: str, *, timeout: float
) -> dict[str, Any] | None:
    root = base_url.strip().rstrip("/") or "http://127.0.0.1:11434"
    url = urljoin(root + "/", "api/show")
    headers: dict[str, str] = {}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json={"name": ollama_name}, headers=headers or None)
        resp.raise_for_status()
        data = resp.json()
    return data if isinstance(data, dict) else None


_OLLAMA_VISION_NAME_HINTS = (
    "llava",
    "bakllava",
    "moondream",
    "minicpm-v",
    "qwen2-vl",
    "qwen-vl",
    "qwen3-vl",
    "llama3.2-vision",
    "gemma3-vision",
    "vision",
    "vl-",
    "-vl",
)


def _ollama_vision_from_show(data: dict[str, Any], raw_name: str) -> bool:
    """Detect multimodal models from Ollama ``/api/show`` metadata and name."""
    caps = data.get("capabilities")
    if isinstance(caps, list):
        cap_set = {str(c).lower() for c in caps}
        if "vision" in cap_set:
            return True
    model_info = data.get("model_info")
    if isinstance(model_info, dict):
        for key in model_info:
            key_l = str(key).lower()
            if "vision" in key_l and "block" in key_l:
                return True
    details = data.get("details")
    if isinstance(details, dict):
        families = details.get("families")
        if isinstance(families, list) and "clip" in {str(f).lower() for f in families}:
            return True
    low = raw_name.lower()
    return any(hint in low for hint in _OLLAMA_VISION_NAME_HINTS)


def _ollama_agent_flags_from_show(
    data: dict[str, Any], *, raw_name: str
) -> tuple[bool, bool, bool, bool]:
    """Return ``(completion, tools, vision, insert)`` from Ollama ``/api/show``."""
    caps = data.get("capabilities")
    if not isinstance(caps, list):
        return True, False, _ollama_vision_from_show(data, raw_name), False
    cap_set = {str(c).lower() for c in caps}
    text_ok = "completion" in cap_set
    tools_ok = "tools" in cap_set
    vision_ok = _ollama_vision_from_show(data, raw_name)
    insert_ok = "insert" in cap_set
    return text_ok, tools_ok, vision_ok, insert_ok


def ollama_context_from_show(data: dict[str, Any]) -> int:
    """Parse context length from an Ollama ``/api/show`` response."""
    model_info = data.get("model_info")
    if isinstance(model_info, dict):
        for key, val in model_info.items():
            if not isinstance(val, int | float):
                continue
            key_l = str(key).lower()
            if "context" in key_l and int(val) > 0:
                return int(val)
    details = data.get("details")
    if isinstance(details, dict):
        for key in ("context_length", "num_ctx"):
            val = details.get(key)
            if isinstance(val, int) and val > 0:
                return val
    return 0


def enrich_ollama_spec(
    spec: ModelSpec,
    *,
    base_url: str,
    api_key: str,
    timeout: float,
    default_context: int = 0,
) -> ModelSpec | None:
    """Fetch ``/api/show`` for context and agent capabilities."""
    raw_name = spec.model.removeprefix("ollama/")
    if _id_looks_non_chat(raw_name):
        return None
    ctx = spec.context
    text_ok = spec.text
    tools_ok = spec.tools
    vision_ok = spec.vision
    insert_ok = spec.insert
    data: dict[str, Any] | None = None
    try:
        data = _ollama_show_json(base_url, raw_name, api_key, timeout=timeout)
        if data is not None:
            show_ctx = ollama_context_from_show(data)
            if show_ctx > 0:
                ctx = show_ctx
            text_ok, tools_ok, vision_ok, insert_ok = _ollama_agent_flags_from_show(
                data, raw_name=raw_name
            )
    except Exception as exc:
        logger.debug("ollama enrich %s failed: %s", raw_name, exc)
        if ctx <= 0:
            ctx = litellm_context_tokens(spec.model)
    if ctx <= 0:
        ctx = litellm_context_tokens(spec.model)
    if ctx <= 0 and default_context > 0:
        ctx = default_context
    if not text_ok or not tools_ok:
        return None
    in_cost, out_cost = _resolve_spec_costs(spec, 0.0, 0.0)
    thinking = False
    thinking_default = ""
    reasoning = False
    efforts: tuple[str, ...] = ()
    default = ""
    if data is not None:
        thinking, thinking_default = ollama_thinking_from_show(data)
        reasoning, efforts, default = ollama_reasoning_from_show(data, raw_name)
    return _spec_with_reasoning(
        spec,
        context=ctx,
        tools=tools_ok,
        vision=vision_ok,
        text=text_ok,
        insert=insert_ok,
        reasoning=reasoning,
        reasoning_efforts=efforts,
        reasoning_default=default,
        thinking=thinking,
        thinking_default=thinking_default,
        input_cost_per_token=in_cost,
        output_cost_per_token=out_cost,
    )


def enrich_litellm_spec(spec: ModelSpec) -> ModelSpec | None:
    """Resolve context and agent flags via LiteLLM."""
    text_ok: bool
    tools_ok: bool
    caps = _litellm_agent_caps(spec.model)
    if caps is None:
        if not (spec.text and spec.tools):
            return None
        text_ok, tools_ok = bool(spec.text), bool(spec.tools)
    else:
        text_ok = bool(caps[0])
        tools_ok = bool(caps[1])
        if not text_ok or not tools_ok:
            return None
    ctx = spec.context if spec.context > 0 else litellm_context_tokens(spec.model)
    vision_ok = spec.vision or litellm_supports_vision(spec.model)
    in_cost, out_cost = _resolve_spec_costs(spec, 0.0, 0.0)
    reasoning, efforts, default = litellm_reasoning(spec.model)
    tiers = litellm_context_tier_thresholds(spec.model)
    return _spec_with_reasoning(
        spec,
        context=ctx,
        tools=tools_ok,
        vision=vision_ok,
        text=text_ok,
        reasoning=reasoning,
        reasoning_efforts=efforts,
        reasoning_default=default,
        context_tiers=tiers,
        input_cost_per_token=in_cost,
        output_cost_per_token=out_cost,
    )


def enrich_openrouter_spec(spec: ModelSpec, row: dict[str, object]) -> ModelSpec | None:
    """Apply OpenRouter list metadata (includes ``context_length``)."""
    text_ok, tools_ok, vision_ok = _openrouter_caps(row)
    if not tools_ok:
        litellm_caps = _litellm_agent_caps(spec.model)
        if litellm_caps is not None:
            text_ok, tools_ok = litellm_caps
        if not vision_ok:
            vision_ok = litellm_supports_vision(spec.model)
    if not text_ok or not tools_ok:
        return None
    ctx = spec.context if spec.context > 0 else litellm_context_tokens(spec.model)
    or_in, or_out = _openrouter_costs(row)
    in_cost, out_cost = _resolve_spec_costs(spec, or_in, or_out)
    reasoning, efforts, default = litellm_reasoning(spec.model)
    tiers = litellm_context_tier_thresholds(spec.model)
    return _spec_with_reasoning(
        spec,
        context=ctx,
        tools=tools_ok,
        vision=vision_ok,
        text=text_ok,
        reasoning=reasoning,
        reasoning_efforts=efforts,
        reasoning_default=default,
        context_tiers=tiers,
        input_cost_per_token=in_cost,
        output_cost_per_token=out_cost,
    )


def enrich_ollama_specs_parallel(
    specs: tuple[ModelSpec, ...],
    *,
    base_url: str,
    api_key: str,
    timeout: float,
    default_context: int = 0,
) -> tuple[ModelSpec, ...]:
    """Enrich many Ollama tags with ``/api/show`` (bounded parallelism)."""
    if not specs:
        return ()
    per_model_timeout = max(3.0, min(timeout / max(len(specs), 1), 15.0))
    ai_log(
        f"Fetching Ollama model metadata ({len(specs)} model(s), {per_model_timeout:.0f}s each)…"
    )

    def _one(spec: ModelSpec) -> ModelSpec | None:
        return enrich_ollama_spec(
            spec,
            base_url=base_url,
            api_key=api_key,
            timeout=per_model_timeout,
            default_context=default_context,
        )

    out: list[ModelSpec] = []
    workers = min(_OLLAMA_ENRICH_WORKERS, len(specs))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_one, s): s for s in specs}
        for fut in as_completed(futures):
            enriched = fut.result()
            if enriched is not None:
                out.append(enriched)
    return tuple(sorted(out, key=lambda m: m.label.lower()))


def enrich_openai_specs(specs: tuple[ModelSpec, ...]) -> tuple[ModelSpec, ...]:
    """Resolve OpenAI-compatible model rows via LiteLLM (list API has no context)."""
    out: list[ModelSpec] = []
    for spec in specs:
        enriched = enrich_litellm_spec(spec)
        if enriched is not None:
            out.append(enriched)
    return tuple(sorted(out, key=lambda m: m.model))


__all__ = [
    "enrich_litellm_spec",
    "enrich_ollama_spec",
    "enrich_ollama_specs_parallel",
    "enrich_openai_specs",
    "enrich_openrouter_spec",
    "litellm_context_tier_thresholds",
    "litellm_context_tokens",
    "litellm_cost_per_token",
    "litellm_reasoning",
    "ollama_context_from_show",
]
