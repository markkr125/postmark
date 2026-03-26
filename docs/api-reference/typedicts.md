# TypedDict Catalogue

Complete reference of all `TypedDict` schemas used to pass structured
data across module boundaries.

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

**Neutral colours:**

| Field | Description |
|-------|-------------|
| `bg` | Background |
| `bg_alt` | Alternate background |
| `text` | Primary text |
| `text_muted` | Muted/secondary text |
| `border` | Border |
| `hover_bg` | Hover state background |
| `hover_tree_bg` | Tree item hover |
| `selected_bg` | Selection highlight |
| `input_bg` | Input field background |

**Semantic colours:**

| Field | Description |
|-------|-------------|
| `accent` | Primary accent |
| `success` | Success/positive |
| `warning` | Warning |
| `danger` | Danger/error |
| `muted` | Muted/disabled |
| `delete` | Delete action |
| `head` | Heading |
| `options` | Options/settings |

**Functional colours:**

| Field | Description |
|-------|-------------|
| `sending` | In-flight request indicator |
| `breadcrumb_sep` | Breadcrumb separator |

**Import dialog colours:**

| Field | Description |
|-------|-------------|
| `drop_zone_border` | Drop zone border |
| `drop_zone_bg` | Drop zone background |
| `drop_zone_active_bg` | Drop zone active state |
| `import_success` | Import success message |
| `import_error` | Import error message |

**Console colours:**

| Field | Description |
|-------|-------------|
| `console_bg` | Console background |
| `console_text` | Console text |

**Timing phase colours:**

| Field | Description |
|-------|-------------|
| `timing_prepare` | Preparation phase |
| `timing_dns` | DNS resolution |
| `timing_tcp` | TCP connection |
| `timing_tls` | TLS handshake |
| `timing_ttfb` | Time to first byte |
| `timing_download` | Download |
| `timing_process` | Processing |

**Variable colours:**

| Field | Description |
|-------|-------------|
| `variable_highlight` | Variable highlight background |
| `variable_unresolved_highlight` | Unresolved variable highlight |
| `variable_unresolved_text` | Unresolved variable text |

**Code editor colours:**

| Field | Description |
|-------|-------------|
| `editor_bracket_match` | Matched bracket highlight |
| `editor_gutter_bg` | Line number gutter background |
| `editor_gutter_text` | Line number text |
| `editor_error_underline` | Error squiggle |
| `editor_fold_indicator` | Code folding indicator |
| `editor_string` | String literal |
| `editor_number` | Number literal |
| `editor_keyword` | Keyword |
| `editor_comment` | Comment |
| `editor_tag` | XML/HTML tag |
| `editor_attribute` | Attribute name |
| `editor_punctuation` | Punctuation |
| `editor_fold_highlight` | Folded code highlight |
| `editor_indent_guide` | Indentation guide |
| `editor_active_indent_guide` | Active indentation guide |
| `editor_error_gutter_bg` | Error gutter background |
| `editor_fold_badge_bg` | Fold badge background |
| `editor_fold_badge_text` | Fold badge text |
| `editor_whitespace_dot` | Whitespace indicator |

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
