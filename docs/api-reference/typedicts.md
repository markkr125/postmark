# TypedDict Catalogue

All `TypedDict` schemas used to pass structured data across modules.

## Service Layer

### RequestLoadDict

**Module:** `services/collection_service.py`

Data dict used to populate a `RequestEditorWidget`.

All fields are optional (`total=False`).

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Request name for display |
| `method` | `str` | HTTP method (GET, POST, etc.) |
| `url` | `str` | Request URL |
| `body` | `str \| None` | Request body text |
| `request_parameters` | `str \| list[dict[str, Any]] \| None` | Query parameters |
| `headers` | `str \| list[dict[str, Any]] \| None` | HTTP headers |
| `description` | `str \| None` | Request description |
| `scripts` | `dict[str, Any] \| None` | Pre/post-request scripts |
| `body_mode` | `str \| None` | Body mode: none, raw, form, json |
| `body_options` | `dict[str, Any] \| None` | Body-specific options |
| `auth` | `dict[str, Any] \| None` | Authentication config |

### SavedResponseDict

**Module:** `services/collection_service.py`

Full saved-response payload used by the sidebar UI.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Primary key |
| `request_id` | `int` | Foreign key to parent request |
| `name` | `str` | Response label |
| `status` | `str \| None` | HTTP status text |
| `code` | `int \| None` | HTTP status code |
| `headers` | `list[dict[str, Any]] \| None` | Response headers |
| `body` | `str \| None` | Response body text |
| `preview_language` | `str \| None` | Language hint for highlighting |
| `original_request` | `dict[str, Any] \| None` | Snapshot of the originating request |
| `created_at` | `str \| None` | ISO 8601 timestamp |
| `body_size` | `int` | Body size in bytes |

### VariableDetail

**Module:** `services/environment_service.py`

Variable metadata shown in hover popups and the variables panel.

Inherits from `_VariableDetailRequired` (required fields) with
`total=False` for optional extras.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `value` | `str` | yes | Resolved variable value |
| `source` | `str` | yes | Origin: "collection", "environment", or "local" |
| `source_id` | `int` | yes | Collection or environment ID (0 for local) |
| `is_local` | `bool` | no | True when value is a per-request override |

### LocalOverride

**Module:** `services/environment_service.py`

Per-request variable override stored in `TabContext.local_overrides`.

| Field | Type | Description |
|-------|------|-------------|
| `value` | `str` | Overridden variable value |
| `original_source` | `str` | Original source: "collection" or "environment" |
| `original_source_id` | `int` | Original collection or environment ID |

### TimingDict

**Module:** `services/http/http_service.py`

Per-phase timing breakdown in milliseconds.

| Field | Type | Description |
|-------|------|-------------|
| `dns_ms` | `float` | DNS resolution |
| `tcp_ms` | `float` | TCP connection (0 if reused) |
| `tls_ms` | `float` | TLS handshake (0 for plain HTTP) |
| `ttfb_ms` | `float` | Time to first byte |
| `download_ms` | `float` | Body download |
| `process_ms` | `float` | Processing overhead |

### NetworkDict

**Module:** `services/http/http_service.py`

Network-level metadata captured from the connection.

| Field | Type | Description |
|-------|------|-------------|
| `http_version` | `str` | HTTP version (e.g. "HTTP/1.1") |
| `remote_address` | `str` | Remote address and port |
| `local_address` | `str` | Local address and port |
| `tls_protocol` | `str \| None` | TLS version or None |
| `cipher_name` | `str \| None` | TLS cipher suite or None |
| `certificate_cn` | `str \| None` | Certificate Common Name or None |
| `issuer_cn` | `str \| None` | Issuer Common Name or None |
| `valid_until` | `str \| None` | Certificate expiry or None |

### HttpResponseDict

**Module:** `services/http/http_service.py`

Structured HTTP response dict passed from `HttpService` to the UI.
Uses `NotRequired` for optional fields.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `elapsed_ms` | `float` | yes | Total elapsed time in milliseconds |
| `status_code` | `int` | no | HTTP status code |
| `status_text` | `str` | no | HTTP status text |
| `headers` | `list[dict[str, str]]` | no | Response headers |
| `body` | `str` | no | Response body |
| `size_bytes` | `int` | no | Total response size |
| `error` | `str` | no | Error description on failure |
| `timing` | `TimingDict` | no | Timing breakdown |
| `request_headers_size` | `int` | no | Request headers size |
| `request_body_size` | `int` | no | Request body size |
| `response_headers_size` | `int` | no | Response headers size |
| `response_uncompressed_size` | `int` | no | Uncompressed body size |
| `network` | `NetworkDict` | no | Network metadata |

### SnippetOptions

**Module:** `services/http/snippet_generator/generator.py`

