"""Persistence for configured AI model entries (QSettings-backed)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from typing import Literal, NotRequired, TypedDict, cast

from PySide6.QtCore import QSettings

from services.ai.provider_catalog import (
    clamp_run_context_tokens,
    context_tokens_for_model,
    litellm_context_tier_thresholds,
    migrate_provider_display_names,
)
from services.ai.reasoning_effort import (
    OLLAMA_BOOLEAN_LEVELS,
    clamp_effort,
    default_effort_for,
    fill_gpt5_reasoning_gaps,
    is_boolean_thinking_efforts,
    normalize_efforts,
)

logger = logging.getLogger(__name__)

_ORG = "Postmark"
_APP = "Postmark"
_KEY_MODELS = "ai/models"
_KEY_DEFAULT = "ai/default_model"
_KEY_CHAT_MODEL = "ai/chat_model_id"
_KEY_CHAT_SESSION = "ai/chat_session_id"
_KEY_CHAT_SESSION_CLEARED = "ai/chat_session_cleared"
_AUTH_KINDS = ("token", "none")


class AiModelEntry(TypedDict):
    """One configured model. ``model`` is the litellm provider/model string."""

    id: str
    provider: str
    label: str
    provider_display_name: NotRequired[str]
    model: str
    base_url: str
    api_version: str
    auth_kind: Literal["token", "none"]
    auth_ref: str
    context: NotRequired[int]
    tools: NotRequired[bool]
    vision: NotRequired[bool]
    text: NotRequired[bool]
    insert: NotRequired[bool]
    reasoning: NotRequired[bool]
    reasoning_efforts: NotRequired[list[str]]
    reasoning_default: NotRequired[str]
    reasoning_effort: NotRequired[str]
    thinking: NotRequired[bool]
    thinking_default: NotRequired[str]
    thinking_enabled: NotRequired[str]
    context_limit: NotRequired[int]
    context_tiers: NotRequired[list[int]]
    tiers_checked: NotRequired[bool]
    enabled: NotRequired[bool]
    default_context: NotRequired[int]
    input_cost_per_token: NotRequired[float]
    output_cost_per_token: NotRequired[float]


def model_entry_enabled(entry: AiModelEntry) -> bool:
    """Whether the model is enabled for use (defaults to disabled)."""
    return bool(entry.get("enabled"))


def merge_tier_backfill_results(
    current: list[AiModelEntry],
    backfilled: list[AiModelEntry],
) -> list[AiModelEntry]:
    """Merge worker tier backfill into *current* by model ``id``.

    Copies ``context_tiers`` only when missing on *current*, and sets
    ``tiers_checked`` when the backfill row has it. Other fields on *current*
    are left unchanged so in-flight user edits are preserved.
    """
    by_id = {entry["id"]: entry for entry in backfilled if entry.get("id")}
    for row in current:
        src = by_id.get(row["id"])
        if src is None:
            continue
        if src.get("context_tiers") and not row.get("context_tiers"):
            row["context_tiers"] = list(src["context_tiers"])
        if src.get("tiers_checked"):
            row["tiers_checked"] = True
    return current


def _get_settings() -> QSettings:
    return QSettings(_ORG, _APP)


class AiConfig:
    """Static accessors for AI model configuration in QSettings."""

    @staticmethod
    def get_models(*, backfill_tiers: bool = False, persist: bool = True) -> list[AiModelEntry]:
        """Return configured models; drop malformed rows; migrate missing ids.

        When ``backfill_tiers`` is ``True``, look up missing LiteLLM pricing
        tiers (imports ``litellm``; slow on first call). When ``False`` (the
        default, used on the startup path), this is a pure QSettings read and
        never imports ``litellm``.

        When ``persist`` is ``False``, migrations are NOT written back to
        QSettings. The background backfill worker uses ``persist=False`` so
        QSettings is only ever written from the GUI thread.
        """
        s = _get_settings()
        raw = s.value(_KEY_MODELS, "")
        if not isinstance(raw, str) or not raw.strip():
            return []
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Malformed %s: %s — dropping", _KEY_MODELS, exc)
            return []
        if not isinstance(parsed, list):
            return []
        out: list[AiModelEntry] = []
        migrated = False
        for raw_entry in parsed:
            if not isinstance(raw_entry, dict):
                continue
            model = str(raw_entry.get("model") or "").strip()
            if not model:
                continue
            provider = str(raw_entry.get("provider") or "").strip()
            label = str(raw_entry.get("label") or "").strip() or model
            base_url = str(raw_entry.get("base_url") or "").strip()
            api_version = str(raw_entry.get("api_version") or "").strip()
            auth_kind = raw_entry.get("auth_kind", "none")
            if auth_kind not in _AUTH_KINDS:
                auth_kind = "none"
            auth_ref = str(raw_entry.get("auth_ref") or "").strip()
            stored_id = str(raw_entry.get("id") or "").strip()
            if stored_id:
                row_id = stored_id
            else:
                row_id = uuid.uuid4().hex
                migrated = True
            row: AiModelEntry = {
                "id": row_id,
                "provider": provider,
                "label": label,
                "model": model,
                "base_url": base_url,
                "api_version": api_version,
                "auth_kind": cast("Literal['token', 'none']", auth_kind),
                "auth_ref": auth_ref,
            }
            ctx = raw_entry.get("context")
            if isinstance(ctx, int) and ctx > 0:
                row["context"] = ctx
            else:
                catalog_ctx = context_tokens_for_model(model)
                if catalog_ctx > 0:
                    row["context"] = catalog_ctx
                    migrated = True
            if isinstance(raw_entry.get("tools"), bool):
                row["tools"] = raw_entry["tools"]
            if isinstance(raw_entry.get("vision"), bool):
                row["vision"] = raw_entry["vision"]
            if isinstance(raw_entry.get("text"), bool):
                row["text"] = raw_entry["text"]
            if isinstance(raw_entry.get("insert"), bool):
                row["insert"] = raw_entry["insert"]
            if isinstance(raw_entry.get("thinking"), bool):
                row["thinking"] = raw_entry["thinking"]
            think_default = raw_entry.get("thinking_default")
            if isinstance(think_default, str) and think_default.strip():
                row["thinking_default"] = think_default.strip().lower()
            think_on = raw_entry.get("thinking_enabled")
            if isinstance(think_on, str) and think_on.strip():
                row["thinking_enabled"] = think_on.strip().lower()
            if isinstance(raw_entry.get("reasoning"), bool):
                row["reasoning"] = raw_entry["reasoning"]
            efforts_raw = raw_entry.get("reasoning_efforts")
            if isinstance(efforts_raw, list):
                row["reasoning_efforts"] = [
                    str(e).strip().lower()
                    for e in efforts_raw
                    if isinstance(e, str) and str(e).strip()
                ]
            efforts_tuple = tuple(row.get("reasoning_efforts", []))
            if is_boolean_thinking_efforts(efforts_tuple):
                row["thinking"] = True
                if not row.get("thinking_enabled"):
                    legacy = raw_entry.get("reasoning_effort")
                    row["thinking_enabled"] = (
                        str(legacy).strip().lower()
                        if isinstance(legacy, str) and str(legacy).strip()
                        else "on"
                    )
                row["reasoning"] = False
                row["reasoning_efforts"] = []
                migrated = True
            elif efforts_tuple:
                filled = fill_gpt5_reasoning_gaps(normalize_efforts(efforts_tuple), model)
                if filled != efforts_tuple:
                    row["reasoning_efforts"] = list(filled)
                    efforts_tuple = filled
                    migrated = True
            default_eff = raw_entry.get("reasoning_default")
            if isinstance(default_eff, str) and default_eff.strip():
                row["reasoning_default"] = default_eff.strip().lower()
            stored_eff = raw_entry.get("reasoning_effort")
            if isinstance(stored_eff, str) and stored_eff.strip() and efforts_tuple:
                row["reasoning_effort"] = clamp_effort(
                    stored_eff.strip().lower(),
                    efforts_tuple,
                    str(row.get("reasoning_default", "")),
                )
            elif row.get("reasoning") and efforts_tuple:
                row["reasoning_effort"] = default_effort_for(efforts_tuple)
            ctx_limit = raw_entry.get("context_limit")
            if isinstance(ctx_limit, int) and ctx_limit > 0:
                row["context_limit"] = clamp_run_context_tokens(ctx_limit, row)
            ctx_tiers = raw_entry.get("context_tiers")
            if isinstance(ctx_tiers, list):
                tiers = sorted({int(v) for v in ctx_tiers if isinstance(v, int) and v > 0})
                if tiers:
                    row["context_tiers"] = tiers
            if raw_entry.get("tiers_checked") is True:
                row["tiers_checked"] = True
            if (
                backfill_tiers
                and not row.get("tiers_checked")
                and not row.get("context_tiers")
                and str(row.get("provider") or "") != "ollama"
            ):
                # Backfill tiers for pre-existing entries from LiteLLM's local
                # dict. Runs at most once per model; mark checked either way so
                # this never re-imports litellm on later launches.
                inferred = litellm_context_tier_thresholds(str(row.get("model") or ""))
                if inferred:
                    row["context_tiers"] = list(inferred)
                row["tiers_checked"] = True
                migrated = True
            if row.get("thinking") and row.get("thinking_enabled") not in OLLAMA_BOOLEAN_LEVELS:
                row["thinking_enabled"] = str(row.get("thinking_default", "on") or "on")
                migrated = True
            provider_display = str(raw_entry.get("provider_display_name") or "").strip()
            if provider_display:
                row["provider_display_name"] = provider_display
            if isinstance(raw_entry.get("enabled"), bool):
                row["enabled"] = raw_entry["enabled"]
            else:
                row["enabled"] = False
                migrated = True
            default_ctx = raw_entry.get("default_context")
            if isinstance(default_ctx, int) and default_ctx > 0:
                row["default_context"] = default_ctx
            inp_cost = raw_entry.get("input_cost_per_token")
            if isinstance(inp_cost, int | float) and float(inp_cost) > 0:
                row["input_cost_per_token"] = float(inp_cost)
            out_cost = raw_entry.get("output_cost_per_token")
            if isinstance(out_cost, int | float) and float(out_cost) > 0:
                row["output_cost_per_token"] = float(out_cost)
            out.append(row)
        if migrate_provider_display_names(out):
            migrated = True
        if migrated and persist:
            s.setValue(_KEY_MODELS, json.dumps(list(out)))
        return out

    @staticmethod
    def set_models(entries: list[AiModelEntry]) -> None:
        """Persist *entries* as a JSON blob. Pass ``[]`` to clear."""
        s = _get_settings()
        s.setValue(_KEY_MODELS, json.dumps(list(entries)))
        s.sync()

    @staticmethod
    def get_default_model_id() -> str:
        """Return the default model id, or ``""`` when unset."""
        s = _get_settings()
        return str(s.value(_KEY_DEFAULT, "") or "").strip()

    @staticmethod
    def _update_model_row(model_id: str, mutator: Callable[[AiModelEntry], None]) -> bool:
        """Load models, mutate the row with *model_id*, and persist if found."""
        entries = AiConfig.get_models()
        for row in entries:
            if row["id"] == model_id:
                mutator(row)
                AiConfig.set_models(entries)
                return True
        return False

    @staticmethod
    def set_model_context_limit(model_id: str, tokens: int) -> None:
        """Persist per-model run context (clamped to 22k .. model max)."""

        def _apply(row: AiModelEntry) -> None:
            row["context_limit"] = clamp_run_context_tokens(tokens, row)

        AiConfig._update_model_row(model_id, _apply)

    @staticmethod
    def set_model_thinking_enabled(model_id: str, enabled: str) -> None:
        """Persist thinking on/off for models that support it."""

        def _apply(row: AiModelEntry) -> None:
            key = enabled.strip().lower()
            row["thinking_enabled"] = key if key in OLLAMA_BOOLEAN_LEVELS else "on"

        AiConfig._update_model_row(model_id, _apply)

    @staticmethod
    def set_model_reasoning_effort(model_id: str, effort: str) -> None:
        """Persist *effort* for the model with *model_id* (clamped to its efforts)."""

        def _apply(row: AiModelEntry) -> None:
            efforts = normalize_efforts(tuple(row.get("reasoning_efforts", [])))
            row["reasoning_effort"] = clamp_effort(
                effort,
                efforts,
                str(row.get("reasoning_default", "")),
            )

        AiConfig._update_model_row(model_id, _apply)

    @staticmethod
    def set_default_model_id(model_id: str) -> None:
        """Persist the default model id (``""`` to clear)."""
        s = _get_settings()
        s.setValue(_KEY_DEFAULT, model_id or "")
        s.sync()

    @staticmethod
    def get_chat_model_id() -> str:
        """Return the last model picked in the AI chat composer, or ``""``."""
        s = _get_settings()
        return str(s.value(_KEY_CHAT_MODEL, "") or "").strip()

    @staticmethod
    def set_chat_model_id(model_id: str) -> None:
        """Persist the AI chat composer model selection (``""`` to clear)."""
        s = _get_settings()
        s.setValue(_KEY_CHAT_MODEL, model_id or "")
        s.sync()

    @staticmethod
    def get_chat_session_id() -> str:
        """Return the last active AI chat session id, or ``""`` when unset."""
        s = _get_settings()
        return str(s.value(_KEY_CHAT_SESSION, "") or "").strip()

    @staticmethod
    def is_chat_session_restore_cleared() -> bool:
        """Return True after **New chat** cleared the restore target."""
        s = _get_settings()
        return bool(s.value(_KEY_CHAT_SESSION_CLEARED, False))

    @staticmethod
    def set_chat_session_id(session_id: str) -> None:
        """Persist the active chat session id.

        Passing ``""`` marks restore as intentionally blank (**New chat**).
        """
        s = _get_settings()
        if session_id:
            s.setValue(_KEY_CHAT_SESSION, session_id)
            s.remove(_KEY_CHAT_SESSION_CLEARED)
        else:
            s.remove(_KEY_CHAT_SESSION)
            s.setValue(_KEY_CHAT_SESSION_CLEARED, True)
        s.sync()

    @staticmethod
    def save_all(entries: list[AiModelEntry]) -> None:
        """Persist models and clear any legacy default id (flushes to disk)."""
        AiConfig.set_models(entries)
        AiConfig.set_default_model_id("")


__all__ = [
    "AiConfig",
    "AiModelEntry",
    "merge_tier_backfill_results",
    "model_entry_enabled",
]
