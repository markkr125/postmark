"""Tests for reasoning metadata detection in model_metadata."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

from services.ai.ops.model_metadata import litellm_reasoning
from services.ai.reasoning_effort import (
    fill_gpt5_reasoning_gaps,
    ollama_reasoning_from_show,
    ollama_thinking_from_show,
)


def test_litellm_reasoning_no_support() -> None:
    """When supports_reasoning is false, return empty efforts."""
    fake = MagicMock()
    fake.supports_reasoning.return_value = False
    with patch.dict("sys.modules", {"litellm": fake}):
        ok, efforts, default = litellm_reasoning("openai/gpt-4o")
    assert ok is False
    assert efforts == ()
    assert default == ""


def test_litellm_reasoning_with_levels() -> None:
    """When supported, collect effort flags and default medium."""
    fake = MagicMock()
    fake.supports_reasoning.return_value = True

    def fake_get_model_info(model: str) -> dict[str, bool]:
        return {
            "supports_low_reasoning_effort": True,
            "supports_high_reasoning_effort": True,
        }

    with (
        patch("litellm.get_model_info", fake_get_model_info),
        patch("litellm.supports_reasoning", return_value=True),
    ):
        ok, efforts, default = litellm_reasoning("openai/gpt-5")
    assert ok is True
    assert "medium" in efforts
    assert "low" in efforts
    assert "high" in efforts
    assert default == "medium"


def test_litellm_reasoning_gpt5_none_medium_injects_low() -> None:
    """GPT-5 with none+medium flags gets ``low`` inserted between them."""
    fake = MagicMock()
    fake.supports_reasoning.return_value = True

    def fake_get_model_info(model: str) -> dict[str, bool]:
        return {"supports_none_reasoning_effort": True}

    with (
        patch("litellm.get_model_info", fake_get_model_info),
        patch("litellm.supports_reasoning", return_value=True),
    ):
        ok, efforts, default = litellm_reasoning("openai/gpt-5")
    assert ok is True
    assert efforts == ("none", "low", "medium")
    assert default == "medium"


def test_litellm_reasoning_gpt5_medium_xhigh_injects_high() -> None:
    """GPT-5 with medium+xhigh flags gets ``high`` inserted between them."""
    fake = MagicMock()
    fake.supports_reasoning.return_value = True

    def fake_get_model_info(model: str) -> dict[str, bool]:
        return {
            "supports_none_reasoning_effort": True,
            "supports_xhigh_reasoning_effort": True,
        }

    with (
        patch("litellm.get_model_info", fake_get_model_info),
        patch("litellm.supports_reasoning", return_value=True),
    ):
        ok, efforts, _default = litellm_reasoning("openai/gpt-5.4-mini")
    assert ok is True
    assert efforts == ("none", "low", "medium", "high", "xhigh")


def test_fill_gpt5_reasoning_gaps_ignores_non_gpt5() -> None:
    """Gap fill applies only to GPT-5 family models."""
    assert fill_gpt5_reasoning_gaps(("none", "medium"), "openai/gpt-4o") == ("none", "medium")


def test_litellm_reasoning_import_error() -> None:
    """Missing litellm module yields no reasoning."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "litellm":
            raise ImportError("no litellm")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    with patch("builtins.__import__", side_effect=fake_import):
        ok, efforts, default = litellm_reasoning("openai/gpt-4o")
    assert ok is False
    assert efforts == ()
    assert default == ""


def test_ollama_gpt_oss_levels() -> None:
    """gpt-oss gets low/medium/high without off."""
    data = cast("dict[str, object]", {"capabilities": ["completion", "tools", "thinking"]})
    ok, efforts, default = ollama_reasoning_from_show(data, "gpt-oss:latest")
    assert ok is True
    assert efforts == ("low", "medium", "high")
    assert default == "medium"
    assert "off" not in efforts


def test_ollama_qwen_thinking_not_reasoning() -> None:
    """Generic thinking models use thinking flags, not leveled reasoning."""
    data = cast("dict[str, object]", {"capabilities": ["completion", "tools", "thinking"]})
    thinking, think_default = ollama_thinking_from_show(data)
    assert thinking is True
    assert think_default == "on"
    ok, efforts, default = ollama_reasoning_from_show(data, "qwen3:latest")
    assert ok is False
    assert efforts == ()
    assert default == ""


def test_ollama_non_thinking() -> None:
    """Without thinking capability."""
    data = cast("dict[str, object]", {"capabilities": ["completion", "tools"]})
    ok, efforts, default = ollama_reasoning_from_show(data, "llama3")
    assert ok is False
    assert efforts == ()
    assert default == ""
