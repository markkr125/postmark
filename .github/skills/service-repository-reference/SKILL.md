---
name: service-repository-reference
description: Complete catalogue of all repository functions, service methods, and TypedDict schemas in the Postmark codebase. Use when adding new service methods, repository functions, TypedDicts, or when you need to know what API exists in the service or database layer.
---

# Service and repository reference

Complete catalogue of every public function in the repository layer and
every method in the service layer, plus all TypedDict schemas used for
cross-layer data interchange.

## Repository function catalogue

### Collection repository — CRUD (`collection_repository.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `create_new_collection(name, parent_id?)` | `CollectionModel` | Create a folder |
| `rename_collection(collection_id, new_name)` | `None` | Update name |
| `delete_collection(collection_id)` | `None` | Delete + cascade children and requests |
| `create_new_request(collection_id, method, url, name, ...)` | `RequestModel` | Create a request |
| `rename_request(request_id, new_name)` | `None` | Update name |
| `delete_request(request_id)` | `None` | Delete a single request |
| `update_request_collection(request_id, new_collection_id)` | `None` | Move request |
| `update_collection_parent(collection_id, new_parent_id)` | `None` | Move collection |
| `save_response(request_id, ...)` | `int` | Persist a response snapshot, return its ID |
| `rename_saved_response(response_id, new_name)` | `None` | Rename a saved response |
| `delete_saved_response(response_id)` | `None` | Delete a saved response |
| `duplicate_saved_response(response_id)` | `int` | Copy a saved response, return new ID |
| `update_collection(collection_id, **fields)` | `None` | Generic field update on a collection |
| `update_request(request_id, **fields)` | `None` | Generic field update on a request |

### Collection query repository (`collection_query_repository.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `fetch_all_collections()` | `dict[str, Any]` | All root collections as nested dict |
| `get_collection_by_id(collection_id)` | `CollectionModel \| None` | PK lookup |
| `get_request_by_id(request_id)` | `RequestModel \| None` | PK lookup |
| `get_request_auth_chain(request_id)` | `dict[str, Any] \| None` | Walk parent chain for auth config |
| `get_request_inherited_auth(request_id)` | `dict[str, Any] \| None` | Resolve inherited auth for a request (walks ancestors) |
| `get_collection_inherited_auth(collection_id)` | `dict[str, Any] \| None` | Resolve inherited auth for a collection (walks ancestors) |
| `get_request_variable_chain(request_id)` | `dict[str, str]` | Collect variables up the parent chain |
| `get_request_variable_chain_detailed(request_id)` | `dict[str, tuple[str, int]]` | Variables with source collection IDs |
| `get_collection_variable_chain_detailed(collection_id)` | `dict[str, tuple[str, int]]` | Variables from collection's parent chain with source IDs |
| `get_request_breadcrumb(request_id)` | `list[dict[str, Any]]` | Ancestor path for breadcrumb bar |
| `get_collection_breadcrumb(collection_id)` | `list[dict[str, Any]]` | Ancestor path for collection breadcrumb |
| `get_saved_responses_for_request(request_id)` | `list[dict[str, Any]]` | Saved responses for a request |
| `get_saved_response(response_id)` | `dict[str, Any] \| None` | Single saved response detail by ID |
| `count_collection_requests(collection_id)` | `int` | Total request count in folder subtree |
| `get_recent_requests_for_collection(collection_id, ...)` | `list[dict[str, Any]]` | Recently modified requests in subtree |

### Import repository (`import_repository.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `import_collection_tree(parsed)` | `dict[str, int]` | Atomic bulk-import of a full collection tree |

### Environment repository (`environment_repository.py`)

| Function | Returns | Purpose |
|----------|---------|----------|
| `fetch_all_environments()` | `list[dict[str, Any]]` | All environments as dicts |
| `create_environment(name, values?)` | `EnvironmentModel` | Create an environment |
| `get_environment_by_id(id)` | `EnvironmentModel \| None` | PK lookup |
| `rename_environment(id, new_name)` | `None` | Update name |
| `delete_environment(id)` | `None` | Delete environment |
| `update_environment_values(id, values)` | `None` | Replace key-value pairs |

