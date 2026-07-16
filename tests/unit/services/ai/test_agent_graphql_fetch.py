"""Tests for GraphQL schema fetch execute op."""

from __future__ import annotations

from unittest.mock import patch

from services.ai.chat.execution.graphql.fetch import run_fetch_graphql_schema
from services.collection_service import CollectionService


class TestFetchGraphqlSchema:
    """Agent GraphQL introspection with truncation."""

    def test_fetch_by_request_id(self) -> None:
        """Successful fetch returns schema_summary without raw dump."""
        col = CollectionService.create_collection("GQL")
        req = CollectionService.create_request(
            int(col.id),
            "POST",
            "https://api.example.com/graphql",
            "Query",
        )
        fake: dict[str, object] = {
            "query_type": "Query",
            "mutation_type": None,
            "subscription_type": None,
            "types": [{"name": "User", "kind": "OBJECT", "description": "a user"}],
            "raw": {"data": {"__schema": {}}},
        }
        with patch(
            "services.http.graphql_schema_service.GraphQLSchemaService.fetch_schema",
            return_value=fake,
        ):
            result = run_fetch_graphql_schema(request_id=int(req.id))
        assert result["ok"] is True
        assert "schema_summary" in result
        assert "User" in result["schema_summary"]
        assert "raw" not in (result.get("schema") or {})
