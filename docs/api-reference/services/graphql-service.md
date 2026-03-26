# GraphQLSchemaService

GraphQL introspection and schema parsing.  All methods are
`@staticmethod`.

Source: `src/services/http/graphql_schema_service.py`

## Methods

### `fetch_schema`

```python
@staticmethod
def fetch_schema(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = _INTROSPECTION_TIMEOUT,
) -> SchemaResultDict
```

Send a GraphQL introspection query to the given URL and parse the
response into a structured schema result.

**Parameters:**
- `url` — GraphQL endpoint URL.
- `headers` — optional headers to include (e.g. auth tokens).
- `timeout` — request timeout in seconds.

**Returns:** `SchemaResultDict` containing root type names, type list,
and raw introspection response.

### `format_schema_summary`

```python
@staticmethod
def format_schema_summary(result: SchemaResultDict) -> str
```

Format a `SchemaResultDict` into a human-readable text summary showing
root types and available types.

## TypedDicts

### `SchemaTypeDict`

```python
class SchemaTypeDict(TypedDict):
    name: str           # Type name (e.g. "Query", "User")
    kind: str           # GraphQL kind (OBJECT, SCALAR, ENUM, etc.)
    description: str    # Type description from schema
```

### `SchemaResultDict`

```python
class SchemaResultDict(TypedDict):
    query_type: str          # Root query type name
    mutation_type: str       # Root mutation type name
    subscription_type: str   # Root subscription type name
    types: list[SchemaTypeDict]  # All types in the schema
    raw: dict                # Raw introspection response
```