## Service method catalogue

### CollectionService

All methods are `@staticmethod`.  "Passthrough" means the method delegates
directly to the repository with no added logic.

| Method | Validation added over repository |
|--------|----------------------------------|
| `fetch_all()` | Logging only |
| `get_collection(id)` | Passthrough |
| `get_request(id)` | Passthrough |
| `create_collection(name, parent_id?)` | `name.strip()`, rejects empty |
| `rename_collection(id, new_name)` | `new_name.strip()`, rejects empty |
| `delete_collection(id)` | Logging only |
| `move_collection(id, new_parent_id)` | Rejects `id == new_parent_id` (no deeper cycle check) |
| `create_request(collection_id, method, url, name, ...)` | `name.strip()`, `method.upper()`, rejects empty |
| `rename_request(id, new_name)` | `new_name.strip()`, rejects empty |
| `delete_request(id)` | Logging only |
| `move_request(id, new_collection_id)` | Passthrough |
| `update_collection(id, **fields)` | Passthrough (generic field update) |
| `update_request(id, **fields)` | Passthrough (generic field update) |
| `get_request_auth_chain(request_id)` | Passthrough |
| `get_request_inherited_auth(request_id)` | Passthrough |
| `get_collection_inherited_auth(collection_id)` | Passthrough |
| `get_request_variable_chain(request_id)` | Passthrough |
| `get_request_breadcrumb(request_id)` | Passthrough |
| `get_collection_breadcrumb(collection_id)` | Passthrough |
| `get_folder_request_count(collection_id)` | Passthrough |
| `get_recent_requests(collection_id, ...)` | Passthrough |
| `get_saved_responses(request_id)` | Formats `created_at` and `body_size` into `SavedResponseDict` |
| `get_saved_response(response_id)` | Formats one row into `SavedResponseDict` |
| `save_response(request_id, ...)` | Passthrough |
| `rename_saved_response(response_id, new_name)` | `new_name.strip()`, rejects empty |
| `delete_saved_response(response_id)` | Logging only |
| `duplicate_saved_response(response_id)` | Logging only |

### SavedResponseDict (`services/collection_service.py`)

```python
class SavedResponseDict(TypedDict):
    id: int
    request_id: int
    name: str
    status: str | None
    code: int | None
    headers: list[dict[str, Any]] | None
    body: str | None
    preview_language: str | None
    original_request: dict[str, Any] | None
    created_at: str | None
    body_size: int
```

### ImportService

All methods are `@staticmethod`.  Each parses the input, then persists via
`import_collection_tree()` and `create_environment()`.  Returns an
`ImportSummary` TypedDict with counts and errors.

| Method | Input |
|--------|-------|
| `import_files(paths)` | List of JSON files (auto-detect collection vs environment) |
| `import_folder(path)` | Postman archive folder or directory of JSON files |
| `import_text(text)` | Raw text — auto-detects cURL, JSON, or URL |
| `import_curl(text)` | One or more cURL commands |
| `import_url(url)` | Fetch URL contents and parse |

### HttpService

All methods are `@staticmethod`.  `send_request()` uses `httpx` with event
hooks to capture timing, and inspects the connection for TLS/network data.

| Method | Purpose |
|--------|---------|
| `send_request(method, url, headers, body, timeout)` | Execute HTTP request, return `HttpResponseDict` |

### EnvironmentService

All methods are `@staticmethod`.  Wraps the environment repository and adds
variable substitution via `{{variable}}` syntax.

| Method | Purpose |
|--------|---------|
| `fetch_all()` | All environments as list of dicts |
| `get_environment(id)` | PK lookup |
| `create_environment(name, values?)` | Create with optional initial values |
| `rename_environment(id, new_name)` | Update name |
| `delete_environment(id)` | Delete environment |
| `update_environment_values(id, values)` | Replace key-value pairs |
| `build_variable_map(environment_id)` | Build `{name: value}` dict for substitution |
| `build_combined_variable_map(env_id, request_id)` | Merged collection + environment `{name: value}` map |
| `build_combined_variable_detail_map(env_id, request_id)` | Merged map with `VariableDetail` metadata per key |
| `update_variable_value(source, source_id, key, new_value)` | Update a single variable at its collection/environment source |
| `add_variable(source, source_id, key, value)` | Add (or update) a variable to a collection or environment |
| `substitute(text, variables)` | Replace `{{key}}` placeholders in text |

