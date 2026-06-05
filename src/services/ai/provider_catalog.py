"""Static catalog of LLM providers and their default models (display only)."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from services.ai.reasoning_effort import (
    clamp_effort,
    default_effort_for,
    format_reasoning_effort,
    normalize_efforts,
    ollama_reasoning_from_show,
)

CapabilityKind = Literal["suggest", "tools", "vision"]

OLLAMA_DEFAULT_CONTEXT_TOKENS = 32_768
MIN_RUN_CONTEXT_TOKENS = 22_000

OLLAMA_CONTEXT_OPTIONS: tuple[tuple[str, int], ...] = (
    ("4k", 4_096),
    ("8k", 8_192),
    ("16k", 16_384),
    ("32k", 32_768),
    ("64k", 65_536),
    ("128k", 131_072),
    ("256k", 262_144),
    ("512k", 524_288),
    ("1M", 1_024_000),
)

CredentialFieldId = Literal["api_key", "base_url", "api_version"]
ModelsFetchKind = Literal[
    "catalog", "litellm", "ollama", "openai", "openrouter", "azure", "openai_compatible"
]


@dataclass(frozen=True)
class CredentialField:
    """One credential input aligned with :class:`openhands.sdk.llm.llm.LLM` fields."""

    field_id: CredentialFieldId
    label: str
    placeholder: str
    required: bool
    default: str = ""


@dataclass(frozen=True)
class ModelSpec:
    """One selectable model. ``model`` is the litellm string."""

    model: str
    label: str
    context: int
    tools: bool
    vision: bool
    text: bool = True
    insert: bool = False
    reasoning: bool = False
    reasoning_efforts: tuple[str, ...] = ()
    reasoning_default: str = ""
    thinking: bool = False
    thinking_default: str = ""
    context_tiers: tuple[int, ...] = ()
    input_cost_per_token: float = 0.0
    output_cost_per_token: float = 0.0


@dataclass(frozen=True)
class ProviderSpec:
    """One provider. ``key`` is our stable id; ``prefix`` is the litellm prefix."""

    key: str
    label: str
    prefix: str
    credential_fields: tuple[CredentialField, ...]
    models_fetch: ModelsFetchKind = "catalog"
    default_base_url: str = ""
    default_models: tuple[ModelSpec, ...] = field(default_factory=tuple)
    probe_model: str = ""


def _fields(*specs: CredentialField) -> tuple[CredentialField, ...]:
    return specs


_API_KEY = CredentialField("api_key", "API key", "", required=True)
_API_KEY_OPT = CredentialField("api_key", "API key", "Optional for local endpoints", required=False)
_BASE = CredentialField("base_url", "Base URL", "https://…", required=True)
_BASE_OPT = CredentialField(
    "base_url",
    "Base URL",
    "https://… (optional override)",
    required=False,
)
_BASE_OLLAMA = CredentialField(
    "base_url",
    "Ollama URL",
    "http://127.0.0.1:11434",
    required=True,
    default="http://127.0.0.1:11434",
)
_API_VER = CredentialField("api_version", "API version", "e.g. 2024-02-15-preview", required=True)


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        key="anthropic",
        label="Anthropic",
        prefix="anthropic",
        credential_fields=_fields(_API_KEY),
        models_fetch="litellm",
        default_models=(
            ModelSpec(
                "anthropic/claude-sonnet-4-5-20250929", "Claude Sonnet 4.5", 200000, True, True
            ),
            ModelSpec("anthropic/claude-opus-4-1-20250805", "Claude Opus 4.1", 200000, True, True),
            ModelSpec(
                "anthropic/claude-3-5-haiku-20241022", "Claude 3.5 Haiku", 200000, True, True
            ),
        ),
        probe_model="anthropic/claude-3-5-haiku-20241022",
    ),
    ProviderSpec(
        key="openai",
        label="OpenAI",
        prefix="openai",
        credential_fields=_fields(_API_KEY, _BASE_OPT),
        models_fetch="openai",
        default_models=(
            ModelSpec("openai/gpt-4o", "GPT-4o", 128000, True, True),
            ModelSpec("openai/gpt-4o-mini", "GPT-4o mini", 128000, True, True),
            ModelSpec("openai/o3-mini", "o3-mini", 200000, True, False),
        ),
        probe_model="openai/gpt-4o-mini",
    ),
    ProviderSpec(
        key="google",
        label="Google Gemini",
        prefix="gemini",
        credential_fields=_fields(_API_KEY),
        models_fetch="litellm",
        default_models=(
            ModelSpec("gemini/gemini-1.5-pro", "Gemini 1.5 Pro", 2000000, True, True),
            ModelSpec("gemini/gemini-1.5-flash", "Gemini 1.5 Flash", 1000000, True, True),
        ),
        probe_model="gemini/gemini-1.5-flash",
    ),
    ProviderSpec(
        key="azure",
        label="Azure OpenAI",
        prefix="azure",
        credential_fields=_fields(_API_KEY, _BASE, _API_VER),
        models_fetch="azure",
        default_models=(
            ModelSpec("azure/gpt-4o", "Azure GPT-4o (deployment)", 128000, True, True),
        ),
        probe_model="azure/gpt-4o",
    ),
    ProviderSpec(
        key="openrouter",
        label="OpenRouter",
        prefix="openrouter",
        credential_fields=_fields(_API_KEY),
        models_fetch="openrouter",
        default_models=(
            ModelSpec(
                "openrouter/anthropic/claude-sonnet-4-5",
                "OpenRouter: Claude Sonnet 4.5",
                200000,
                True,
                True,
            ),
            ModelSpec("openrouter/openai/gpt-4o", "OpenRouter: GPT-4o", 128000, True, True),
        ),
        probe_model="openrouter/openai/gpt-4o-mini",
    ),
    ProviderSpec(
        key="ollama",
        label="Ollama (local)",
        prefix="ollama",
        credential_fields=_fields(
            _BASE_OLLAMA,
            CredentialField(
                "api_key",
                "API key",
                "Optional — reverse proxies or authenticated endpoints",
                required=False,
            ),
        ),
        models_fetch="ollama",
        default_base_url="http://127.0.0.1:11434",
        default_models=(
            ModelSpec("ollama/llama3", "Llama 3", 8192, False, False),
            ModelSpec("ollama/qwen2.5", "Qwen 2.5", 32768, True, False),
        ),
        probe_model="ollama/llama3",
    ),
    ProviderSpec(
        key="xai",
        label="xAI Grok",
        prefix="xai",
        credential_fields=_fields(_API_KEY),
        models_fetch="litellm",
        default_models=(ModelSpec("xai/grok-2", "Grok 2", 131072, True, False),),
        probe_model="xai/grok-2",
    ),
    ProviderSpec(
        key="custom",
        label="Custom (OpenAI-compatible)",
        prefix="openai",
        credential_fields=_fields(_API_KEY_OPT, _BASE),
        models_fetch="openai_compatible",
        default_models=(),
        probe_model="openai/gpt-4o-mini",
    ),
)

_BY_KEY: dict[str, ProviderSpec] = {p.key: p for p in PROVIDERS}

# Providers whose credentials are verified by HTTP model listing (not an LLM ping).
LIVE_MODEL_LIST_KINDS: frozenset[ModelsFetchKind] = frozenset(
    {"ollama", "openai", "openrouter", "azure", "openai_compatible"}
)


def provider_lists_models_live(key: str) -> bool:
    """True when setup should call the provider's model-list API instead of a chat ping."""
    spec = provider_by_key(key)
    return spec is not None and spec.models_fetch in LIVE_MODEL_LIST_KINDS


