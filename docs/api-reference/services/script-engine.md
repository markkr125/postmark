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

### `execute`

```python
@staticmethod
def execute(script: str, context: ScriptInput) -> ScriptOutput
```

Run JavaScript in a fresh V8 isolate (PyMiniRacer).  Injects
`pm_bootstrap.js` preamble, sets context, executes script, extracts
state.  Returns valid `ScriptOutput` even on error.

- Timeout: 5000 ms
- Max memory: 64 MB

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