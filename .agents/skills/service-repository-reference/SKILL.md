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

### Run history repository (`run_history_repository.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `create_run(collection_id, source?)` | `RunHistoryModel` | Start a new run record |
| `finish_run(run_id, **stats)` | `None` | Finalise a run with duration, test counts, status |
| `add_result(run_id, **fields)` | `RunResultModel` | Add a per-request result |
| `get_runs_for_collection(collection_id, limit?)` | `list[RunHistoryModel]` | Runs for a collection, newest first |
| `get_run_results(run_id)` | `list[RunResultModel]` | Results for a run, ordered by ID |
| `delete_run(run_id)` | `bool` | Delete a single run (True if found) |
| `delete_runs_for_collection(collection_id)` | `int` | Delete all runs for a collection, return count |

### Local script repository (`local_script_repository.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `create_folder(name, parent_id?)` | `LocalScriptFolderModel` | Create folder |
| `create_script(folder_id, name, *, language, module_format="esm", content)` | `LocalScriptModel` | Create script; ``module_format`` validated via ``_normalize_module_format`` |
| `rename_script_and_rewrite_refs(script_id, new_name, *, language?, module_format?)` | `int` | Rename + rewrite ``pm.require("local:…")`` when virtual path changes (``.js`` ↔ ``.cjs``) |
| `move_script_and_rewrite_refs(script_id, new_folder_id)` | `int` | Move + rewrite local refs |
| `update_script_content(script_id, content, language?, module_format?)` | `None` | Persist editor body |

``module_format="commonjs"`` is only valid when ``language=="javascript"``; otherwise
``ValueError``. TypeScript/Python rows always store ``"esm"``.

### Local script query repository (`local_script_query_repository.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `fetch_all_local_scripts_tree()` | `dict[str, Any]` | Nested tree; script nodes include ``module_format`` |
| `get_script_by_id(script_id)` | `LocalScriptModel \| None` | PK lookup |
| `get_local_script_breadcrumb(script_id)` | `list[dict[str, Any]]` | Breadcrumb segments |

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

### RunHistoryService

All methods are `@staticmethod`.  Wraps `run_history_repository` for run
history CRUD.

| Method | Purpose |
|--------|---------|
| `create_run(collection_id, source?)` | Start a new run record |
| `finish_run(run_id, **stats)` | Finalise a run with stats (incl. `skipped`) |
| `add_result(run_id, **fields)` | Add a per-request result |
| `get_runs(collection_id, limit?)` | Runs for a collection as list of dicts |
| `get_results(run_id)` | Results for a run as list of dicts |
| `delete_run(run_id)` | Delete a single run |
| `delete_runs(collection_id)` | Delete all runs for a collection |

### LocalScriptService (`services/local_script_service.py`)

All methods are `@staticmethod`.  UI must use this module, not `database/`.

| Method | Purpose |
|--------|---------|
| `fetch_all()` | Nested local-scripts tree dict (includes ``module_format`` on script nodes) |
| `list_virtual_paths(*, language)` | Virtual paths for ``pm.require("local:…")`` autocomplete |
| `get_script_load_dict(script_id)` | Editor open payload (see ``LocalScriptLoadDict``) |
| `create_script(folder_id, name, *, language, module_format="esm", content)` | Create script |
| `rename_script(script_id, new_name, *, language?, module_format?)` | Rename + ref rewrite |
| `save_script_content(script_id, content, language?, module_format?)` | Persist buffer |

**CJS policy:** ``.cjs`` local scripts are leaf modules — no ``pm.require("local:…")``
inside CJS bodies (enforced in ``local_script_modules.resolve_required``). Consumers
use ``pm.require("local:…/file.cjs")`` from ESM pre-request/test scripts only.

**UI signals (local scripts tree):** ``new_script_clicked(str, str)`` (language,
module_format); ``new_script_requested(object, str, str)`` on header; ``script_rename_requested(int, str, str, str)`` on ``CollectionTree`` and ``CollectionWidget``.

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

### ScriptService

All methods are `@staticmethod`.  Resolves inherited script chains
by walking the collection ancestor tree.

| Method | Returns | Purpose |
|--------|---------|---------|
| `build_script_chain(request_id)` | `tuple[list[ScriptEntry], list[ScriptEntry]]` | Collect pre-request and test scripts from ancestors + self |

### ScriptEngine

All methods are `@staticmethod`.  Orchestrates script execution across
`DenoRuntime` / `JSRuntime` (Deno ``deno run`` subprocess) and `PyRuntime` (RestrictedPython subprocess).

| Method | Returns | Purpose |
|--------|---------|---------|
| `run_pre_request_scripts(chain, context)` | `ScriptOutput` | Run pre-request chain, merge outputs |
| `run_test_scripts(chain, context)` | `ScriptOutput` | Run test chain, merge outputs |
| `run_single(script, language, context)` | `ScriptOutput` | Run one script in specified runtime |

Module-level helper in `services/scripting/engine.py` (used by the script
editor gutter; not a `ScriptEngine` method):