def provider_by_key(key: str) -> ProviderSpec | None:
    """Return the :class:`ProviderSpec` for *key*, or ``None``."""
    return _BY_KEY.get(key)


def catalog_provider_label(provider_key: str) -> str:
    """Default human-readable name from the static provider catalog."""
    spec = provider_by_key(provider_key)
    if spec is not None:
        return spec.label
    return provider_key or "Other"


def provider_connection_key(entry: Mapping[str, Any]) -> str:
    """Stable id grouping rows that share one provider connection."""
    auth_ref = str(entry.get("auth_ref") or "").strip()
    if auth_ref:
        return auth_ref
    provider = str(entry.get("provider") or "").strip()
    base_url = str(entry.get("base_url") or "").strip()
    return f"{provider}:{base_url}"


def allocate_provider_display_name(provider_key: str, existing_names: set[str]) -> str:
    """Pick a unique provider display name (``Ollama (local)``, ``Ollama (local) 2``, …)."""
    base = catalog_provider_label(provider_key)
    if base not in existing_names:
        return base
    n = 2
    while True:
        candidate = f"{base} {n}"
        if candidate not in existing_names:
            return candidate
        n += 1


def provider_group_label(entry: Mapping[str, Any]) -> str:
    """Display label for a provider group header row in the settings tree."""
    stored = str(entry.get("provider_display_name") or "").strip()
    if stored:
        return stored
    return catalog_provider_label(str(entry.get("provider") or ""))


