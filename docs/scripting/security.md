# Security

Script execution uses defense-in-depth sandboxing for both JavaScript
and Python runtimes.  This page documents the threat model, sandbox
architecture, and resource limits.

## Threat Model

Postmark is a desktop app — the user runs scripts on their own machine.
Primary threats:

1. **Imported collections with malicious scripts** — a shared Postman
   collection could contain scripts that exfiltrate data or damage the
   filesystem.
2. **Copy-pasted scripts** from untrusted internet sources.
3. **Accidental damage** — infinite loops, memory exhaustion, or app
   state corruption.

Scripts are NOT like browser JavaScript.  The user explicitly imports a
collection or writes a script.  But users often don't read scripts
before running them, so defense-in-depth is mandatory.

## JavaScript Sandbox (V8 Isolate)

The JavaScript runtime uses PyMiniRacer, which embeds a V8 isolate.

| Capability | Status | Notes |
|-----------|--------|-------|
| File system access | Blocked | V8 has no `fs` module |
| Network access | Blocked | No `fetch`, `XMLHttpRequest`, `net` |
| Process spawning | Blocked | No `child_process`, `exec` |
| `require` / `import` | Blocked | No module system |
| `eval()` | Available | Runs inside same isolate |
| Timers (`setTimeout`) | Not available | V8 isolate has no event loop |

### Resource Limits

| Resource | Limit |
|----------|-------|
| Execution time | 5 seconds |
| Memory (heap) | 64 MB |
| Console messages | 200 per execution |
| `pm.sendRequest()` calls | 10 (JS-side); 50 total (host-side) |
| Sub-request response size | 10 MB |

Implementation: `src/services/scripting/js_runtime.py` —
`_TIMEOUT_MS = 5000`, `_MAX_MEMORY_BYTES = 67_108_864`.

## Python Sandbox (Three-Layer Defense)

### Layer 1: Subprocess Isolation

Python scripts run in a separate subprocess
(`src/services/scripting/_py_sandbox.py`).  A crash, exploit, or
resource exhaustion in the subprocess cannot affect the main Postmark
app.

### Layer 2: RestrictedPython Compilation

Scripts are compiled using `compile_restricted()` from RestrictedPython.
This performs AST-level blocking of:

- `import` statements
- `exec()` and `eval()` calls
- Augmented attribute access (all `_`-prefixed attributes blocked)

### Layer 3: Restricted Builtins + Resource Limits

A minimal whitelist of builtins is provided.  Dangerous builtins are
removed:

**Blocked:** `open`, `__import__`, `exec`, `eval`, `compile`,
`globals`, `locals`, `vars`, `dir`, `delattr`, `setattr`, `getattr`
(on `_`-prefixed names), `breakpoint`, `exit`, `quit`, `help`,
`input`, `memoryview`, `object.__subclasses__`.

**Allowed:** `abs`, `all`, `any`, `bool`, `dict`, `enumerate`,
`filter`, `float`, `int`, `isinstance`, `len`, `list`, `map`, `max`,
`min`, `range`, `reversed`, `round`, `set`, `sorted`, `str`, `sum`,
`tuple`, `type` (single-argument only), `zip`.

### Python Resource Limits (Linux)

| Resource | Limit | `rlimit` |
|----------|-------|----------|
| CPU time | 5 seconds | `RLIMIT_CPU` |
| Memory (address space) | 128 MB | `RLIMIT_AS` |
| File descriptors | 3 (stdin/stdout/stderr only) | `RLIMIT_NOFILE` |

Implementation: `_py_sandbox.py::_apply_resource_limits()`.  On
non-Linux systems, limits are best-effort (may not apply).

### Attribute Guard

The `_getattr_guard()` function rejects all access to `_`-prefixed
attributes.  This prevents escape attempts via `__class__`,
`__subclasses__`, `__dict__`, etc.

```text
pm.response.__class__  --> AttributeError: Attribute access denied: __class__
```

## Safe Standard Library

Python scripts cannot import modules.  Instead, a curated set of
functions is pre-injected into the script namespace.  See
[Python API Reference](python-api.md) for the full list.

## Console Rate Limiting

Both runtimes cap console output at 200 messages per execution.
Messages beyond the limit are silently dropped.

## What Scripts CAN Do

- Read request/response data via `pm.request` / `pm.response`.
- Set/get variables across scopes.
- Register named test assertions.
- Mutate the request in pre-request scripts.
- Parse JSON, use regex, compute hashes, encode/decode base64.
- Write to the Console panel via `console.log()` / `print()`.

## What Scripts CANNOT Do

- Access the filesystem.
- Make network requests (only via `pm.sendRequest()`, rate-limited,
  http/https only, 10 MB response cap).
- Import arbitrary modules (Python) or require packages (JavaScript).
- Access Postmark's internal state or database.
- Spawn processes.
- Access environment variables or OS information.
- Persist data outside of variables.
- Run longer than the timeout allows.

## For Contributors

### Adding Sandbox Tests

Every sandbox escape attempt MUST be covered by a test in
`tests/unit/services/test_script_sandbox.py`.  Test categories:

1. **Import blocking** — `import os`, `__import__("os")`.
2. **Attribute escape** — `__class__.__subclasses__()`.
3. **Builtin abuse** — `open()`, `exec()`, `eval()`.
4. **Resource exhaustion** — infinite loop, large allocation.
5. **getattr bypass** — `_`-prefixed attribute access.

### Security Test Requirements

Security tests are part of CI.  If a sandbox test fails, the build
fails.  New sandbox features must include escape-attempt tests.
