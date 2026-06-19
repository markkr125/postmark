"""Build OpenHands ``LLM`` objects from config and test connectivity."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal, cast

from services.ai.ai_config import AiModelEntry
from services.ai.ai_logging import log as ai_log
from services.ai.provider_catalog import provider_by_key
from services.ai.reasoning_effort import (
    _is_ollama_model,
    chat_reasoning_effort_for_litellm,
    chat_reasoning_summary_for_llm,
    ollama_chat_litellm_extra_body,
)
from services.ai.sdk_env import (
    CHAT_RUN_TIMEOUT_SEC,
    CONNECTION_TEST_TIMEOUT_SEC,
    ensure_openhands_env,
)
from services.scripting.secret_store import get_default_store

ensure_openhands_env()

if TYPE_CHECKING:
    from openhands.sdk import LLM

_ReasoningEffort = Literal["low", "medium", "high", "xhigh", "none"]
_CHAT_USAGE_PREFIX = "postmark-chat"


def resolve_llm_base_url(entry: AiModelEntry) -> str | None:
    """Return the LiteLLM ``api_base`` for *entry*, applying provider defaults."""
    url = entry.get("base_url", "").strip().rstrip("/")
    if url:
        return url
    spec = provider_by_key(str(entry.get("provider", "")))
    if spec is not None and spec.default_base_url.strip():
        return spec.default_base_url.strip().rstrip("/")
    return None


def resolve_litellm_model(entry: AiModelEntry, *, usage_id: str) -> str:
    """Return the LiteLLM model id for *entry*, applying chat-specific routing.

    Ollama chat runs use LiteLLM's ``ollama_chat`` provider (``/api/chat``) instead
    of the ``ollama`` completion provider (``/api/generate``). The generate path
    converts messages to a single ``prompt`` and mishandles ``think`` for gpt-oss
    when OpenHands' default ``reasoning_effort="high"`` leaks through.
    """
    model = str(entry.get("model", "")).strip()
    if not model or not _is_ollama_model(entry):
        return model
    if not usage_id.startswith(_CHAT_USAGE_PREFIX):
        return model
    if model.startswith("ollama_chat/"):
        return model
    bare = model.removeprefix("ollama/")
    return f"ollama_chat/{bare}"


@contextmanager
def _allow_short_context_for_config_test():
    """Let OpenHands accept catalog models below its agent minimum for a ping only."""
    key = "ALLOW_SHORT_CONTEXT_WINDOWS"
    prev = os.environ.get(key)
    os.environ[key] = "true"
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev


@contextmanager
def _ollama_api_base_env(entry: AiModelEntry, base_url: str | None):
    """Scope ``OLLAMA_API_BASE`` for LiteLLM when targeting a local Ollama host."""
    if not base_url or not _is_ollama_model(entry):
        yield
        return
    key = "OLLAMA_API_BASE"
    prev = os.environ.get(key)
    os.environ[key] = base_url
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev


class AiLlmService:
    """Construct and test ``LLM`` instances. SDK imported lazily."""

    @staticmethod
    def build_llm(
        entry: AiModelEntry,
        *,
        usage_id: str = "postmark-config-test",
        max_output_tokens: int | None = None,
        timeout_sec: int | None = None,
        stream: bool = False,
        reasoning_effort: str | None = None,
        run_context_tokens: int | None = None,
        thinking_enabled: str | None = None,
    ) -> LLM:
        """Build an ``openhands.sdk.LLM`` from *entry* (resolving the stored key)."""
        from openhands.sdk import LLM  # lazy: heavy dependency
        from pydantic import SecretStr

        api_key: SecretStr | None = None
        if entry["auth_kind"] != "none" and entry["auth_ref"]:
            raw = get_default_store().get(entry["auth_ref"])
            if raw:
                api_key = SecretStr(raw)

        if timeout_sec is not None:
            timeout = timeout_sec
        elif stream and usage_id.startswith("postmark-chat"):
            timeout = CHAT_RUN_TIMEOUT_SEC
        else:
            timeout = CONNECTION_TEST_TIMEOUT_SEC

        base_url = resolve_llm_base_url(entry)
        litellm_model = resolve_litellm_model(entry, usage_id=usage_id)
        effort = chat_reasoning_effort_for_litellm(
            entry,
            reasoning_effort,
            streaming=stream,
        )
        # OpenHands defaults reasoning_effort to "high"; pass None explicitly to omit.
        resolved_effort: _ReasoningEffort | None = (
            None if effort is None else cast(_ReasoningEffort, effort)
        )
        if usage_id.startswith(_CHAT_USAGE_PREFIX) and _is_ollama_model(entry):
            resolved_effort = None

        # Strict Ollama reverse-proxies (FastAPI/Open WebUI) require an explicit
        # Content-Type; LiteLLM's native Ollama transport omits it. Direct-local
        # Ollama ignores it, so set it for every Ollama entry.
        extra_headers: dict[str, str] | None = None
        if _is_ollama_model(entry):
            extra_headers = {"Content-Type": "application/json"}

        litellm_extra_body: dict[str, Any] = {}
        num_retries: int | None = None
        if usage_id.startswith(_CHAT_USAGE_PREFIX) and _is_ollama_model(entry):
            litellm_extra_body = cast(
                dict[str, Any],
                ollama_chat_litellm_extra_body(
                    entry,
                    run_context_tokens=run_context_tokens,
                    thinking_enabled=thinking_enabled,
                    reasoning_effort=reasoning_effort,
                ),
            )
            # Local Ollama: skip OpenHands' default 5 retries (8s min backoff each).
            num_retries = 0

        llm_kwargs: dict[str, Any] = {
            "model": litellm_model,
            "api_key": api_key,
            "base_url": base_url,
            "api_version": entry["api_version"].strip() or None,
            "max_output_tokens": max_output_tokens,
            "timeout": timeout,
            "usage_id": usage_id,
            "stream": stream,
            "reasoning_effort": resolved_effort,
            "extra_headers": extra_headers,
            "litellm_extra_body": litellm_extra_body,
        }
        if num_retries is not None:
            llm_kwargs["num_retries"] = num_retries

        reasoning_summary = chat_reasoning_summary_for_llm(
            entry,
            usage_id=usage_id,
            streaming=stream,
        )
        if reasoning_summary is not None:
            llm_kwargs["reasoning_summary"] = reasoning_summary

        with _ollama_api_base_env(entry, base_url):
            llm = LLM(**llm_kwargs)
        if (
            usage_id.startswith(_CHAT_USAGE_PREFIX)
            and _is_ollama_model(entry)
            and llm.reasoning_effort is not None
        ):
            llm = llm.model_copy(update={"reasoning_effort": None}, deep=True)
        return llm

    @staticmethod
    def test(entry: AiModelEntry, *, timeout_sec: int | None = None) -> tuple[bool, str]:
        """Send a cheap ping. Return ``(ok, detail_or_error)``. Never raises."""
        timeout = timeout_sec if timeout_sec is not None else CONNECTION_TEST_TIMEOUT_SEC
        model = entry.get("model", "")
        base = resolve_llm_base_url(entry) or "(default)"
        ai_log(f"Chat test: {model} @ {base} (timeout {timeout}s)")
        try:
            from openhands.sdk import Message, TextContent

            with _allow_short_context_for_config_test():
                llm = AiLlmService.build_llm(entry, max_output_tokens=16, timeout_sec=timeout)
                resp = llm.completion(
                    messages=[Message(role="user", content=[TextContent(text="ping")])]
                )
            text = ""
            for item in resp.message.content:
                if isinstance(item, TextContent):
                    text = item.text
                    break
            detail = text.strip() or "Connection OK"
            ai_log(f"Chat test OK: {detail[:120]}")
            return True, detail
        except Exception as exc:
            ai_log(f"Chat test failed: {exc}")
            return False, str(exc)


__all__ = ["AiLlmService", "resolve_litellm_model", "resolve_llm_base_url"]
