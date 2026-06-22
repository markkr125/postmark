"""Provider-level test and model listing."""

from __future__ import annotations

import pytest

from services.ai.ops.connection import setup_provider, verify_provider_connection
from services.ai.ops.models import fetch_provider_models, fetch_provider_models_live


def test_test_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anthropic without a key fails validation before SDK import."""
    ok, detail = verify_provider_connection(
        provider_key="anthropic",
        auth_kind="none",
        auth_ref="",
    )
    assert ok is False
    assert "API key" in detail


def test_fetch_ollama_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama listing uses tags plus /api/show for context."""

    class _Resp:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None: ...

        def json(self) -> dict[str, object]:
            return self._payload

    class _Client:
        def __init__(self, *a: object, **k: object) -> None: ...

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *a: object) -> None: ...

        def get(self, url: str, headers: dict[str, str] | None = None) -> _Resp:
            assert "api/tags" in url
            return _Resp({"models": [{"name": "llama3:latest"}]})

        def post(
            self, url: str, json: dict[str, object], headers: dict[str, str] | None = None
        ) -> _Resp:
            assert "api/show" in url
            return _Resp(
                {
                    "model_info": {"llama.context_length": 8192},
                    "capabilities": ["completion", "tools"],
                }
            )

    monkeypatch.setattr("services.ai.ops.models.httpx.Client", _Client)
    monkeypatch.setattr("services.ai.ops.model_metadata.httpx.Client", _Client)
    models = fetch_provider_models(
        provider_key="ollama",
        base_url="http://127.0.0.1:11434",
        auth_kind="none",
        auth_ref="",
    )
    assert len(models) == 1
    assert models[0].model == "ollama/llama3:latest"
    assert models[0].context == 8192


def test_ollama_setup_lists_without_llm_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama connection test must not chat-complete a guessed model name."""
    ping_calls: list[str] = []

    def _no_ping(entry: object, **kwargs: object) -> tuple[bool, str]:
        ping_calls.append(str(entry))
        return True, "should not run"

    monkeypatch.setattr("services.ai.ops.connection.AiLlmService.test", _no_ping)

    class _Resp:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None: ...

        def json(self) -> dict[str, object]:
            return self._payload

    class _Client:
        def __init__(self, *a: object, **k: object) -> None: ...

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *a: object) -> None: ...

        def get(self, url: str, headers: dict[str, str] | None = None) -> _Resp:
            return _Resp({"models": [{"name": "qwen2.5:latest"}]})

        def post(
            self, url: str, json: dict[str, object], headers: dict[str, str] | None = None
        ) -> _Resp:
            return _Resp(
                {
                    "model_info": {"qwen2.5.context_length": 32768},
                    "capabilities": ["completion", "tools"],
                }
            )

    monkeypatch.setattr("services.ai.ops.models.httpx.Client", _Client)
    monkeypatch.setattr("services.ai.ops.model_metadata.httpx.Client", _Client)

    ok, detail, models = setup_provider(
        provider_key="ollama",
        base_url="http://127.0.0.1:11434",
        auth_kind="none",
        auth_ref="",
    )
    assert ping_calls == []
    assert ok is True
    assert "Found" in detail
    assert models[0].model == "ollama/qwen2.5:latest"


def test_test_provider_delegates_to_llm_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """Catalog providers still use a cheap API ping with a probe model."""
    calls: list[str] = []

    def _fake_test(entry: object, **kwargs: object) -> tuple[bool, str]:
        assert isinstance(entry, dict)
        calls.append(str(entry.get("model")))
        return True, "ok"

    monkeypatch.setattr("services.ai.ops.connection.AiLlmService.test", _fake_test)
    monkeypatch.setattr(
        "services.ai.ops.connection.fetch_provider_models",
        lambda **kwargs: (),
    )

    monkeypatch.setattr(
        "services.ai.ops.connection.get_secret",
        lambda _ref: "sk",
    )

    ok, detail = verify_provider_connection(
        provider_key="anthropic",
        auth_kind="token",
        auth_ref="ai:x",
        entry_id="x",
    )
    assert ok is True
    assert "Connected" in detail
    assert calls == ["anthropic/claude-3-5-haiku-20241022"]


def test_openai_setup_lists_without_llm_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI connection test uses GET /v1/models, not a chat ping."""
    ping_calls: list[int] = []

    def _no_ping(entry: object, **kwargs: object) -> tuple[bool, str]:
        ping_calls.append(1)
        return True, "nope"

    monkeypatch.setattr("services.ai.ops.connection.AiLlmService.test", _no_ping)
    monkeypatch.setattr("services.ai.ops.connection.get_secret", lambda _ref: "sk-test")
    monkeypatch.setattr("services.ai.ops.models.get_secret", lambda _ref: "sk-test")

    class _Resp:
        def raise_for_status(self) -> None: ...

        def json(self) -> dict[str, object]:
            return {"data": [{"id": "gpt-4o-mini"}]}

    class _Client:
        def __init__(self, *a: object, **k: object) -> None: ...

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *a: object) -> None: ...

        def get(self, url: str, headers: dict[str, str] | None = None) -> _Resp:
            assert url.endswith("/models")
            return _Resp()

    monkeypatch.setattr("services.ai.ops.models.httpx.Client", _Client)
    ok, _, models = setup_provider(
        provider_key="openai",
        auth_kind="token",
        auth_ref="ai:x",
    )
    assert ping_calls == []
    assert ok is True
    assert models[0].model == "openai/gpt-4o-mini"


def test_fetch_live_empty_ollama_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty tag list is a failed connection, not a silent catalog fallback."""

    class _Resp:
        def raise_for_status(self) -> None: ...

        def json(self) -> dict[str, object]:
            return {"models": []}

    class _Client:
        def __init__(self, *a: object, **k: object) -> None: ...

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *a: object) -> None: ...

        def get(self, url: str, headers: dict[str, str] | None = None) -> _Resp:
            return _Resp()

    monkeypatch.setattr("services.ai.ops.models.httpx.Client", _Client)
    ok, detail, models = fetch_provider_models_live(
        provider_key="ollama",
        base_url="http://127.0.0.1:11434",
    )
    assert ok is False
    assert "tool-capable" in detail
    assert models == ()