def model_row_label(spec: ModelSpec) -> str:
    """Per-model name for the tree (never the provider display name)."""
    if spec.label:
        return spec.label
    mid = spec.model
    if "/" in mid:
        mid = mid.rsplit("/", 1)[-1]
    if ":" in mid:
        mid = mid.split(":", 1)[0]
    return mid or spec.model


def migrate_provider_display_names(entries: list[Any]) -> bool:
    """Assign ``provider_display_name`` on each connection group when missing."""
    groups: dict[str, list[int]] = {}
    for index, row in enumerate(entries):
        groups.setdefault(provider_connection_key(row), []).append(index)

    used: set[str] = set()
    migrated = False
    for indices in groups.values():
        stored = ""
        for index in indices:
            name = str(entries[index].get("provider_display_name") or "").strip()
            if name:
                stored = name
                break
        if stored:
            used.add(stored)
            for index in indices:
                if not str(entries[index].get("provider_display_name") or "").strip():
                    entries[index]["provider_display_name"] = stored
                    migrated = True
            continue
        provider_key = str(entries[indices[0]].get("provider") or "")
        name = allocate_provider_display_name(provider_key, used)
        used.add(name)
        for index in indices:
            entries[index]["provider_display_name"] = name
            migrated = True
    return migrated


def probe_model_for_provider(key: str) -> str:
    """Return the litellm model id used for a provider connectivity ping."""
    spec = provider_by_key(key)
    if spec is None:
        return ""
    if spec.probe_model:
        return spec.probe_model
    if spec.default_models:
        return spec.default_models[0].model
    return f"{spec.prefix}/gpt-4o-mini"


def _catalog_model_spec(model: str) -> ModelSpec | None:
    for prov in PROVIDERS:
        for m in prov.default_models:
            if m.model == model:
                return m
    return None


def context_tokens_for_model(model: str) -> int:
    """Return context window from the static catalog, else ``0``."""
    spec = _catalog_model_spec(model)
    return spec.context if spec is not None else 0


def ollama_default_context_tokens(entry: Mapping[str, Any] | None) -> int:
    """Saved Ollama provider default context, else :data:`OLLAMA_DEFAULT_CONTEXT_TOKENS`."""
    if entry is None:
        return OLLAMA_DEFAULT_CONTEXT_TOKENS
    raw = entry.get("default_context")
    if isinstance(raw, int) and raw > 0:
        return raw
    return OLLAMA_DEFAULT_CONTEXT_TOKENS


def model_max_context_tokens(entry: Mapping[str, Any] | None) -> int:
    """Maximum context window for a saved model row (from fetch metadata)."""
    if entry is None:
        return 0
    ctx = entry.get("context")
    return ctx if isinstance(ctx, int) and ctx > 0 else 0


_logger = logging.getLogger(__name__)
_INPUT_TIER_ABOVE_RE = re.compile(r"^input_cost_per_token_above_(?P<num>\d+)(?P<unit>k)?_tokens$")


def _tier_tokens_from_cost_key(key: str) -> int | None:
    """Parse ``input_cost_per_token_above_{N}k_tokens`` into a token count."""
    match = _INPUT_TIER_ABOVE_RE.match(key)
    if match is None:
        return None
    num = int(match.group("num"))
    return num * 1000 if match.group("unit") == "k" else num


def litellm_context_tier_thresholds(model_id: str) -> tuple[int, ...]:
    """Return pricing-tier breakpoints from LiteLLM ``model_cost`` (zero network calls)."""
    thresholds: set[int] = set()
    try:
        import litellm

        bare = model_id.split("/", 1)[-1]
        candidates: tuple[str, ...] = (model_id, bare)
        if "/" in model_id:
            candidates = (model_id, bare, f"{model_id.split('/', 1)[0]}/{bare}")
        for key in candidates:
            row = litellm.model_cost.get(key)
            if not isinstance(row, dict):
                continue
            for field_name in row:
                tokens = _tier_tokens_from_cost_key(str(field_name))
                if tokens is not None and tokens > 0:
                    thresholds.add(tokens)
            if thresholds:
                break
    except Exception as exc:
        _logger.debug("context tiers(%s): %s", model_id, exc)
    return tuple(sorted(thresholds))


