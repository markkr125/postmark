"""build_llm composition + test() success/failure with fakes."""

from __future__ import annotations

import sys
import types

import pytest

from services.ai.ai_config import AiModelEntry
from services.ai.llm_service import AiLlmService, resolve_litellm_model
from services.ai.reasoning_effort import (
    chat_reasoning_effort_for_litellm,
    minimum_reasoning_effort_for,
)


def _entry(**kw: object) -> AiModelEntry:
    base: AiModelEntry = {
        "id": "id1",
        "provider": "openai",
        "label": "L",
        "model": "openai/gpt-4o",
        "base_url": "https://x",
        "api_version": "v1",
        "auth_kind": "token",
        "auth_ref": "ai:id1",
    }
    base.update(kw)  # type: ignore[typeddict-item]
    return base


def _install_fake_sdk(
    monkeypatch: pytest.MonkeyPatch,
    *,
    text: str = "pong",
    raise_exc: Exception | None = None,
) -> None:
    mod = types.ModuleType("openhands.sdk")

    class _TextContent:
        def __init__(self, text: str = "") -> None:
            self.text = text

    class _Message:
        def __init__(self, role: str = "user", content: object = None) -> None:
            self.role = role
            self.content = content or []

    class _Resp:
        def __init__(self, t: str) -> None:
            self.message = _Message(content=[_TextContent(t)])

    class _LLM:
        def __init__(self, **kw: object) -> None:
            self.kw = kw

        def completion(self, messages: object) -> _Resp:
            if raise_exc:
                raise raise_exc
            return _Resp(text)

    mod.LLM = _LLM  # type: ignore[attr-defined]
    mod.Message = _Message  # type: ignore[attr-defined]
    mod.TextContent = _TextContent  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openhands", types.ModuleType("openhands"))
    monkeypatch.setitem(sys.modules, "openhands.sdk", mod)


def test_build_llm_composes_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """build_llm passes model, base_url, api_version, and max_output_tokens."""
    _install_fake_sdk(monkeypatch)
    import services.ai.llm_service as svc

    monkeypatch.setattr(svc, "get_secret", lambda _ref: "sk-test")
    llm = AiLlmService.build_llm(_entry(), max_output_tokens=16)
    kw = getattr(llm, "kw", {})
    assert kw["model"] == "openai/gpt-4o"
    assert kw["base_url"] == "https://x"
    assert kw["api_version"] == "v1"
    assert kw["max_output_tokens"] == 16
    assert kw.get("extra_headers") is None
    assert "reasoning_summary" not in kw


def test_build_llm_openai_chat_requests_reasoning_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streaming OpenAI reasoning models request Responses reasoning summaries."""
    _install_fake_sdk(monkeypatch)
    import services.ai.llm_service as svc

    monkeypatch.setattr(svc, "get_secret", lambda _ref: "sk-test")
    entry = _entry(
        model="openai/gpt-5.4-mini",
        reasoning_efforts=["low", "medium", "high"],
        reasoning_effort="medium",
    )
    llm = AiLlmService.build_llm(
        entry,
        stream=True,
        usage_id="postmark-chat-session",
        reasoning_effort="medium",
    )
    kw = getattr(llm, "kw", {})
    assert kw["reasoning_summary"] == "detailed"


def test_build_llm_ollama_chat_skips_reasoning_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ollama chat must not set OpenAI-only reasoning_summary."""
    import os

    import services.ai.llm_service as svc

    monkeypatch.setattr(svc, "get_secret", lambda _ref: "sk-test")
    os.environ["ALLOW_SHORT_CONTEXT_WINDOWS"] = "true"
    entry = _entry(
        provider="ollama",
        model="ollama/gpt-oss:20b",
        base_url="",
        auth_kind="none",
        auth_ref="",
    )
    llm = AiLlmService.build_llm(
        entry,
        stream=True,
        usage_id="postmark-chat-test",
        reasoning_effort="medium",
    )
    assert getattr(llm, "reasoning_summary", None) is None


def test_build_llm_ollama_extra_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama entries set Content-Type for strict reverse-proxies."""
    import os

    import services.ai.llm_service as svc

    monkeypatch.setattr(svc, "get_secret", lambda _ref: "sk-test")
    os.environ["ALLOW_SHORT_CONTEXT_WINDOWS"] = "true"
    entry = _entry(
        provider="ollama",
        model="ollama/llama3",
        base_url="",
        auth_kind="none",
        auth_ref="",
    )
    llm = AiLlmService.build_llm(entry, usage_id="postmark-chat-test")
    assert llm.extra_headers == {"Content-Type": "application/json"}


def test_test_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """test() returns success when the fake SDK responds."""
    _install_fake_sdk(monkeypatch, text="pong")
    import services.ai.llm_service as svc

    monkeypatch.setattr(svc, "get_secret", lambda _ref: "sk-test")
    ok, detail = AiLlmService.test(_entry())
    assert ok is True
    assert "pong" in detail


def test_test_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """test() returns failure when completion raises."""
    _install_fake_sdk(monkeypatch, raise_exc=RuntimeError("boom"))
    import services.ai.llm_service as svc

    monkeypatch.setattr(svc, "get_secret", lambda _ref: "sk-test")
    ok, detail = AiLlmService.test(_entry())
    assert ok is False
    assert "boom" in detail


def test_build_llm_clears_reasoning_for_ollama_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    """Streaming Ollama chat must override OpenHands default reasoning_effort."""
    import os

    import services.ai.llm_service as svc

    monkeypatch.setattr(svc, "get_secret", lambda _ref: "sk-test")
    os.environ["ALLOW_SHORT_CONTEXT_WINDOWS"] = "true"
    entry = _entry(
        provider="ollama",
        model="ollama/gpt-oss:20b",
        base_url="",
        auth_kind="none",
        auth_ref="",
    )
    llm = AiLlmService.build_llm(
        entry,
        stream=True,
        usage_id="postmark-chat-test",
        reasoning_effort="xhigh",
    )
    assert llm.stream is True
    assert llm.reasoning_effort is None
    assert llm.model == "ollama_chat/gpt-oss:20b"
    assert llm.base_url == "http://127.0.0.1:11434"


def test_resolve_litellm_model_uses_ollama_chat_for_postmark_chat() -> None:
    """Ollama chat runs route through LiteLLM's ollama_chat provider."""
    entry: AiModelEntry = {
        "id": "o1",
        "provider": "ollama",
        "label": "gpt-oss",
        "model": "ollama/gpt-oss:20b",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
    }
    assert resolve_litellm_model(entry, usage_id="postmark-chat-abc") == "ollama_chat/gpt-oss:20b"
    assert resolve_litellm_model(entry, usage_id="postmark-config-test") == "ollama/gpt-oss:20b"


