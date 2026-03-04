"""Tests for the GraphQL schema introspection service."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.graphql_schema_service import (
    INTROSPECTION_QUERY,
    GraphQLSchemaService,
    SchemaResultDict,
    SchemaTypeDict,
)

# -- Helpers ---------------------------------------------------------------


def _make_introspection_response(
    *,
    types: list[dict] | None = None,
    query_type: str = "Query",
    mutation_type: str | None = "Mutation",
    subscription_type: str | None = None,
    errors: list[dict] | None = None,
) -> dict:
    """Build a mock introspection response payload."""
    if types is None:
        types = [
            {"kind": "OBJECT", "name": "Query", "description": "Root query"},
            {"kind": "OBJECT", "name": "User", "description": "A user"},
            {"kind": "OBJECT", "name": "Mutation", "description": None},
            {"kind": "SCALAR", "name": "String", "description": "Built-in string"},
            {"kind": "OBJECT", "name": "__Schema", "description": "Introspection"},
            {"kind": "ENUM", "name": "Role", "description": "User role"},
        ]

    schema_data: dict = {
        "queryType": {"name": query_type},
        "mutationType": {"name": mutation_type} if mutation_type else None,
        "subscriptionType": {"name": subscription_type} if subscription_type else None,
        "types": types,
    }
    result: dict = {"data": {"__schema": schema_data}}
    if errors:
        result["errors"] = errors
    return result


def _mock_httpx_post(response_json: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Client that returns *response_json* from POST."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = response_json
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response
    return mock_client


# -- Tests -----------------------------------------------------------------


class TestFetchSchema:
    """Tests for GraphQLSchemaService.fetch_schema."""

    @patch("services.graphql_schema_service.httpx.Client")
    def test_successful_introspection(self, mock_client_cls: MagicMock) -> None:
        """A valid introspection response is parsed into a SchemaResultDict."""
        payload = _make_introspection_response()
        mock_client_cls.return_value = _mock_httpx_post(payload)

        result = GraphQLSchemaService.fetch_schema("https://api.example.com/graphql")

        assert result["query_type"] == "Query"
        assert result["mutation_type"] == "Mutation"
        assert result["subscription_type"] == ""
        # Built-in __Schema type should be filtered out.
        names = [t["name"] for t in result["types"]]
        assert "__Schema" not in names
        assert "User" in names
        assert "Query" in names
        assert "Role" in names

    @patch("services.graphql_schema_service.httpx.Client")
    def test_custom_headers_forwarded(self, mock_client_cls: MagicMock) -> None:
        """Custom headers are merged with Content-Type and sent."""
        payload = _make_introspection_response()
        mock_client = _mock_httpx_post(payload)
        mock_client_cls.return_value = mock_client

        GraphQLSchemaService.fetch_schema(
            "https://api.example.com/graphql",
            headers={"Authorization": "Bearer tok123"},
        )

        call_kwargs = mock_client.post.call_args
        sent_headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert sent_headers["Content-Type"] == "application/json"
        assert sent_headers["Authorization"] == "Bearer tok123"

    @patch("services.graphql_schema_service.httpx.Client")
    def test_sends_introspection_query(self, mock_client_cls: MagicMock) -> None:
        """The POST body contains the standard introspection query."""
        payload = _make_introspection_response()
        mock_client = _mock_httpx_post(payload)
        mock_client_cls.return_value = mock_client

        GraphQLSchemaService.fetch_schema("https://api.example.com/graphql")

        call_kwargs = mock_client.post.call_args
        sent_content = call_kwargs.kwargs.get("content") or call_kwargs[1].get("content")
        body = json.loads(sent_content)
        assert body["query"] == INTROSPECTION_QUERY

    @patch("services.graphql_schema_service.httpx.Client")
    def test_graphql_errors_without_data_raises(self, mock_client_cls: MagicMock) -> None:
        """A response with only errors raises ValueError."""
        error_payload = {"errors": [{"message": "Introspection disabled"}]}
        mock_client_cls.return_value = _mock_httpx_post(error_payload)

        with pytest.raises(ValueError, match="Introspection disabled"):
            GraphQLSchemaService.fetch_schema("https://api.example.com/graphql")

    @patch("services.graphql_schema_service.httpx.Client")
    def test_missing_schema_data_raises(self, mock_client_cls: MagicMock) -> None:
        """A response without __schema raises ValueError."""
        mock_client_cls.return_value = _mock_httpx_post({"data": {}})

        with pytest.raises(ValueError, match="__schema"):
            GraphQLSchemaService.fetch_schema("https://api.example.com/graphql")

    @patch("services.graphql_schema_service.httpx.Client")
    def test_http_error_propagates(self, mock_client_cls: MagicMock) -> None:
        """An HTTP error from the server propagates as httpx.HTTPStatusError."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=MagicMock(),
        )

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            GraphQLSchemaService.fetch_schema("https://api.example.com/graphql")

    @patch("services.graphql_schema_service.httpx.Client")
    def test_no_mutation_type(self, mock_client_cls: MagicMock) -> None:
        """Schema without mutation/subscription returns empty strings."""
        payload = _make_introspection_response(
            mutation_type=None,
            subscription_type=None,
        )
        mock_client_cls.return_value = _mock_httpx_post(payload)

        result = GraphQLSchemaService.fetch_schema("https://api.example.com/graphql")

        assert result["mutation_type"] == ""
        assert result["subscription_type"] == ""