def context_tiers_for_entry(entry: Mapping[str, Any] | None) -> tuple[int, ...]:
    """LiteLLM pricing tier breakpoints (e.g. 272k before higher input cost)."""
    if entry is None:
        return ()
    raw = entry.get("context_tiers")
    if not isinstance(raw, list):
        return ()
    values = sorted({int(v) for v in raw if isinstance(v, int) and v > 0})
    return tuple(values)


def default_run_context_tokens(entry: Mapping[str, Any] | None) -> int:
    """Provider/model default run context before a per-model override."""
    if entry is None:
        return 0
    max_ctx = model_max_context_tokens(entry)
    if max_ctx <= 0:
        return 0
    if str(entry.get("provider") or "") == "ollama":
        return min(ollama_default_context_tokens(entry), max_ctx)
    tiers = context_tiers_for_entry(entry)
    if tiers:
        return min(tiers[0], max_ctx)
    return max_ctx


def effective_run_context_tokens(entry: Mapping[str, Any] | None) -> int:
    """Context size used for runs and picker display (override or default)."""
    if entry is None:
        return 0
    override = entry.get("context_limit")
    if isinstance(override, int) and override > 0:
        return clamp_run_context_tokens(override, entry)
    return default_run_context_tokens(entry)


def clamp_run_context_tokens(tokens: int, entry: Mapping[str, Any] | None) -> int:
    """Clamp *tokens* to ``MIN_RUN_CONTEXT_TOKENS`` .. model max."""
    max_ctx = model_max_context_tokens(entry)
    if max_ctx <= 0:
        return 0
    low = min(MIN_RUN_CONTEXT_TOKENS, max_ctx)
    return max(low, min(tokens, max_ctx))


def run_context_choices(entry: Mapping[str, Any] | None) -> tuple[tuple[str, int], ...]:
    """Preset context sizes for the picker edit flyout."""
    max_ctx = model_max_context_tokens(entry)
    if max_ctx < MIN_RUN_CONTEXT_TOKENS:
        return ()
    if entry is not None and str(entry.get("provider") or "") == "ollama":
        return _ollama_run_context_choices(max_ctx, entry)
    return _tiered_run_context_choices(max_ctx, entry)


def _ollama_run_context_choices(
    max_ctx: int, entry: Mapping[str, Any] | None
) -> tuple[tuple[str, int], ...]:
    """Ollama: stepped presets from 22k up to the model max."""
    out: list[tuple[str, int]] = []
    for label, value in OLLAMA_CONTEXT_OPTIONS:
        if MIN_RUN_CONTEXT_TOKENS <= value <= max_ctx:
            out.append((label, value))
    if max_ctx not in {v for _, v in out}:
        out.append((format_context_tokens(max_ctx), max_ctx))
    default = default_run_context_tokens(entry)
    if default >= MIN_RUN_CONTEXT_TOKENS and default not in {v for _, v in out}:
        out.append((format_context_tokens(default), default))
    out.sort(key=lambda pair: pair[1])
    return tuple(out)


def _tiered_run_context_choices(
    max_ctx: int, entry: Mapping[str, Any] | None
) -> tuple[tuple[str, int], ...]:
    """Cloud models: only tier breakpoints where pricing changes (not every step)."""
    tiers = context_tiers_for_entry(entry)
    if not tiers:
        return ()
    candidates: set[int] = set()
    for threshold in tiers:
        if MIN_RUN_CONTEXT_TOKENS <= threshold <= max_ctx:
            candidates.add(threshold)
    largest_tier = max(tiers)
    if max_ctx > largest_tier:
        candidates.add(max_ctx)
    if len(candidates) < 2:
        return ()
    return tuple((format_context_tokens(value), value) for value in sorted(candidates))


def context_tokens_for_entry(entry: object) -> int:
    """Context window for settings tree (model max, else catalog default)."""
    if not isinstance(entry, dict):
        return 0
    ctx = model_max_context_tokens(entry)
    if ctx > 0:
        return ctx
    if str(entry.get("provider") or "") == "ollama":
        return ollama_default_context_tokens(entry)
    return context_tokens_for_model(str(entry.get("model") or ""))


