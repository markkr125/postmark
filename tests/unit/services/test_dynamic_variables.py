"""Tests for ``services.scripting.dynamic_variables`` and send-time substitution."""

from __future__ import annotations

import re

from services.environment_service import EnvironmentService
from services.scripting.dynamic_variables import resolve


def test_resolve_guid_is_uuid() -> None:
    """``$guid`` resolves to a UUID v4 string."""
    val = resolve("$guid")
    assert val is not None
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        val,
    )


def test_resolve_unknown_returns_none() -> None:
    """Unknown ``$`` names return ``None``."""
    assert resolve("$not_a_postman_var") is None


def test_substitute_dynamic_vars_empty_map() -> None:
    """``substitute`` resolves ``$`` keys even when the variable map is empty."""
    text = "a/{{$guid}}?n={{$randomInt}}"
    out = EnvironmentService.substitute(text, {})
    assert out.startswith("a/")
    assert "?n=" in out
    assert "{{" not in out
