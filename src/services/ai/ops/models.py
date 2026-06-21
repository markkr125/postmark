"""Fetch selectable models after provider credentials are verified."""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx

from services.ai.ai_logging import log as ai_log
from services.ai.ops.model_filters import _id_looks_non_chat, filter_settings_models
from services.ai.ops.model_metadata import (
    enrich_litellm_spec,
    enrich_ollama_specs_parallel,
    enrich_openai_specs,
    enrich_openrouter_spec,
    litellm_context_tokens,
)
from services.ai.sdk_env import MODEL_LIST_TIMEOUT_SEC
from services.ai.provider_catalog import (
    LIVE_MODEL_LIST_KINDS,
    ModelSpec,
    ProviderSpec,
    provider_by_key,
)
from services.scripting.secret_store import get_secret

logger = logging.getLogger(__name__)


def _context_tokens(raw: object) -> int:
    if isinstance(raw, int) and raw > 0:
        return raw
    return 0


def _ollama_list_tags(base_url: str, api_key: str, *, timeout: float) -> tuple[ModelSpec, ...]:
    """List models from ``/api/tags`` (context filled by ``/api/show`` enrichment)."""
    root = base_url.strip().rstrip("/") or "http://127.0.0.1:11434"
    url = urljoin(root + "/", "api/tags")
    headers: dict[str, str] = {}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    ai_log(f"GET {url}")
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers=headers or None)
        resp.raise_for_status()
        data = resp.json()
    out: list[ModelSpec] = []
    for row in data.get("models") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name or _id_looks_non_chat(name):
            continue
        label = name.split(":")[0]
        out.append(ModelSpec(f"ollama/{name}", label, 0, False, False, True))
    return tuple(sorted(out, key=lambda m: m.label.lower()))


def _ollama_models(
    base_url: str,
    api_key: str,
    *,
    timeout: float,
    default_context: int = 0,
) -> tuple[ModelSpec, ...]:
    tags = _ollama_list_tags(base_url, api_key, timeout=timeout)
    return enrich_ollama_specs_parallel(
        tags,
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        default_context=default_context,
    )


def _openai_list_ids(base_url: str, api_key: str, *, timeout: float) -> tuple[ModelSpec, ...]:
    root = base_url.strip().rstrip("/") or "https://api.openai.com/v1"
    url = urljoin(root.rstrip("/") + "/", "models")
    headers = {"Authorization": f"Bearer {api_key}"}
    ai_log(f"GET {url}")
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    out: list[ModelSpec] = []
    for row in data.get("data") or []:
        if not isinstance(row, dict):
            continue
        mid = str(row.get("id") or "").strip()
        if not mid or _id_looks_non_chat(mid):
            continue
        full = f"openai/{mid}"
        out.append(ModelSpec(full, mid, 0, False, False, True))
    return tuple(sorted(out, key=lambda m: m.model))


def _openai_models(base_url: str, api_key: str, *, timeout: float) -> tuple[ModelSpec, ...]:
    """OpenAI ``/models`` has no context; resolve via LiteLLM per model id."""
    listed = _openai_list_ids(base_url, api_key, timeout=timeout)
    ai_log(f"Resolving context for {len(listed)} OpenAI model(s) via LiteLLM…")
    return enrich_openai_specs(listed)


def _openrouter_models(api_key: str, *, timeout: float) -> tuple[ModelSpec, ...]:
    headers = {"Authorization": f"Bearer {api_key}"}
    url = "https://openrouter.ai/api/v1/models"
    ai_log(f"GET {url}")
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    out: list[ModelSpec] = []
    for row in data.get("data") or []:
        if not isinstance(row, dict):
            continue
        mid = str(row.get("id") or "").strip()
        if not mid:
            continue
        label = str(row.get("name") or mid)
        ctx = _context_tokens(row.get("context_length"))
        if ctx <= 0:
            ctx = litellm_context_tokens(f"openrouter/{mid}")
        base = ModelSpec(f"openrouter/{mid}", label, ctx, False, False, True)
        enriched = enrich_openrouter_spec(base, row)
        if enriched is not None:
            out.append(enriched)
    return tuple(out)


def _azure_models(
    base_url: str, api_version: str, api_key: str, *, timeout: float
) -> tuple[ModelSpec, ...]:
    root = base_url.strip().rstrip("/")
    url = f"{root}/openai/deployments?api-version={api_version.strip()}"
    headers = {"api-key": api_key}
    ai_log(f"GET {url}")
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    out: list[ModelSpec] = []
    for row in data.get("data") or []:
        if not isinstance(row, dict):
            continue
        dep = str(row.get("id") or row.get("name") or "").strip()
        if not dep:
            continue
        full = f"azure/{dep}"
        ctx = litellm_context_tokens(full)
        base = ModelSpec(full, dep, ctx, False, False, True)
        enriched = enrich_litellm_spec(base)
        if enriched is not None:
            out.append(enriched)
    return tuple(out)