def format_context_tokens(context: int) -> str:
    """Human-readable context size for the settings tree."""
    if context <= 0:
        return "—"
    if context >= 1_000_000:
        whole = context // 1_000_000
        return f"{whole}M" if context % 1_000_000 == 0 else f"{context / 1_000_000:.1f}M"
    if context >= 1000:
        whole = context // 1000
        return f"{whole}k" if context % 1000 == 0 else f"{context / 1000:.1f}k"
    return str(context)


def context_display_for_entry(entry: object) -> str:
    """Context column text for the settings models tree."""
    return format_context_tokens(context_tokens_for_entry(entry))


class CapabilityTag(TypedDict):
    """One capability pill in the settings models tree."""

    label: str
    tooltip: str
    kind: CapabilityKind


_CAPABILITY_SUGGEST_TOOLTIP = (
    "Fill-in-the-middle: completes text between a prefix and suffix (suffix completion)."
)
_CAPABILITY_TOOLS_TOOLTIP = (
    "Supports tool / function calling so agents can invoke APIs and other tools."
)
_CAPABILITY_VISION_TOOLTIP = "Accepts images or other vision inputs alongside text prompts."


def capability_tags_from_flags(
    *, tools: bool, vision: bool, insert: bool = False
) -> list[CapabilityTag]:
    """Ordered capability pills for the settings tree (UI labels + hover text)."""
    tags: list[CapabilityTag] = []
    if insert:
        tags.append({"label": "suggest", "tooltip": _CAPABILITY_SUGGEST_TOOLTIP, "kind": "suggest"})
    if tools:
        tags.append({"label": "tools", "tooltip": _CAPABILITY_TOOLS_TOOLTIP, "kind": "tools"})
    if vision:
        tags.append({"label": "vision", "tooltip": _CAPABILITY_VISION_TOOLTIP, "kind": "vision"})
    return tags


def _format_capability_flags(*, tools: bool, vision: bool, insert: bool = False) -> str:
    """Joined capability labels (for tests and legacy combined strings)."""
    tags = capability_tags_from_flags(tools=tools, vision=vision, insert=insert)
    return " · ".join(t["label"] for t in tags)


def capability_tags_for_entry(entry: object) -> list[CapabilityTag]:
    """Capability pills for a saved model row."""
    if not isinstance(entry, dict):
        return []
    model = str(entry.get("model") or "")
    if "tools" in entry or "vision" in entry or "insert" in entry:
        return capability_tags_from_flags(
            tools=bool(entry.get("tools")),
            vision=bool(entry.get("vision")),
            insert=bool(entry.get("insert")),
        )
    spec = _catalog_model_spec(model)
    if spec is None:
        return []
    return capability_tags_from_flags(
        tools=spec.tools,
        vision=spec.vision,
        insert=spec.insert,
    )


def capability_flags_for_model(model: str) -> str:
    """Tools/vision/text flags from the static catalog only (no LiteLLM probes)."""
    spec = _catalog_model_spec(model)
    if spec is None:
        return ""
    return _format_capability_flags(tools=spec.tools, vision=spec.vision, insert=spec.insert)


def capability_flags_for_entry(entry: object) -> str:
    """Capabilities column (no context) for a saved model row."""
    if not isinstance(entry, dict):
        return ""
    model = str(entry.get("model") or "")
    if "tools" in entry or "vision" in entry or "insert" in entry:
        return _format_capability_flags(
            tools=bool(entry.get("tools")),
            vision=bool(entry.get("vision")),
            insert=bool(entry.get("insert")),
        )
    return capability_flags_for_model(model)


def capability_text(model: str) -> str:
    """Legacy combined string (context + flags); prefer separate columns in UI."""
    spec = _catalog_model_spec(model)
    if spec is None:
        return ""
    ctx = format_context_tokens(spec.context)
    flags = _format_capability_flags(tools=spec.tools, vision=spec.vision, insert=spec.insert)
    return f"{ctx} · {flags}" if flags else ctx


def capability_text_for_entry(entry: object) -> str:
    """Legacy combined capabilities string."""
    ctx = context_display_for_entry(entry)
    flags = capability_flags_for_entry(entry)
    if ctx == "—":
        return flags
    return f"{ctx} · {flags}" if flags else ctx


def _format_usd_per_million(usd: float) -> str:
    """Compact USD label for *usd* dollars per 1M tokens."""
    if usd >= 100:
        return f"{usd:.0f}"
    if usd >= 1:
        text = f"{usd:.2f}"
    elif usd >= 0.01:
        text = f"{usd:.3f}"
    else:
        text = f"{usd:.4f}"
    return text.rstrip("0").rstrip(".")


