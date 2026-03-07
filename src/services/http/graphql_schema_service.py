"""GraphQL schema introspection service.

Sends the standard GraphQL introspection query to an endpoint and parses
the response into a structured schema summary.  All methods are
``@staticmethod`` — no instance state.
"""

from __future__ import annotations

import json
import logging
from typing import TypedDict

import httpx

logger = logging.getLogger(__name__)

# Timeout for introspection requests (seconds).
_INTROSPECTION_TIMEOUT = 15.0

# Standard introspection query — fetches all types, their fields and args.
INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      kind
      name
      description
      fields(includeDeprecated: true) {
        name
        description
        args {
          name
          description
          type {
            ...TypeRef
          }
          defaultValue
        }
        type {
          ...TypeRef
        }
        isDeprecated
        deprecationReason
      }
      inputFields {
        name
        description
        type {
          ...TypeRef
        }
        defaultValue
      }
      interfaces {
        ...TypeRef
      }
      enumValues(includeDeprecated: true) {
        name
        description
        isDeprecated
        deprecationReason
      }
      possibleTypes {
        ...TypeRef
      }
    }
  }
}

fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
        ofType {
          kind
          name
        }
      }
    }
  }
}
""".strip()


class SchemaTypeDict(TypedDict):
    """Summary of a single GraphQL type for display."""

    name: str
    kind: str
    description: str


class SchemaResultDict(TypedDict):
    """Parsed introspection result returned to the UI."""

    query_type: str
    mutation_type: str
    subscription_type: str
    types: list[SchemaTypeDict]
    raw: dict


class GraphQLSchemaService:
    """Fetch and parse GraphQL schemas via introspection.

    Every method is a ``@staticmethod`` — no shared state.
    """

    @staticmethod
    def fetch_schema(
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = _INTROSPECTION_TIMEOUT,
    ) -> SchemaResultDict:
        """Send an introspection query to *url* and return parsed schema.

        Args:
            url: The GraphQL endpoint URL.
            headers: Optional HTTP headers to include (e.g. auth tokens).
            timeout: Request timeout in seconds.

        Returns:
            A :class:`SchemaResultDict` with the parsed schema summary.

        Raises:
            ValueError: If the response does not contain valid schema data.
            httpx.HTTPError: On network failures.
        """
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)

        payload = json.dumps({"query": INTROSPECTION_QUERY})

        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.post(
                url,
                content=payload.encode("utf-8"),
                headers=request_headers,
            )
            response.raise_for_status()

        body = response.json()

        # GraphQL errors returned inside a 200 response.
        if "errors" in body and "data" not in body:
            messages = [e.get("message", "Unknown error") for e in body["errors"]]
            raise ValueError(f"GraphQL errors: {'; '.join(messages)}")

        schema_data = (body.get("data") or {}).get("__schema")
        if not schema_data:
            raise ValueError("Response does not contain __schema data")

        return GraphQLSchemaService._parse_schema(schema_data, raw=body)

    @staticmethod
    def _parse_schema(schema_data: dict, *, raw: dict) -> SchemaResultDict:
        """Extract a structured summary from raw ``__schema`` data."""
        query_type = (schema_data.get("queryType") or {}).get("name", "")
        mutation_type = (schema_data.get("mutationType") or {}).get("name", "")
        subscription_type = (schema_data.get("subscriptionType") or {}).get("name", "")

        types: list[SchemaTypeDict] = []
        for t in schema_data.get("types", []):
            name = t.get("name", "")
            # Skip built-in introspection types (prefixed with __).
            if name.startswith("__"):
                continue
            types.append(
                SchemaTypeDict(
                    name=name,
                    kind=t.get("kind", ""),
                    description=t.get("description") or "",
                )
            )

        # Sort by kind then name for consistent display.
        types.sort(key=lambda t: (t["kind"], t["name"]))

        return SchemaResultDict(
            query_type=query_type,
            mutation_type=mutation_type,
            subscription_type=subscription_type,
            types=types,
            raw=raw,
        )

    @staticmethod
    def format_schema_summary(result: SchemaResultDict) -> str:
        """Build a human-readable summary of the schema.

        Returns a multi-line string listing root types and user-defined
        types grouped by kind.
        """
        lines: list[str] = []

        if result["query_type"]:
            lines.append(f"Query: {result['query_type']}")
        if result["mutation_type"]:
            lines.append(f"Mutation: {result['mutation_type']}")
        if result["subscription_type"]:
            lines.append(f"Subscription: {result['subscription_type']}")

        if lines:
            lines.append("")

        # Group by kind.
        by_kind: dict[str, list[str]] = {}
        for t in result["types"]:
            by_kind.setdefault(t["kind"], []).append(t["name"])

        for kind in ("OBJECT", "INPUT_OBJECT", "ENUM", "INTERFACE", "UNION", "SCALAR"):
            names = by_kind.get(kind, [])
            if names:
                lines.append(f"{kind} ({len(names)}):")
                for n in names:
                    lines.append(f"  {n}")
                lines.append("")

        return "\n".join(lines).rstrip()
