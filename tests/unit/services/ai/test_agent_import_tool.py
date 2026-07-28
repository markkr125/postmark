"""Tests for dedicated ``postmark_import`` OpenHands tool."""

from __future__ import annotations

from types import SimpleNamespace
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
from services.ai.chat.tools.workspace_import.turn_guard import clear_import_turn
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

    def test_collection_name_suffix_is_an_import_option(self) -> None:
        """Name suffix is accepted without counting as a second source."""
        action = WorkspaceImportAction(
            url="https://example.com/openapi.yaml",
            collection_name_suffix="10",
        )
        assert action.source_fields() == {"url": "https://example.com/openapi.yaml"}
        assert "append '10'" in action.human_preview()

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

    def test_import_observation_exposes_named_collection_links(self) -> None:
        """Observation provides ready-to-copy named links, never a raw URI label."""
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
        match = re.search(r"imported_collections: \[\{'id': (\d+),", obs.text)
        assert match is not None, obs.text
        collection_id = int(match.group(1))
        assert collection_id > 0
        # The advertised id must be the collection that was actually created.
        created = CollectionService.get_collection(collection_id)
        assert created is not None
        assert created.name == "PostmarkDeepLinkApi"
        assert (
            f"collection_links: ['[PostmarkDeepLinkApi](postmark://collection/{collection_id})']"
            in obs.text
        )
        assert f"[postmark://collection/{collection_id}]" not in obs.text
        assert "Do not import this source again in this turn" in obs.text

    def test_import_suffix_renames_root_without_second_import(self) -> None:
        """One import call can append a suffix to the created root name."""
        import json
        import re

        openapi = {
            "openapi": "3.0.0",
            "info": {"title": "Hotel Booking API"},
            "paths": {"/ping": {"get": {"summary": "Ping"}}},
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(openapi).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        with patch("urllib.request.urlopen", return_value=mock_resp):
            obs = WorkspaceImportExecutor()(
                WorkspaceImportAction(
                    url="https://example.com/hotel.yaml",
                    collection_name_suffix="10",
                ),
                None,
            )
        match = re.search(r"imported_collections: \[\{'id': (\d+),", obs.text)
        assert match is not None
        created = CollectionService.get_collection(int(match.group(1)))
        assert created is not None
        assert created.name == "Hotel Booking API 10"
        assert "[Hotel Booking API 10](postmark://collection/" in obs.text

    def test_duplicate_source_in_one_turn_reuses_first_result(self) -> None:
        """A repeated model call cannot import the same source twice in one turn."""
        import json

        session_id = "import-dedupe-session"
        clear_import_turn(session_id)
        conversation = SimpleNamespace(state=SimpleNamespace(id=session_id, persistence_dir=None))
        openapi = {
            "openapi": "3.0.0",
            "info": {"title": "One Import Only"},
            "paths": {"/ping": {"get": {"summary": "Ping"}}},
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(openapi).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        executor = WorkspaceImportExecutor()
        action = WorkspaceImportAction(url="https://example.com/once.yaml")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            first = executor(action, conversation)  # type: ignore[arg-type]
            after_first = CollectionService.count_all_collections()
            second = executor(action, conversation)  # type: ignore[arg-type]
        assert "duplicate_skipped: true" not in first.text
        assert "duplicate_skipped: true" in second.text
        assert after_first > 0
        assert CollectionService.count_all_collections() == after_first

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
