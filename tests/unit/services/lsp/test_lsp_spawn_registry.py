"""Unit tests for background LSP spawn and registry warm guards."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from services.lsp.server_registry import LspRegistry, reset_registry_for_tests
from services.lsp.servers.spawn import language_to_bucket


@pytest.fixture
def registry(qapp: QApplication) -> Generator[LspRegistry, None, None]:
    """Fresh registry instance per test."""
    reset_registry_for_tests()
    reg = LspRegistry.instance()
    yield reg
    reg.shutdown()
    reset_registry_for_tests()


def test_language_to_bucket_maps_js_family() -> None:
    """JS and TS share the Deno bucket."""
    assert language_to_bucket("javascript") == "js"
    assert language_to_bucket("typescript") == "js"
    assert language_to_bucket("python") == "python"
    assert language_to_bucket("json") is None


def test_warm_async_dedupes_in_flight_spawn(registry: LspRegistry) -> None:
    """Concurrent warm_async calls start only one worker per bucket."""
    started: list[str] = []

    class FakeWorker:
        def __init__(self, bucket: str, parent: object | None = None) -> None:
            started.append(bucket)

        finished_with = MagicMock()
        finished = MagicMock()

        def start(self) -> None:
            pass

    with patch("services.lsp.server_registry.LspSpawnWorker", FakeWorker):
        registry.warm_async("js")
        registry.warm_async("js")
    assert started == ["js"]
    assert "js" in registry._warming


def test_shutdown_stops_spawned_client(registry: LspRegistry) -> None:
    """Clients in ``_clients`` are stopped on registry shutdown even without editor attach."""
    mock_client = MagicMock()
    registry._clients["js"] = mock_client
    registry.shutdown()
    mock_client.stop.assert_called_once()
    assert registry._clients == {}