### GraphQLSchemaService

All methods are `@staticmethod`.

| Method | Purpose |
|--------|---------|
| `fetch_schema(url, headers)` | Introspect endpoint, return `SchemaResultDict` |
| `_parse_schema(schema_data)` | Convert raw introspection JSON to structured types |
| `format_schema_summary(result)` | Human-readable schema summary text |

### SnippetGenerator

Located in `services/http/snippet_generator/` sub-package (re-exported via
`services/http/__init__.py`).  All methods are `@staticmethod`.

| Method | Purpose |
|--------|---------|
| `available_languages()` | List of 23 supported language display names |
| `get_language_info(name)` | Return `LanguageEntry` for a display name, or `None` |
| `generate(language, method, url, headers, body, auth, options)` | Dispatch to language-specific generator |

**`LanguageEntry`** (`NamedTuple`): `display_name`, `lexer`, `applicable_options`, `generate_fn`.

**Supported languages (23):** cURL, HTTP, PowerShell (RestMethod),
Shell (HTTPie), Shell (wget), Python (requests), Python (http.client),
JavaScript (fetch), JavaScript (XHR), NodeJS (Axios), NodeJS (Native),
Ruby (Net::HTTP), PHP (cURL), PHP (Guzzle), Dart (http), C (libcurl),
C# (HttpClient), C# (RestSharp), Go (net/http), Java (OkHttp),
Kotlin (OkHttp), Rust (reqwest), Swift (URLSession).

### Shared HTTP utilities (`services/http/header_utils.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `parse_header_dict(raw)` | `dict[str, str]` | Parse `Key: Value\n` lines into a dict |

### Auth handler (`services/http/auth_handler.py`)

Shared auth header injection used by both `http_worker.py` (actual send)
and `snippet_generator/generator.py` (code snippets).

| Function | Returns | Purpose |
|----------|---------|---------|
| `apply_auth(auth, url, headers, *, method, body)` | `(url, headers)` | Dispatch to type-specific handler |

Supports 12 field-based auth types: bearer, basic, apikey, oauth2, digest,
oauth1, hawk, awsv4, jwt, asap, ntlm, edgegrid.  HMAC-based JWT (HS256/384/512)
uses stdlib; RSA/EC algorithms require optional `PyJWT`.  NTLM is pass-through
(requires live challenge-response).

### OAuth2Service (`services/http/oauth2_service.py`)

OAuth 2.0 token exchange for all four grant types.

| Method | Returns | Purpose |
|--------|---------|---------|
| `get_token(config)` | `OAuth2TokenResult` | Dispatch to grant-type handler |
| `refresh_token(token_url, refresh_token, client_id, client_secret, client_auth)` | `OAuth2TokenResult` | Refresh an expired token |

Grant types: Authorization Code (browser + redirect), Implicit (browser +
fragment capture), Password Credentials (direct POST), Client Credentials
(direct POST).  Browser-based flows open the system browser and start a
local HTTP server to capture the callback.

## TypedDict schemas

### SnippetOptions (`services/http/snippet_generator/generator.py`)

```python
class SnippetOptions(TypedDict, total=False):
    indent_count: int              # default 2
    indent_type: str               # "space" or "tab", default "space"
    trim_body: bool                # default False
    follow_redirect: bool          # default True
    request_timeout: int           # seconds, 0 = no timeout
    include_boilerplate: bool      # default True — imports/main wrappers
    async_await: bool              # default False — async/await vs promise chains
    es6_features: bool             # default False — ES6 import/arrow syntax
    multiline: bool                # default True — split shell commands across lines
    long_form: bool                # default True — --header vs -H
    line_continuation: str         # default "\\" — continuation char (\, ^, `)
    quote_type: str                # default "single" — URL quoting style
    follow_original_method: bool   # default False — keep method on redirect
    silent_mode: bool              # default False — suppress progress meter
