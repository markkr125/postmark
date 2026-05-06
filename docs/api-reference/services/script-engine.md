# ScriptEngine

Script execution engine — orchestrates JS and Python runtimes.

**Module:** `services/scripting/engine.py`
**Re-exported from:** `services/scripting/__init__.py`

## Class: `ScriptEngine`

All methods are `@staticmethod`.

### `run_pre_request_scripts`

```python
@staticmethod
def run_pre_request_scripts(
    chain: list[ScriptEntry],
    context: ScriptInput,
) -> ScriptOutput
```

Run pre-request scripts in top-down order (collection → folder →
request).  Variable changes from earlier scripts propagate to later
ones.

### `run_test_scripts`

```python
@staticmethod
def run_test_scripts(
    chain: list[ScriptEntry],
    context: ScriptInput,
) -> ScriptOutput
```

Run test scripts in bottom-up order (request → folder → collection).

### `run_single`

```python
@staticmethod
def run_single(
    script: str,
    language: str,
    context: ScriptInput,
) -> ScriptOutput
```

Run a single script without chain merging.  Returns empty output for
blank scripts.

## Class: `JSRuntime`

**Module:** `services/scripting/js_runtime.py`

`JSRuntime` provides bootstrap, polyfills, and vendor ``require`` resolution
for script bundles.  `execute` delegates to `DenoRuntime` in
`services/scripting/deno_runtime.py`, which runs user code in a
``deno run`` subprocess with a generated bundle and
`data/scripts/deno_drain.mjs` (line-JSON ``pm.sendRequest`` IPC to Python).

### `execute`

```python
@staticmethod
def execute(script: str, context: ScriptInput) -> ScriptOutput
```

Injects the bundle preamble, sets context, runs the script in Deno, extracts
state from stdout.  Returns valid `ScriptOutput` even on error.

- Subprocess hard timeout: 10 seconds (see `DenoRuntime`)
- A configured Deno binary (or managed download) is required

## Class: `PyRuntime`

**Module:** `services/scripting/py_runtime.py`

### `execute`

```python
@staticmethod
def execute(script: str, context: ScriptInput) -> ScriptOutput
```

Run Python in a sandboxed subprocess (`_py_sandbox.py`).  Sends
`ScriptInput` as JSON via stdin, reads `ScriptOutput` from stdout.
Returns valid `ScriptOutput` even on error.

- Timeout: 10 seconds (hard kill)
- Memory: 128 MB (`RLIMIT_AS`)
- CPU: 5 seconds (`RLIMIT_CPU`)

## Context Builders

**Module:** `services/scripting/context.py`

### `build_pre_request_context`

```python
def build_pre_request_context(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str,
    variables: dict[str, str],
    environment_vars: dict[str, str],
    collection_vars: dict[str, str],
    global_vars: dict[str, str] | None = None,
    info: dict[str, Any],
) -> ScriptInput
```

Build context for pre-request scripts.  `response` is `None`.

### `build_test_context`

```python
def build_test_context(
    *,
    request_data: dict[str, Any],
    response_data: dict[str, Any],
    variables: dict[str, str],
    environment_vars: dict[str, str],
    collection_vars: dict[str, str],
    global_vars: dict[str, str] | None = None,
    info: dict[str, Any],
) -> ScriptInput
```

Build context for test scripts.  `response` is populated.

### `apply_request_mutations`

```python
def apply_request_mutations(
    mutations: dict[str, Any] | None,
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str,
) -> tuple[str, str, dict[str, str], str]
```

Apply pre-request script mutations.  Returns
`(method, url, headers, body)`.

### `apply_variable_changes`

```python
def apply_variable_changes(
    changes: dict[str, str],
    local_overrides: dict[str, str],
) -> dict[str, str]
```

Merge variable changes into local overrides.  Returns new dict.

### `normalize_events`

```python
def normalize_events(events: Any) -> dict[str, str]
```

Convert events from Postman list format or internal dict format to
`{"pre_request": "...", "test": "..."}`.

### `execute_sub_request`

```python
def execute_sub_request(spec: dict[str, Any]) -> dict[str, Any]
```

Execute a single HTTP sub-request for `pm.sendRequest()`.  Validates
scheme whitelist (http/https only), parses Postman-style headers and
body, returns response dict or `{"error": "..."}`.

### `load_globals` / `save_globals`

```python
def load_globals() -> dict[str, str]
def save_globals(changes: dict[str, str]) -> None
```

Load/save global variables from `data/globals.json`.  `save_globals`
merges changes into the existing file.

## Function: `detect_advanced_features`

**Module:** `services/scripting/feature_detect.py`
**Re-exported from:** `services/scripting/__init__.py`

```python
def detect_advanced_features(script: str, language: str) -> set[str]
```

Scan a script for advanced features that require the Deno runtime.
Returns a set of feature flags: `"async"` for `async/await` patterns,
`"npm"` for `require("npm:...")` or `import ... from "npm:..."`.
Returns empty set for Python scripts or blank input.

**Constants:** `FEATURE_ASYNC = "async"`, `FEATURE_NPM = "npm"`

## Class: `DenoManager`

**Module:** `services/scripting/deno_manager.py`
**Re-exported from:** `services/scripting/__init__.py`

All methods are `@staticmethod`.

### `is_available`

```python
@staticmethod
def is_available() -> bool
```

Return `True` if the Deno binary exists and is executable.

### `deno_path`

```python
@staticmethod
def deno_path() -> Path | None
```

Return the path to the cached Deno binary, or `None` if not installed.

### `download`

```python
@staticmethod
def download(
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path
```

Download the pinned Deno release from GitHub.  Extracts the zip to
`runtime_dir()` and makes the binary executable.  Calls
`progress_callback(received_bytes, total_bytes)` during download.
Returns the path to the Deno binary.

### `remove`

```python
@staticmethod
def remove() -> None
```

Delete the cached Deno binary directory.

### `download_url`

```python
@staticmethod
def download_url() -> str
```

Return the GitHub release URL for the pinned Deno version.

### `runtime_dir`

```python
@staticmethod
def runtime_dir() -> Path
```

Return the directory where the Deno binary is cached
(`~/.local/share/postmark/runtimes/deno-<version>/`).