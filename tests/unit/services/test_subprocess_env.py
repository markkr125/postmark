"""Tests for the minimal sandbox subprocess environment (F7 — secret leakage)."""

from __future__ import annotations

import pytest

from services.scripting._subprocess_env import safe_subprocess_env


def test_excludes_host_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Secrets in the parent environment are NOT forwarded to subprocesses."""
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "shhh")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_xxx")
    monkeypatch.setenv("MY_API_KEY", "secret")
    env = safe_subprocess_env()
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    assert "MY_API_KEY" not in env


def test_forwards_operational_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Operational vars the toolchain needs are forwarded."""
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("HOME", "/home/tester")
    env = safe_subprocess_env()
    assert env.get("PATH") == "/usr/bin:/bin"
    assert env.get("HOME") == "/home/tester"


def test_extra_vars_merged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime-specific extras (DENO_DIR, …) are merged on top."""
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "shhh")
    env = safe_subprocess_env({"DENO_DIR": "/tmp/deno", "PM_PYODIDE_CACHE": "/tmp/pyo"})
    assert env["DENO_DIR"] == "/tmp/deno"
    assert env["PM_PYODIDE_CACHE"] == "/tmp/pyo"
    assert "AWS_SECRET_ACCESS_KEY" not in env