```

### HttpService TypedDicts (`services/http/http_service.py`)

```python
class TimingDict(TypedDict):
    dns_ms: float
    tcp_ms: float
    tls_ms: float
    ttfb_ms: float
    download_ms: float
    process_ms: float

class NetworkDict(TypedDict):
    http_version: str
    remote_address: str
    local_address: str
    tls_protocol: str | None
    cipher_name: str | None
    certificate_cn: str | None
    issuer_cn: str | None
    valid_until: str | None

class HttpResponseDict(TypedDict):
    elapsed_ms: float                          # always present
    status_code: NotRequired[int]
    status_text: NotRequired[str]
    headers: NotRequired[list[dict[str, str]]]
    body: NotRequired[str]
    size_bytes: NotRequired[int]
    error: NotRequired[str]
    timing: NotRequired[TimingDict]
    request_headers_size: NotRequired[int]
    request_body_size: NotRequired[int]
    response_headers_size: NotRequired[int]
    response_uncompressed_size: NotRequired[int]
    network: NotRequired[NetworkDict]
```

### OAuth2TokenResult (`services/http/oauth2_service.py`)

```python
class OAuth2TokenResult(TypedDict):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: str
    error: str
```

### CollectionService TypedDicts (`services/collection_service.py`)

```python
class RequestLoadDict(TypedDict, total=False):
    name: str
    method: str
    url: str
    body: str | None
    request_parameters: str | list[dict[str, Any]] | None
    headers: str | list[dict[str, Any]] | None
    description: str | None
    scripts: dict[str, str] | None
    body_mode: str | None
    body_options: dict[str, Any] | None
    auth: dict[str, Any] | None
```

### EnvironmentService TypedDicts (`services/environment_service.py`)

```python
class VariableDetail(TypedDict, total=False):
    value: str           # resolved value
    source: str          # "collection", "environment", or "local"
    source_id: int       # collection_id or environment_id (0 for local)
    is_local: bool       # True when value is a per-request override

class LocalOverride(TypedDict):
    value: str                # overridden value
    original_source: str      # "collection" or "environment"
    original_source_id: int   # PK of the original source
```

### GraphQLSchemaService TypedDicts (`services/http/graphql_schema_service.py`)

```python
class SchemaTypeDict(TypedDict):
    name: str
    kind: str
    description: str

class SchemaResultDict(TypedDict):
    query_type: str
    mutation_type: str
    subscription_type: str
    types: list[SchemaTypeDict]
    raw: dict
```

### Import parser TypedDicts (`services/import_parser/models.py`)

```python
class ParsedSavedResponse(TypedDict): ...
class ParsedFolder(TypedDict): ...
class ParsedCollection(TypedDict): ...
class ParsedEnvironment(TypedDict): ...
class ImportResult(TypedDict): ...
class ImportSummary(TypedDict): ...
```

See `services/import_parser/models.py` for full field definitions.

### Theme TypedDict (`ui/styling/theme.py`)

```python
class ThemePalette(TypedDict): ...
```

See `ui/styling/theme.py` for full field definitions.

## Response viewer and popup system

`ResponseViewerWidget` displays the HTTP response with four tabs:
Body, Headers, Cookies, and Saved.

### Body tab

- **Format toolbar** — Pretty/Raw/Preview combo, Beautify button
- **`CodeEditorWidget`** — `QPlainTextEdit` subclass (read-only) with
  Pygments syntax highlighting, line numbers, fold gutter, word wrap,
  and search (Ctrl+F)

### Status bar (below tabs)

Four clickable labels show response metadata.  Each opens an `InfoPopup`
subclass:

| Label | Popup | Data source |
|-------|-------|-------------|
| Status code + text | `StatusPopup` | `status_code`, `status_text` |
| Response time | `TimingPopup` | `TimingDict` |
| Response size | `SizePopup` | `size_*` fields + `TimingDict` |
| Network info | `NetworkPopup` | `NetworkDict` |
