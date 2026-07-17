"""Tests for dedicated ``postmark_import`` OpenHands tool."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from services.ai.chat.mutation.auto_approve import (
    CATALOG,
    is_mutate_or_execute_tool,
    kind_from_action_event,
    kind_from_tool_args,
)
from services.ai.chat.mutation.bridge import clear_mutation_events, drain_mutation_events
from services.ai.chat.tools.workspace_import.tool import (
    IMPORT_TOOL_NAME,
    WorkspaceImportAction,
    WorkspaceImportExecutor,
)
from services.collection_service import CollectionService


@pytest.fixture(autouse=True)
def _clear_bridge() -> Any:
    """Clear mutation bridge around each test."""
    clear_mutation_events()
    yield
    clear_mutation_events()


class TestWorkspaceImportAction:
    """Action schema requires exactly one source."""

    def test_url_only(self) -> None:
        """URL source is accepted."""
        action = WorkspaceImportAction(url="https://example.com/openapi.yaml")
        assert action.source_fields() == {"url": "https://example.com/openapi.yaml"}
        assert "openapi.yaml" in action.human_preview()

    def test_rejects_multiple_sources(self) -> None:
        """Two sources raise ValidationError."""
        with pytest.raises(ValidationError):
            WorkspaceImportAction(url="https://x", path="/tmp/a.yaml")

    def test_rejects_empty(self) -> None:
        """No source raises ValidationError."""
        with pytest.raises(ValidationError):
            WorkspaceImportAction()


class TestWorkspaceImportKind:
    """Approve / auto-approve kind mapping."""

    def test_kind_from_tool_name(self) -> None:
        """postmark_import maps to mutate:create:import."""
        assert "mutate:create:import" in CATALOG
        assert kind_from_tool_args(IMPORT_TOOL_NAME) == "mutate:create:import"
        assert is_mutate_or_execute_tool(IMPORT_TOOL_NAME)

    def test_kind_from_action_event(self) -> None:
        """ActionEvent with import action maps to Import workspace kind."""
        from types import SimpleNamespace

        action = WorkspaceImportAction(url="https://example.com/spec.yaml")
        event = SimpleNamespace(tool_name=IMPORT_TOOL_NAME, action=action)
        assert kind_from_action_event(event) == "mutate:create:import"


class TestWorkspaceImportExecutor:
    """Executor calls ImportService and enqueues UI refresh."""

    def test_import_openapi_url(self) -> None:
        """URL source fetches OpenAPI and persists a collection."""
        import json

        openapi = {
            "openapi": "3.0.0",
            "info": {"title": "PostmarkImportTool"},
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/ping": {"get": {"summary": "Ping", "tags": ["health"]}},
            },
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(openapi).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        with patch("urllib.request.urlopen", return_value=mock_resp):
            obs = WorkspaceImportExecutor()(
                WorkspaceImportAction(url="https://example.com/openapi.json"),
                None,
            )
        assert "ok: true" in obs.text
        assert "collections_imported:" in obs.text
        assert "requests_imported: 1" in obs.text
        events = drain_mutation_events()
        mutated = next(e for e in events if e.get("type") == "mutated")
        assert mutated["entity"] == "import"
        assert CollectionService.count_all_collections() >= 1

    def test_import_observation_exposes_collection_deep_links(self) -> None:
        """Observation carries real postmark://collection/<id> links to link in chat."""
        import json
        import re

        openapi = {
            "openapi": "3.0.0",
            "info": {"title": "PostmarkDeepLinkApi"},
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/ping": {"get": {"summary": "Ping", "tags": ["health"]}},
            },
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(openapi).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        with patch("urllib.request.urlopen", return_value=mock_resp):
            obs = WorkspaceImportExecutor()(
                WorkspaceImportAction(url="https://example.com/openapi.json"),
                None,
            )
        assert "ok: true" in obs.text
        assert "PostmarkDeepLinkApi" in obs.text
        match = re.search(r"deep_links: \['postmark://collection/(\d+)'", obs.text)
        assert match is not None, obs.text
        collection_id = int(match.group(1))
        assert collection_id > 0
        # The advertised id must be the collection that was actually created.
        created = CollectionService.get_collection(collection_id)
        assert created is not None
        assert created.name == "PostmarkDeepLinkApi"

    def test_import_curl(self) -> None:
        """Curl source imports via ImportService."""
        obs = WorkspaceImportExecutor()(
            WorkspaceImportAction(curl="curl https://example.com/agent-import"),
            None,
        )
        assert "ok: true" in obs.text
        assert "collections_imported:" in obs.text
        events = drain_mutation_events()
        mutated = next(e for e in events if e.get("type") == "mutated")
        assert mutated["entity"] == "import"

    def test_import_url_dispatches(self, monkeypatch: Any) -> None:
        """URL source reaches ImportService.import_url."""
        calls: list[str] = []

        def _fake_url(url: str) -> dict[str, object]:
            calls.append(url)
            return {
                "collections_imported": 0,
                "requests_imported": 0,
                "environments_imported": 0,
                "errors": [],
            }

        monkeypatch.setattr(
            "services.import_service.ImportService.import_url",
            staticmethod(_fake_url),
        )
        obs = WorkspaceImportExecutor()(
            WorkspaceImportAction(url="https://example.com/openapi.yaml"),
            None,
        )
        assert calls == ["https://example.com/openapi.yaml"]
        assert "ok: true" in obs.text
