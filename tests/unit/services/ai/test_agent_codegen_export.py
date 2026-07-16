"""Tests for generate_snippet and export_workspace_artifact execute ops."""

from __future__ import annotations

from services.ai.chat.execution.codegen.snippet import run_generate_snippet
from services.ai.chat.execution.export.artifact import run_export_workspace_artifact
from services.collection_service import CollectionService
from services.run_export import export_run_results_csv


class TestGenerateSnippet:
    """Codegen keeps auth secrets as placeholders."""

    def test_bearer_uses_placeholder(self) -> None:
        """Resolved bearer tokens must not appear in the snippet."""
        col = CollectionService.create_collection("Snip")
        req = CollectionService.create_request(
            int(col.id),
            "GET",
            "https://api.example.com/me",
            "Me",
        )
        CollectionService.update_request(
            int(req.id),
            auth={
                "type": "bearer",
                "bearer": [{"key": "token", "value": "SECRET_TOKEN_XYZ", "type": "string"}],
            },
        )
        result = run_generate_snippet(request_id=int(req.id), language="cURL")
        assert result["ok"] is True
        snippet = str(result.get("snippet") or "")
        assert "SECRET_TOKEN_XYZ" not in snippet
        # Scrubbed auth injects placeholder token into Authorization.
        assert "{{token}}" in snippet or "Authorization" in snippet


class TestExportArtifact:
    """Export serializers."""

    def test_run_csv_helper(self) -> None:
        """CSV export includes status column."""
        csv_text = export_run_results_csv(
            [
                {
                    "name": "A",
                    "method": "GET",
                    "status_code": 200,
                    "elapsed_ms": 12,
                    "test_results": [{"passed": True}],
                }
            ]
        )
        assert "Name" in csv_text
        assert "200" in csv_text

    def test_export_missing_history(self) -> None:
        """Missing history entry returns a structured error."""
        result = run_export_workspace_artifact(
            kind="test_results_json",
            history_entry_id=99999999,
        )
        assert result["ok"] is False
        assert result["error"] == "history_not_found"
