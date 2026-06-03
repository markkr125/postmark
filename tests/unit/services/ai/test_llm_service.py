"""build_llm composition + test() success/failure with fakes."""

from __future__ import annotations

import sys
import types

import pytest

from services.ai.ai_config import AiModelEntry
from services.ai.llm_service import AiLlmService


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


class _Store:
    backend_id = "spy"

    def put(self, r: str, s: str) -> None: ...

    def get(self, r: str) -> str | None:
        return "sk-test"

    def delete(self, r: str) -> None: ...


def test_build_llm_composes_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """build_llm passes model, base_url, api_version, and max_output_tokens."""
    _install_fake_sdk(monkeypatch)
    import services.ai.llm_service as svc

    monkeypatch.setattr(svc, "get_default_store", lambda: _Store())
    llm = AiLlmService.build_llm(_entry(), max_output_tokens=16)
    kw = getattr(llm, "kw", {})
    assert kw["model"] == "openai/gpt-4o"
    assert kw["base_url"] == "https://x"
    assert kw["api_version"] == "v1"
    assert kw["max_output_tokens"] == 16


def test_test_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """test() returns success when the fake SDK responds."""
    _install_fake_sdk(monkeypatch, text="pong")
    import services.ai.llm_service as svc

    monkeypatch.setattr(svc, "get_default_store", lambda: _Store())
    ok, detail = AiLlmService.test(_entry())
    assert ok is True
    assert "pong" in detail


def test_test_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """test() returns failure when completion raises."""
    _install_fake_sdk(monkeypatch, raise_exc=RuntimeError("boom"))
    import services.ai.llm_service as svc

    monkeypatch.setattr(svc, "get_default_store", lambda: _Store())
    ok, detail = AiLlmService.test(_entry())
    assert ok is False
    assert "boom" in detail