def test_build_llm_ollama_chat_does_not_pass_reasoning_effort_to_litellm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ollama chat must not leak OpenHands' default reasoning_effort into LiteLLM."""
    import os

    from openhands.sdk.llm.options.chat_options import select_chat_options

    import services.ai.llm_service as svc

    monkeypatch.setattr(svc, "get_secret", lambda _ref: "sk-test")
    os.environ["ALLOW_SHORT_CONTEXT_WINDOWS"] = "true"
    entry = _entry(
        provider="ollama",
        model="ollama/gpt-oss:20b",
        base_url="",
        auth_kind="none",
        auth_ref="",
    )
    llm = AiLlmService.build_llm(
        entry,
        stream=True,
        usage_id="postmark-chat-test",
        reasoning_effort="high",
    )
    opts = select_chat_options(llm, {}, has_tools=False)
    assert "reasoning_effort" not in opts


def test_resolve_llm_base_url_uses_provider_default() -> None:
    """Empty model base_url falls back to the Ollama provider default."""
    entry: AiModelEntry = {
        "id": "o1",
        "provider": "ollama",
        "label": "gpt-oss",
        "model": "ollama/gpt-oss:20b",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
    }
    from services.ai.llm_service import resolve_llm_base_url

    assert resolve_llm_base_url(entry) == "http://127.0.0.1:11434"


def test_build_llm_ollama_chat_passes_context_and_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ollama chat runs pass num_ctx and think via litellm_extra_body."""
    import os

    import services.ai.llm_service as svc

    monkeypatch.setattr(svc, "get_secret", lambda _ref: "sk-test")
    os.environ["ALLOW_SHORT_CONTEXT_WINDOWS"] = "true"
    entry = _entry(
        provider="ollama",
        model="ollama/qwen3:8b",
        base_url="",
        auth_kind="none",
        auth_ref="",
        thinking=True,
    )
    llm = AiLlmService.build_llm(
        entry,
        stream=True,
        usage_id="postmark-chat-test",
        run_context_tokens=8192,
        thinking_enabled="off",
    )
    assert llm.litellm_extra_body == {"num_ctx": 8192, "think": False}
    assert llm.num_retries == 0


def test_build_llm_ollama_chat_harmony_passes_think_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Harmony models pass think level via extra_body when streaming."""
    import os

    import services.ai.llm_service as svc

    monkeypatch.setattr(svc, "get_secret", lambda _ref: "sk-test")
    os.environ["ALLOW_SHORT_CONTEXT_WINDOWS"] = "true"
    entry = _entry(
        provider="ollama",
        model="ollama/gpt-oss:20b",
        base_url="",
        auth_kind="none",
        auth_ref="",
    )
    llm = AiLlmService.build_llm(
        entry,
        stream=True,
        usage_id="postmark-chat-test",
        run_context_tokens=4096,
        reasoning_effort="medium",
    )
    assert llm.litellm_extra_body == {"num_ctx": 4096, "think": "medium"}
    assert llm.num_retries == 0


def test_chat_reasoning_effort_maps_xhigh_to_high_for_harmony_offline() -> None:
    """Harmony models map xhigh to high when streaming is disabled."""
    entry: AiModelEntry = {
        "id": "o1",
        "provider": "ollama",
        "label": "gpt-oss",
        "model": "ollama/gpt-oss:20b",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
    }
    assert chat_reasoning_effort_for_litellm(entry, "xhigh", streaming=False) == "high"


def test_minimum_reasoning_effort_for_harmony_is_low() -> None:
    """Harmony Ollama models cannot disable thinking; lowest is ``low``."""
    entry = _entry(provider="ollama", model="ollama/gpt-oss:20b")
    assert minimum_reasoning_effort_for(entry) == "low"


def test_minimum_reasoning_effort_for_leveled_model() -> None:
    """Leveled models pick the lowest token from the supported set."""
    entry = _entry(
        reasoning_efforts=["medium", "high", "minimal"],
        reasoning_default="medium",
    )
    assert minimum_reasoning_effort_for(entry) == "minimal"


def test_minimum_reasoning_effort_defaults_to_off() -> None:
    """Models without leveled reasoning use boolean ``off``."""
    assert minimum_reasoning_effort_for(_entry()) == "off"