class TestParseSchema:
    """Tests for the internal _parse_schema method."""

    def test_filters_introspection_types(self) -> None:
        """Types prefixed with __ are excluded."""
        schema_data = {
            "queryType": {"name": "Query"},
            "mutationType": None,
            "subscriptionType": None,
            "types": [
                {"kind": "OBJECT", "name": "Query", "description": ""},
                {"kind": "OBJECT", "name": "__Schema", "description": ""},
                {"kind": "OBJECT", "name": "__Type", "description": ""},
            ],
        }

        result = GraphQLSchemaService._parse_schema(schema_data, raw={})

        names = [t["name"] for t in result["types"]]
        assert names == ["Query"]

    def test_sorts_by_kind_then_name(self) -> None:
        """Types are sorted alphabetically by kind, then by name."""
        schema_data = {
            "queryType": {"name": "Query"},
            "mutationType": None,
            "subscriptionType": None,
            "types": [
                {"kind": "SCALAR", "name": "Int", "description": ""},
                {"kind": "OBJECT", "name": "User", "description": ""},
                {"kind": "ENUM", "name": "Role", "description": ""},
                {"kind": "OBJECT", "name": "Post", "description": ""},
                {"kind": "ENUM", "name": "Status", "description": ""},
            ],
        }

        result = GraphQLSchemaService._parse_schema(schema_data, raw={})

        kinds_and_names = [(t["kind"], t["name"]) for t in result["types"]]
        assert kinds_and_names == [
            ("ENUM", "Role"),
            ("ENUM", "Status"),
            ("OBJECT", "Post"),
            ("OBJECT", "User"),
            ("SCALAR", "Int"),
        ]

    def test_null_description_becomes_empty_string(self) -> None:
        """A null description is normalised to an empty string."""
        schema_data = {
            "queryType": {"name": "Query"},
            "mutationType": None,
            "subscriptionType": None,
            "types": [
                {"kind": "OBJECT", "name": "Query", "description": None},
            ],
        }

        result = GraphQLSchemaService._parse_schema(schema_data, raw={})

        assert result["types"][0]["description"] == ""

    def test_raw_preserved(self) -> None:
        """The raw payload is stored unmodified."""
        raw: dict[str, dict] = {"data": {"__schema": {}}}
        result = GraphQLSchemaService._parse_schema(
            {"queryType": None, "mutationType": None, "subscriptionType": None, "types": []},
            raw=raw,
        )

        assert result["raw"] is raw


class TestFormatSchemaSummary:
    """Tests for the human-readable schema summary formatter."""

    def test_includes_root_types(self) -> None:
        """The summary lists query, mutation, and subscription root types."""
        result = SchemaResultDict(
            query_type="Query",
            mutation_type="Mutation",
            subscription_type="",
            types=[],
            raw={},
        )

        summary = GraphQLSchemaService.format_schema_summary(result)

        assert "Query: Query" in summary
        assert "Mutation: Mutation" in summary
        assert "Subscription" not in summary

    def test_groups_by_kind(self) -> None:
        """Types are grouped under their kind heading."""
        result = SchemaResultDict(
            query_type="Query",
            mutation_type="",
            subscription_type="",
            types=[
                SchemaTypeDict(name="User", kind="OBJECT", description=""),
                SchemaTypeDict(name="Post", kind="OBJECT", description=""),
                SchemaTypeDict(name="Role", kind="ENUM", description=""),
            ],
            raw={},
        )

        summary = GraphQLSchemaService.format_schema_summary(result)

        assert "OBJECT (2):" in summary
        assert "  User" in summary
        assert "  Post" in summary
        assert "ENUM (1):" in summary
        assert "  Role" in summary

    def test_empty_schema(self) -> None:
        """An empty schema produces an empty summary string."""
        result = SchemaResultDict(
            query_type="",
            mutation_type="",
            subscription_type="",
            types=[],
            raw={},
        )

        summary = GraphQLSchemaService.format_schema_summary(result)

        assert summary == ""