def format_model_cost_display(
    input_per_token: float,
    output_per_token: float,
    *,
    model: str = "",
) -> str:
    """Human-readable input/output cost (USD per 1M tokens); empty when unknown."""
    del model  # reserved for provider-specific rules; no special-case labels
    if input_per_token <= 0 and output_per_token <= 0:
        return ""
    parts: list[str] = []
    if input_per_token > 0:
        parts.append(f"${_format_usd_per_million(input_per_token * 1_000_000)} in")
    if output_per_token > 0:
        parts.append(f"${_format_usd_per_million(output_per_token * 1_000_000)} out")
    return " / ".join(parts)


def cost_per_token_for_entry(entry: object) -> tuple[float, float]:
    """Input/output USD per token from persisted values only.

    Settings page rows are loaded on the GUI thread, so this helper must never
    call LiteLLM metadata lookup. Live model refresh/enrichment is responsible
    for persisting known costs ahead of time.
    """
    if not isinstance(entry, dict):
        return 0.0, 0.0
    inp_raw = entry.get("input_cost_per_token")
    out_raw = entry.get("output_cost_per_token")
    inp = float(inp_raw) if isinstance(inp_raw, int | float) and float(inp_raw) > 0 else 0.0
    out = float(out_raw) if isinstance(out_raw, int | float) and float(out_raw) > 0 else 0.0
    return inp, out


def cost_display_for_spec(spec: ModelSpec) -> str:
    """Cost column text for a :class:`ModelSpec` (import preview, etc.)."""
    inp = spec.input_cost_per_token
    out = spec.output_cost_per_token
    if inp <= 0 and out <= 0:
        from services.ai.ops.model_metadata import litellm_cost_per_token

        inp, out = litellm_cost_per_token(spec.model)
    return format_model_cost_display(inp, out, model=spec.model)


def cost_display_for_entry(entry: object) -> str:
    """Cost column text for a saved model row."""
    if not isinstance(entry, dict):
        return "—"
    model = str(entry.get("model") or "")
    inp, out = cost_per_token_for_entry(entry)
    return format_model_cost_display(inp, out, model=model)


def persisted_cost_fields(spec: ModelSpec) -> dict[str, float]:
    """Optional cost keys to store on :class:`AiModelEntry`."""
    out: dict[str, float] = {}
    if spec.input_cost_per_token > 0:
        out["input_cost_per_token"] = spec.input_cost_per_token
    if spec.output_cost_per_token > 0:
        out["output_cost_per_token"] = spec.output_cost_per_token
    return out


__all__ = [
    "LIVE_MODEL_LIST_KINDS",
    "MIN_RUN_CONTEXT_TOKENS",
    "OLLAMA_CONTEXT_OPTIONS",
    "OLLAMA_DEFAULT_CONTEXT_TOKENS",
    "PROVIDERS",
    "CapabilityKind",
    "CapabilityTag",
    "CredentialField",
    "CredentialFieldId",
    "ModelSpec",
    "ModelsFetchKind",
    "ProviderSpec",
    "allocate_provider_display_name",
    "capability_flags_for_entry",
    "capability_flags_for_model",
    "capability_tags_for_entry",
    "capability_tags_from_flags",
    "capability_text",
    "capability_text_for_entry",
    "catalog_provider_label",
    "clamp_effort",
    "clamp_run_context_tokens",
    "context_display_for_entry",
    "context_tiers_for_entry",
    "context_tokens_for_entry",
    "context_tokens_for_model",
    "cost_display_for_entry",
    "cost_display_for_spec",
    "cost_per_token_for_entry",
    "default_effort_for",
    "default_run_context_tokens",
    "effective_run_context_tokens",
    "format_context_tokens",
    "format_model_cost_display",
    "format_reasoning_effort",
    "litellm_context_tier_thresholds",
    "migrate_provider_display_names",
    "model_max_context_tokens",
    "model_row_label",
    "normalize_efforts",
    "ollama_default_context_tokens",
    "ollama_reasoning_from_show",
    "persisted_cost_fields",
    "probe_model_for_provider",
    "provider_by_key",
    "provider_connection_key",
    "provider_group_label",
    "provider_lists_models_live",
    "run_context_choices",
]