Per-snippet configuration (`total=False`, all optional).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `indent_count` | `int` | 2 | Indent characters per level |
| `indent_type` | `str` | "space" | "space" or "tab" |
| `trim_body` | `bool` | False | Strip body whitespace |
| `follow_redirect` | `bool` | True | Include redirect flag |
| `request_timeout` | `int` | 0 | Timeout in seconds (0 = none) |
| `include_boilerplate` | `bool` | True | Include imports/wrappers |
| `async_await` | `bool` | False | Use async/await syntax |
| `es6_features` | `bool` | False | Use ES6+ syntax |
| `multiline` | `bool` | True | Split shell commands |
| `long_form` | `bool` | True | Use long option flags |
| `line_continuation` | `str` | "\\" | Line continuation character |
| `quote_type` | `str` | "single" | "single" or "double" |
| `follow_original_method` | `bool` | False | Keep method on redirect |
| `silent_mode` | `bool` | False | Suppress progress output |

### OAuth2TokenResult

**Module:** `services/http/oauth2_service.py`

Result of an OAuth 2.0 token exchange.

| Field | Type | Description |
|-------|------|-------------|
| `access_token` | `str` | Access token (empty on error) |
| `token_type` | `str` | Token type (usually "Bearer") |
| `expires_in` | `int` | Expiration in seconds |
| `refresh_token` | `str` | Refresh token (empty if not provided) |
| `scope` | `str` | Granted scope (space-separated) |
| `error` | `str` | Error description (empty on success) |

### SchemaTypeDict

**Module:** `services/http/graphql_schema_service.py`

Summary of a single GraphQL type.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Type name |
| `kind` | `str` | Type kind (OBJECT, ENUM, SCALAR, etc.) |
| `description` | `str` | Human-readable description |

### SchemaResultDict

**Module:** `services/http/graphql_schema_service.py`

Parsed introspection result returned to the UI.

| Field | Type | Description |
|-------|------|-------------|
| `query_type` | `str` | Root Query type name |
| `mutation_type` | `str` | Root Mutation type name |
| `subscription_type` | `str` | Root Subscription type name |
| `types` | `list[SchemaTypeDict]` | All user-defined types |
| `raw` | `dict` | Full raw introspection response |

## Import Parser Types

### ParsedSavedResponse

**Module:** `services/import_parser/models.py`

A single saved response (Postman example).

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Response label |
| `status` | `str \| None` | HTTP status text |
| `code` | `int \| None` | HTTP status code |
| `headers` | `list[dict[str, Any]] \| None` | Response headers |
| `body` | `str \| None` | Response body |
| `preview_language` | `str \| None` | Language hint |
| `original_request` | `dict[str, Any] \| None` | Originating request snapshot |

### ParsedRequest

**Module:** `services/import_parser/models.py`

A single HTTP request extracted from an import source
(`total=False`).

| Field | Type | Description |
|-------|------|-------------|
| `type` | `str` | Always "request" |
| `name` | `str` | Request name |
| `method` | `str` | HTTP method |
| `url` | `str` | Request URL |
| `headers` | `list[dict[str, Any]] \| None` | Request headers |
| `request_parameters` | `list[dict[str, Any]] \| None` | Query parameters |
| `body` | `str \| None` | Request body |
| `body_mode` | `str \| None` | Body mode |
| `body_options` | `dict[str, Any] \| None` | Body options |
| `auth` | `dict[str, Any] \| None` | Authentication config |
| `description` | `str \| None` | Request description |
| `events` | `list[dict[str, Any]] \| None` | Pre/post-request scripts |
| `scripts` | `dict[str, Any] \| None` | Script metadata |
| `settings` | `dict[str, Any] \| None` | Request-specific settings |
| `protocol_profile_behavior` | `dict[str, Any] \| None` | Protocol behaviour flags |
| `saved_responses` | `list[ParsedSavedResponse]` | Saved example responses |

### ParsedFolder

**Module:** `services/import_parser/models.py`

A folder node in the collection tree.

| Field | Type | Description |
|-------|------|-------------|
| `type` | `str` | Always "folder" |
| `name` | `str` | Folder name |
| `description` | `str \| None` | Folder description |
| `auth` | `dict[str, Any] \| None` | Default auth for children |
| `events` | `list[dict[str, Any]] \| None` | Pre/post-request scripts |
| `children` | `list[ParsedFolder \| ParsedRequest]` | Nested items |
| `variables` | `list[dict[str, Any]] \| None` | Folder-level variables |

### ParsedCollection

**Module:** `services/import_parser/models.py`

A complete parsed collection ready for DB import.  Uses
`NotRequired` for optional fields.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | yes | Collection name |
| `items` | `list[ParsedFolder \| ParsedRequest]` | yes | Root-level items |
| `description` | `str \| None` | no | Collection description |
| `events` | `list[dict[str, Any]] \| None` | no | Scripts |
| `variables` | `list[dict[str, Any]] \| None` | no | Collection variables |
| `auth` | `dict[str, Any] \| None` | no | Default auth |

