"""Build OpenHands ``LLM`` objects from config and test connectivity."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING

from services.ai.ai_config import AiModelEntry
from services.ai.ai_logging import log as ai_log
from services.ai.sdk_env import CONNECTION_TEST_TIMEOUT_SEC
from services.ai.sdk_env import ensure_openhands_env
from services.scripting.secret_store import get_default_store

ensure_openhands_env()

if TYPE_CHECKING:
    from openhands.sdk import LLM


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


class AiLlmService:
    """Construct and test ``LLM`` instances. SDK imported lazily."""

    @staticmethod
    def build_llm(
        entry: AiModelEntry,
        *,
        usage_id: str = "postmark-config-test",
        max_output_tokens: int | None = None,
        timeout_sec: int | None = None,
    ) -> LLM:
        """Build an ``openhands.sdk.LLM`` from *entry* (resolving the stored key)."""
        from openhands.sdk import LLM  # lazy: heavy dependency
        from pydantic import SecretStr

        api_key: SecretStr | None = None
        if entry["auth_kind"] != "none" and entry["auth_ref"]:
            raw = get_default_store().get(entry["auth_ref"])
            if raw:
                api_key = SecretStr(raw)

        timeout = timeout_sec if timeout_sec is not None else CONNECTION_TEST_TIMEOUT_SEC
        return LLM(
            model=entry["model"],
            api_key=api_key,
            base_url=entry["base_url"].strip() or None,
            api_version=entry["api_version"].strip() or None,
            max_output_tokens=max_output_tokens,
            timeout=timeout,
            usage_id=usage_id,
        )

    @staticmethod
    def test(entry: AiModelEntry, *, timeout_sec: int | None = None) -> tuple[bool, str]:
        """Send a cheap ping. Return ``(ok, detail_or_error)``. Never raises."""
        timeout = timeout_sec if timeout_sec is not None else CONNECTION_TEST_TIMEOUT_SEC
        model = entry.get("model", "")
        ai_log(f"Chat test: {model} (timeout {timeout}s)")
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


__all__ = ["AiLlmService"]