def _litellm_catalog(spec: ProviderSpec) -> tuple[ModelSpec, ...]:
    try:
        import litellm
    except ImportError:
        return filter_settings_models(spec.default_models)
    names = litellm.models_by_provider.get(spec.prefix)
    if not names:
        return filter_settings_models(spec.default_models)
    out: list[ModelSpec] = []
    for name in names:
        mid = f"{spec.prefix}/{name}" if "/" not in name else name
        if not mid.startswith(f"{spec.prefix}/"):
            mid = f"{spec.prefix}/{name}"
        if _id_looks_non_chat(mid):
            continue
        ctx = litellm_context_tokens(mid)
        base = ModelSpec(mid, name, ctx, False, False, True)
        enriched = enrich_litellm_spec(base)
        if enriched is not None:
            out.append(enriched)
    return tuple(out[:120]) if out else filter_settings_models(spec.default_models)


def _fetch_live_models(
    spec: ProviderSpec,
    *,
    base_url: str,
    api_version: str,
    api_key: str,
    timeout: float,
    ollama_default_context: int = 0,
) -> tuple[ModelSpec, ...]:
    """Call the provider model-list HTTP API and enrich metadata. Raises on failure."""
    fetch = spec.models_fetch
    if fetch == "ollama":
        return _ollama_models(
            base_url or spec.default_base_url,
            api_key,
            timeout=timeout,
            default_context=ollama_default_context,
        )
    if fetch == "openai":
        if not api_key:
            raise ValueError("API key is required.")
        return _openai_models(base_url, api_key, timeout=timeout)
    if fetch == "openrouter":
        if not api_key:
            raise ValueError("API key is required.")
        return _openrouter_models(api_key, timeout=timeout)
    if fetch == "azure":
        if not api_key or not base_url.strip() or not api_version.strip():
            raise ValueError("API key, base URL, and API version are required.")
        return _azure_models(base_url, api_version, api_key, timeout=timeout)
    if fetch == "openai_compatible":
        if not base_url.strip():
            raise ValueError("Base URL is required.")
        return _openai_models(base_url, api_key, timeout=timeout)
    raise ValueError(f"Provider {spec.key} has no live model list.")


def fetch_provider_models_live(
    *,
    provider_key: str,
    base_url: str = "",
    api_version: str = "",
    auth_kind: str = "none",
    auth_ref: str = "",
    http_timeout: float | None = None,
    bulk: bool = True,
    ollama_default_context: int = 0,
) -> tuple[bool, str, tuple[ModelSpec, ...]]:
    """List models over HTTP with per-model context metadata. Used for connection test."""
    _ = bulk
    spec = provider_by_key(provider_key)
    if spec is None:
        return False, f"Unknown provider: {provider_key}", ()
    if spec.models_fetch not in LIVE_MODEL_LIST_KINDS:
        return False, f"Provider {provider_key} has no live model list.", ()
    timeout = http_timeout if http_timeout is not None else MODEL_LIST_TIMEOUT_SEC
    api_key = ""
    if auth_kind == "token" and auth_ref:
        api_key = get_secret(auth_ref) or ""
    try:
        live = _fetch_live_models(
            spec,
            base_url=base_url,
            api_version=api_version,
            api_key=api_key,
            timeout=timeout,
            ollama_default_context=ollama_default_context,
        )
        models = filter_settings_models(live)
        if not models:
            return False, "No tool-capable chat models found at this endpoint.", ()
        count = len(models)
        return True, f"Found {count} model(s)", models
    except Exception as exc:
        ai_log(f"Model list failed: {exc}")
        logger.debug("fetch_provider_models_live(%s) failed: %s", provider_key, exc)
        return False, str(exc), ()


def fetch_provider_models(
    *,
    provider_key: str,
    base_url: str = "",
    api_version: str = "",
    auth_kind: str = "none",
    auth_ref: str = "",
    http_timeout: float | None = None,
    bulk: bool = True,
    ollama_default_context: int = 0,
) -> tuple[ModelSpec, ...]:
    """Return models for *provider_key* with provider-specific context metadata."""
    _ = bulk
    spec = provider_by_key(provider_key)
    if spec is None:
        return ()
    timeout = http_timeout if http_timeout is not None else MODEL_LIST_TIMEOUT_SEC
    api_key = ""
    if auth_kind == "token" and auth_ref:
        api_key = get_secret(auth_ref) or ""
    fetch = spec.models_fetch
    ai_log(f"Fetching models for {provider_key} (timeout {timeout}s)")
    try:
        if fetch in LIVE_MODEL_LIST_KINDS:
            if fetch == "openai" and not api_key:
                return filter_settings_models(spec.default_models)
            if fetch == "openrouter" and not api_key:
                return filter_settings_models(spec.default_models)
            if fetch == "azure" and (
                not api_key or not base_url.strip() or not api_version.strip()
            ):
                return filter_settings_models(spec.default_models)
            if fetch == "openai_compatible" and not base_url.strip():
                return filter_settings_models(spec.default_models)
            live = _fetch_live_models(
                spec,
                base_url=base_url,
                api_version=api_version,
                api_key=api_key,
                timeout=timeout,
                ollama_default_context=ollama_default_context,
            )
            return filter_settings_models(live or spec.default_models)
        if fetch == "litellm":
            return filter_settings_models(_litellm_catalog(spec))
    except Exception as exc:
        ai_log(f"Model fetch failed: {exc}")
        logger.debug("fetch_provider_models(%s) failed: %s", provider_key, exc)
    return filter_settings_models(spec.default_models)


__all__ = ["fetch_provider_models", "fetch_provider_models_live"]