| Function | Returns | Purpose |
|----------|---------|---------|
| `find_pm_tests(source, language)` | `list[dict[str, Any]]` | `{"name", "line"}` (1-based) for each `pm.test` (Python AST, JS esprima + regex fallback) |
| `find_top_level_statement_lines(source, language)` | `set[int]` | 0-based lines of top-level statements (step-debugger checkpoints); empty set means do not style breakpoints as unreachable |

`ScriptLinter` exposes `_esprima_parse_result` for the shared esprima JSON
parse (linting + `find_pm_tests` and `find_top_level_statement_lines`).

**Response assertions (Postman-compat):** In `data/scripts/pm_bootstrap.js`,
`pm.response.to` is a getter that returns a new `__Expectation` wrapping the
response (so `pm.response.to.have.status(200)` works).  **`pm.require`** in JS
loads `npm:` / `jsr:` packages only when the specifier is a **string literal**
in the user script: `js_runtime._detect_pm_require_specs` validates the name and
exact semver, `js_runtime._pm_require_imports_block` emits static ESM `import`s
and registers `globalThis.__pm_require_modules` (see `deno_runtime.deno_ipc_argv_and_env`
for cache + optional `--allow-net`).  In
`services/scripting/_py_sandbox.py`, `_PmResponse.to` returns `_Expectation(self)`;
`jsonBody` is aliased to `json_body` on the Python side.

**Python (Pyodide):** When `data/scripts/vendor_pyodide/pyodide.asm.wasm` exists and
Deno is available, `PyRuntime.execute` uses `pyodide_runtime.PyodideRuntime` →
`data/scripts/pyodide_run.mjs` (`loadPyodide` from `./vendor_pyodide/pyodide.mjs`,
`micropip` for `py_runtime.detect_pm_require_py_specs` literals, then
`data/scripts/pm_bootstrap.py` — generated by `scripts/gen_pm_bootstrap_pyodide.py` from
`_py_sandbox.py` (stdlib imports, `_console_emit` / `_console_logs`, `_Pm` excerpt), with
`postmark_ipc.send_request_sync`, `pm.require`, safe builtins including `print` → `_console_emit`,
and `collect_pm_output`.  Otherwise execution
stays on `_py_sandbox.py` + RestrictedPython (`PyRuntime.execute_restricted`).

Context builders and utilities in `services/scripting/context.py`:

| Function | Purpose |
|----------|---------|
| `build_pre_request_context(...)` | Build `ScriptInput` for pre-request scripts |
| `build_test_context(...)` | Build `ScriptInput` for test/post-response scripts |
| `normalize_events(events)` | Convert Postman-style event list to `{pre_request, test}` dict |
| `execute_sub_request(spec)` | HTTP bridge for `pm.sendRequest()` (scheme whitelist, rate-limited) |
| `load_globals()` | Load persisted global variables from `data/globals.json` |
| `save_globals(changes)` | Merge changes into persisted globals file |

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

### LocalScriptService TypedDicts (`services/local_script_service.py`)

```python
class LocalScriptLoadDict(TypedDict, total=False):
    id: int
    name: str
    language: str
    module_format: str  # "esm" | "commonjs"
    content: str
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

### Scripting TypedDicts (`services/scripting/__init__.py`)

```python
class ScriptInput(TypedDict):
    request: dict[str, Any]       # method, url, headers, body
    response: dict[str, Any]      # status, headers, body, elapsed_ms (test only)
    variables: dict[str, str]     # combined environment + collection vars
    environment_vars: dict[str, str]  # environment-scoped variables
    collection_vars: dict[str, str]   # collection-scoped variables
    global_vars: NotRequired[dict[str, str]]  # persisted global variables
    info: dict[str, Any]          # request name, iteration index
    iteration_data: NotRequired[dict[str, Any]]  # data-driven row (runner only)

class ScriptOutput(TypedDict):
    test_results: list[TestResult]          # pm.test() assertion results
    console_logs: list[ConsoleLog]          # console.log/warn/error output
    variable_changes: dict[str, str]        # pm.variables/environment/collection changes
    global_variable_changes: NotRequired[dict[str, str]]  # pm.globals changes
    request_mutations: dict[str, Any] | None  # pm.request.* mutations
    next_request: NotRequired[str | None]   # pm.execution.setNextRequest()
    skip_request: NotRequired[bool]         # pm.execution.skipRequest()

class ScriptEntry(TypedDict):
    code: str                     # script source code
    language: str                 # "javascript", "typescript", or "python"
    source_name: str              # display label (e.g. "Collection > Test")

class TestResult(TypedDict):
    name: str                     # test description
    passed: bool                  # assertion outcome
    error: str | None             # failure message
    duration_ms: float            # execution time

class ConsoleLog(TypedDict):
    level: str                    # "log", "warn", "error", "info"
    message: str                  # formatted message
    timestamp: float              # time.time() value
    source_line: NotRequired[int | None]  # 0-based editor line (best-effort)
```

### Theme TypedDict (`ui/styling/theme.py`)

```python
class ThemePalette(TypedDict): ...
```

See `ui/styling/theme.py` for full field definitions.

## Response viewer and popup system

`ResponseViewerWidget` displays the HTTP response with five tabs:
Body, Headers, Cookies, Test Results (hidden), and Pre-request (hidden).

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
