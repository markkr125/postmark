# Service Layer

The service layer sits between the UI and the database.  UI widgets call
service methods; services call repository functions.  UI code must never
import from `database/` directly.

## Design Pattern

All services use the same pattern:

- **Class with `@staticmethod` methods** — no instance state, no `self`.
  The class exists only as a namespace.
- **Single import point** — `from services import CollectionService`.
- **TypedDict for cross-boundary data** — complex return values and
  interchange dicts are defined as TypedDicts in the service module.
- **Thin wrappers** — most methods delegate directly to a repository
  function.  Business logic (validation, aggregation) lives here when
  needed.

## Service Catalogue

| Service | Module | Purpose |
|---------|--------|---------|
| `CollectionService` | `collection_service.py` | Collection and request CRUD, auth chains, breadcrumbs, saved responses |
| `EnvironmentService` | `environment_service.py` | Environment CRUD, variable maps, `{{var}}` substitution |
| `ImportService` | `import_service.py` | Parse and persist imported files/text/URLs |
| `HttpService` | `http/http_service.py` | Execute HTTP requests via httpx, return structured response |
| `GraphQLSchemaService` | `http/graphql_schema_service.py` | GraphQL introspection and schema parsing |
| `SnippetGenerator` | `http/snippet_generator/generator.py` | Generate code snippets in 23 languages |
| `OAuth2Service` | `http/oauth2_service.py` | OAuth 2.0 token exchange (4 grant types) |

Additionally, `apply_auth()` in `http/auth_handler.py` is a standalone
function (not a class) that injects authentication headers for 12 auth
types.

## Re-export Modules

Two `__init__.py` files re-export the public API for convenience:

**`services/__init__.py`** re-exports:
- `CollectionService`, `EnvironmentService`, `ImportService`
- `RequestLoadDict`, `VariableDetail`, `LocalOverride`

**`services/http/__init__.py`** re-exports:
- `HttpService`, `GraphQLSchemaService`, `SnippetGenerator`
- `SnippetOptions`, `HttpResponseDict`, `OAuth2Service`,
  `OAuth2TokenResult`, `parse_header_dict`

## TypedDict Interchange

Services define TypedDicts for structured data that crosses module
boundaries.  This provides type safety without coupling layers to ORM
models.

Key TypedDicts by service:

| TypedDict | Owner | Purpose |
|-----------|-------|---------|
| `RequestLoadDict` | `collection_service` | Populate RequestEditor from DB data |
| `SavedResponseDict` | `collection_service` | Full saved response payload for sidebar |
| `VariableDetail` | `environment_service` | Variable metadata for popups (value, source, source_id) |
| `LocalOverride` | `environment_service` | Per-request variable override with original source |
| `HttpResponseDict` | `http_service` | Full HTTP response: status, headers, body, timing, network, sizes |
| `TimingDict` | `http_service` | DNS, TCP, TLS, TTFB, download, process timing breakdown |
| `NetworkDict` | `http_service` | HTTP version, addresses, TLS details, certificate info |
| `SnippetOptions` | `snippet_generator` | Indentation, timeout, style options for code generation |
| `OAuth2TokenResult` | `oauth2_service` | Token exchange result (access_token, type, expires, etc.) |
| `SchemaResultDict` | `graphql_schema_service` | Introspection result (types, root operations) |

See [TypedDict Catalogue](../api-reference/typedicts.md) for complete
field definitions.

## Import Parser Sub-system

The import pipeline has its own sub-package under `services/import_parser/`
with dedicated TypedDicts:

```text
ImportService.import_files(paths)
  --> detect_postman_type(data)       -- route to correct parser
  --> parse_collection_file(path)     -- or parse_environment_file, etc.
  --> import_collection_tree(parsed)  -- persist via import_repository
  <-- ImportSummary
```

Parser TypedDicts: `ParsedCollection`, `ParsedFolder`, `ParsedRequest`,
`ParsedSavedResponse`, `ParsedEnvironment`, `ImportResult`,
`ImportSummary`.

See [Import Parsers](../api-reference/services/import-parsers.md) for
details.
