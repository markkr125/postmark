"""Persistence for configured AI model entries (QSettings-backed)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Literal, NotRequired, TypedDict, cast

from PySide6.QtCore import QSettings

from services.ai.provider_catalog import (
    context_tokens_for_model,
    migrate_provider_display_names,
)

logger = logging.getLogger(__name__)

_ORG = "Postmark"
_APP = "Postmark"
_KEY_MODELS = "ai/models"
_KEY_DEFAULT = "ai/default_model"
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
    enabled: NotRequired[bool]
    default_context: NotRequired[int]
    input_cost_per_token: NotRequired[float]
    output_cost_per_token: NotRequired[float]


def model_entry_enabled(entry: AiModelEntry) -> bool:
    """Whether the model is enabled for use (defaults to disabled)."""
    return bool(entry.get("enabled"))


def _get_settings() -> QSettings:
    return QSettings(_ORG, _APP)


class AiConfig:
    """Static accessors for AI model configuration in QSettings."""

    @staticmethod
    def get_models() -> list[AiModelEntry]:
        """Return configured models; drop malformed rows; migrate missing ids."""
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
        if migrated:
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
    def set_default_model_id(model_id: str) -> None:
        """Persist the default model id (``""`` to clear)."""
        s = _get_settings()
        s.setValue(_KEY_DEFAULT, model_id or "")
        s.sync()

    @staticmethod
    def save_all(entries: list[AiModelEntry]) -> None:
        """Persist models and clear any legacy default id (flushes to disk)."""
        AiConfig.set_models(entries)
        AiConfig.set_default_model_id("")


__all__ = ["AiConfig", "AiModelEntry", "model_entry_enabled"]