### ParsedEnvironment

**Module:** `services/import_parser/models.py`

A parsed environment with its variable list.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Environment name |
| `values` | `list[dict[str, Any]]` | Variable dicts with "key" and "value" |

### ImportResult

**Module:** `services/import_parser/models.py`

Aggregate result returned by any parser entry point.

| Field | Type | Description |
|-------|------|-------------|
| `collections` | `list[ParsedCollection]` | Parsed collections |
| `environments` | `list[ParsedEnvironment]` | Parsed environments |
| `errors` | `list[str]` | Parse errors encountered |

### ImportSummary

**Module:** `services/import_parser/models.py`

Summary of what was actually persisted to the database.

| Field | Type | Description |
|-------|------|-------------|
| `collections_imported` | `int` | Collections imported |
| `requests_imported` | `int` | Requests imported |
| `responses_imported` | `int` | Saved responses imported |
| `environments_imported` | `int` | Environments imported |
| `errors` | `list[str]` | Import errors |

## UI Layer

### ThemePalette

**Module:** `ui/styling/theme.py`

Colour slots consumed by the global stylesheet and widget painting.
Every field is a hex colour string.

| Category | Fields | Examples |
|----------|--------|----------|
| Neutral | 9 | `bg`, `bg_alt`, `text`, `text_muted`, `border`, `hover_bg`, `selected_bg` |
| Semantic | 6 | `accent`, `success`, `warning`, `danger`, `muted`, `delete` |
| HTTP method | 8 | `head`, `options`, `get`, `post`, `put`, `patch`, `delete` |
| Functional | 2 | `sending`, `breadcrumb_sep` |
| Import dialog | 5 | `drop_zone_border`, `import_success`, `import_error` |
| Console | 2 | `console_bg`, `console_text` |
| Timing phases | 7 | `timing_prepare`, `timing_dns`, `timing_tcp`, `timing_tls` |
| Variable highlight | 3 | `variable_highlight`, `variable_unresolved_highlight` |
| Code editor | 18 | `editor_bracket_match`, `editor_string`, `editor_keyword` |

See `src/ui/styling/theme.py` for the full field list.

### CollectionDict

**Module:** `ui/collections/collection_widget.py`

Nested dict flowing between collection fetcher and tree widget
(`total=False`).

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Item ID |
| `name` | `str` | Item name |
| `type` | `str` | "folder" or "request" |
| `children` | `dict[str, CollectionDict]` | Nested items (folders only) |
| `method` | `str` | HTTP method (requests only) |

## Scripting Types

Defined in `services/scripting/__init__.py`.  See
[ScriptEngine](services/script-engine.md) for usage.

### `ScriptInput`

| Field | Type | Description |
|-------|------|-------------|
| `request` | `dict[str, Any]` | Request data (url, method, headers, body) |
| `response` | `dict[str, Any] \| None` | Response data (`None` in pre-request) |
| `variables` | `dict[str, str]` | Merged variable scope |
| `environment_vars` | `dict[str, str]` | Environment-scoped variables |
| `collection_vars` | `dict[str, str]` | Collection-scoped variables |
| `global_vars` | `dict[str, str]` | Global variables (persisted to disk) |
| `info` | `dict[str, Any]` | Execution metadata (name, iteration) |
| `iteration_data` | `dict[str, Any]` | Data-driven row (runner only, optional) |

### `ScriptOutput`

| Field | Type | Description |
|-------|------|-------------|
| `test_results` | `list[TestResult]` | `pm.test()` assertion results |
| `console_logs` | `list[ConsoleLog]` | Console output lines |
| `variable_changes` | `dict[str, str]` | Variable scope mutations |
| `global_variable_changes` | `dict[str, str]` | Global scope mutations (optional) |
| `request_mutations` | `dict[str, Any] \| None` | Request mutations (pre-request only) |
| `next_request` | `str \| None` | `setNextRequest()` target (optional) |
| `skip_request` | `bool` | `skipRequest()` flag (optional) |

### `ScriptEntry`

| Field | Type | Description |
|-------|------|-------------|
| `code` | `str` | Script source code |
| `language` | `str` | `"javascript"`, `"typescript"`, or `"python"` |
| `source_name` | `str` | Display label (e.g. collection/folder name) |

### `TestResult`

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Test description |
| `passed` | `bool` | Assertion outcome |
| `error` | `str \| None` | Failure message |
| `duration_ms` | `float` | Execution time in milliseconds |

### `ConsoleLog`

| Field | Type | Description |
|-------|------|-------------|
| `level` | `str` | `"log"`, `"warn"`, `"error"`, or `"info"` |
| `message` | `str` | Formatted message |
| `timestamp` | `float` | UNIX timestamp |
