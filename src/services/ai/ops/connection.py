"""Test LLM provider credentials (not a specific saved model row)."""

from __future__ import annotations

from services.ai.ai_config import AiModelEntry
from services.ai.ai_logging import log as ai_log
from services.ai.llm_service import AiLlmService
from services.ai.ops.models import fetch_provider_models, fetch_provider_models_live
from services.ai.sdk_env import CONNECTION_TEST_TIMEOUT_SEC
from services.scripting.secret_store import get_secret
from services.ai.provider_catalog import (
    ModelSpec,
    probe_model_for_provider,
    provider_by_key,
    provider_lists_models_live,
)


def credential_validation_error(
    *,
    provider_key: str,
    base_url: str = "",
    api_version: str = "",
    auth_kind: str = "none",
    auth_ref: str = "",
) -> str | None:
    """Return a user-facing error when required fields are missing, else ``None``."""
    spec = provider_by_key(provider_key)
    if spec is None:
        return f"Unknown provider: {provider_key}"
    if any(f.field_id == "api_key" and f.required for f in spec.credential_fields) and (
        auth_kind == "none" or not auth_ref
    ):
        return "API key is required for this provider."
    if (
        auth_kind == "token"
        and auth_ref
        and any(f.field_id == "api_key" and f.required for f in spec.credential_fields)
        and not get_secret(auth_ref)
    ):
        return "API key is not available. Re-enter the provider API key."
    if (
        any(f.field_id == "base_url" and f.required for f in spec.credential_fields)
        and not base_url.strip()
    ):
        return "Base URL is required for this provider."
    if (
        any(f.field_id == "api_version" and f.required for f in spec.credential_fields)
        and not api_version.strip()
    ):
        return "API version is required for this provider."
    return None


def _probe_entry(
    *,
    provider_key: str,
    base_url: str,
    api_version: str,
    auth_kind: str,
    auth_ref: str,
    entry_id: str,
) -> AiModelEntry | None:
    """Build a throwaway entry used only for a provider connectivity ping."""
    spec = provider_by_key(provider_key)
    model = probe_model_for_provider(provider_key)
    if spec is None or not model:
        return None
    return {
        "id": entry_id,
        "provider": provider_key,
        "label": spec.label,
        "model": model,
        "base_url": base_url,
        "api_version": api_version,
        "auth_kind": "token" if auth_kind == "token" else "none",
        "auth_ref": auth_ref,
    }


def _ping_provider(
    *,
    provider_key: str,
    base_url: str,
    api_version: str,
    auth_kind: str,
    auth_ref: str,
    entry_id: str,
    timeout_sec: int,
) -> tuple[bool, str]:
    """Chat completion ping for catalog-only providers (Anthropic, Gemini, …)."""
    entry = _probe_entry(
        provider_key=provider_key,
        base_url=base_url,
        api_version=api_version,
        auth_kind=auth_kind,
        auth_ref=auth_ref,
        entry_id=entry_id,
    )
    if entry is None:
        return False, f"Unknown provider: {provider_key}"
    model = entry["model"]
    ai_log(f"API test: {provider_key} → {model} ({timeout_sec}s timeout)")
    ok, detail = AiLlmService.test(entry, timeout_sec=timeout_sec)
    if ok:
        ai_log(f"Provider test OK ({provider_key})")
    else:
        ai_log(f"Provider test failed ({provider_key}): {detail}")
    return ok, detail


def setup_provider(
    *,
    provider_key: str,
    base_url: str = "",
    api_version: str = "",
    auth_kind: str = "none",
    auth_ref: str = "",
    entry_id: str = "probe",
    timeout_sec: int | None = None,
    bulk: bool = True,
    ollama_default_context: int = 0,
) -> tuple[bool, str, tuple[ModelSpec, ...]]:
    """Validate credentials, list models (HTTP) or ping + catalog. Never raises."""
    timeout = timeout_sec if timeout_sec is not None else CONNECTION_TEST_TIMEOUT_SEC
    err = credential_validation_error(
        provider_key=provider_key,
        base_url=base_url,
        api_version=api_version,
        auth_kind=auth_kind,
        auth_ref=auth_ref,
    )
    if err:
        return False, err, ()
    spec = provider_by_key(provider_key)
    assert spec is not None
    endpoint = base_url.strip() or spec.default_base_url or "(default)"
    if provider_lists_models_live(provider_key):
        ai_log(f"Listing models: {provider_key} → {endpoint} ({timeout}s timeout)")
        ok, detail, models = fetch_provider_models_live(
            provider_key=provider_key,
            base_url=base_url,
            api_version=api_version,
            auth_kind=auth_kind,
            auth_ref=auth_ref,
            http_timeout=float(timeout),
            bulk=bulk,
            ollama_default_context=ollama_default_context,
        )
        if ok:
            ai_log(f"Provider OK ({provider_key})")
        else:
            ai_log(f"Provider failed ({provider_key}): {detail}")
        return ok, detail, models
    ok, detail = _ping_provider(
        provider_key=provider_key,
        base_url=base_url,
        api_version=api_version,
        auth_kind=auth_kind,
        auth_ref=auth_ref,
        entry_id=entry_id,
        timeout_sec=timeout,
    )
    if not ok:
        return False, detail, ()
    ai_log("API OK — loading model catalog…")
    models = fetch_provider_models(
        provider_key=provider_key,
        base_url=base_url,
        api_version=api_version,
        auth_kind=auth_kind,
        auth_ref=auth_ref,
        bulk=bulk,
        ollama_default_context=ollama_default_context,
    )
    count = len(models)
    summary = f"Connected — {count} model(s) in catalog"
    return True, summary, models


def verify_provider_connection(
    *,
    provider_key: str,
    base_url: str = "",
    api_version: str = "",
    auth_kind: str = "none",
    auth_ref: str = "",
    entry_id: str = "probe",
    timeout_sec: int | None = None,
) -> tuple[bool, str]:
    """Check provider credentials. Live-list providers use HTTP only (no LLM ping)."""
    ok, detail, _ = setup_provider(
        provider_key=provider_key,
        base_url=base_url,
        api_version=api_version,
        auth_kind=auth_kind,
        auth_ref=auth_ref,
        entry_id=entry_id,
        timeout_sec=timeout_sec,
    )
    return ok, detail


__all__ = [
    "credential_validation_error",
    "setup_provider",
    "verify_provider_connection",
]
