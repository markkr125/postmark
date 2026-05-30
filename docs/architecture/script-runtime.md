# Script runtime architecture

This document describes how a user script becomes a running, sandboxed
subprocess in Postmark. Read this before changing anything under
[src/services/scripting/](../../src/services/scripting/) or
[data/scripts/](../../data/scripts/).

## Overview

Each user script runs in a one-shot subprocess. The host fills the
`pm.*` context (request, response, variables, environment, etc.) into
the subprocess, the subprocess streams `console.log` and `pm.sendRequest`
events as JSON lines, and emits a single `__done__` JSON envelope on
completion. The host parses that envelope and returns a `ScriptOutput`.

Three execution modes exist today (TypeScript shares the Deno JavaScript path; the temp bundle uses a `.ts` extension so Deno strips types):

- **JavaScript via Deno** — [src/services/scripting/deno_runtime.py](../../src/services/scripting/deno_runtime.py).
- **Python via Pyodide (CPython on WebAssembly)** — [src/services/scripting/pyodide_runtime.py](../../src/services/scripting/pyodide_runtime.py).
- **Python via RestrictedPython (legacy fallback)** — [src/services/scripting/_py_sandbox.py](../../src/services/scripting/_py_sandbox.py).

Dispatch happens in [src/services/scripting/engine.py](../../src/services/scripting/engine.py).
The Python path additionally has its own dispatch step in
[src/services/scripting/py_runtime.py](../../src/services/scripting/py_runtime.py)
(`_use_pyodide()` chooses Pyodide when both Deno and the vendored
Pyodide WASM assets are present, otherwise falls back to RestrictedPython).

## Lifecycle of a script run

1. UI invokes `engine.execute_*` with the script and a context dict.
2. The engine selects a runtime by language.
3. The runtime builds a bundle (or temp file), spawns a subprocess with
   locked-down flags, writes the context, reads stdout JSON lines.
4. The subprocess emits `{"__ipc__": "sendRequest", ...}` for each
   sub-request the user script makes; the host fulfils them and writes
   the response back on stdin.
5. On completion the subprocess emits one
   `{"__done__": true, "test_results": [...], "console_logs": [...], "variable_changes": {...}, ...}`
   line on stdout.
6. The runtime maps the `__done__` envelope into a `ScriptOutput` and
   returns it.

## The Deno subprocess (JavaScript)

Entry: `DenoRuntime.execute` in [deno_runtime.py](../../src/services/scripting/deno_runtime.py).

Default flags:

```text
deno run --no-prompt --no-lock
  --allow-read=<bundle dir>,<cache dir>,<scripts dir>
  --allow-write=<cache dir>
  --allow-env
```

When the user script contains `pm.require('npm:...')` or `pm.require('jsr:...')`,
the host adds:

```text
  --allow-net=registry.npmjs.org,jsr.io,deno.land
  --node-modules-dir=auto
```

Cache directory: `_postmark_deno_user_cache_dir()` returns
`$XDG_CACHE_HOME/postmark/deno_cache/` on Linux, the macOS / Windows
equivalents otherwise. `DENO_DIR` is pinned to `<cache>/.deno_dir/` so
npm/jsr packages persist across runs.

The host-to-subprocess sub-request bridge is `_ipc_subprocess` in the
same file.

## The Pyodide subprocess (Python)

Entry: `PyodideRuntime.execute` in [pyodide_runtime.py](../../src/services/scripting/pyodide_runtime.py).

Same Deno binary as the JS path, different bundle:
[data/scripts/pyodide_run.mjs](../../data/scripts/pyodide_run.mjs) is a
small Deno script that loads CPython-on-WASM from
[data/scripts/vendor_pyodide/](../../data/scripts/vendor_pyodide/) (Pyodide
0.26.4 vendored at app release time, pinned in
[data/scripts/vendor_pyodide/VERSION](../../data/scripts/vendor_pyodide/VERSION)).

`pm.require` calls in the user script are detected at bundle time by
`detect_pm_require_py_specs` in
[py_runtime.py](../../src/services/scripting/py_runtime.py); each spec is
pre-installed via `micropip.install()` before the user script runs. The
Python-side `pm.*` API is provided by
[data/scripts/pm_bootstrap.py](../../data/scripts/pm_bootstrap.py).

Dispatch gate: `_use_pyodide()` in
[py_runtime.py](../../src/services/scripting/py_runtime.py) returns
true when both Deno and `data/scripts/vendor_pyodide/pyodide.asm.wasm`
exist; otherwise the legacy CPython sandbox runs.

## The legacy CPython sandbox (fallback)

[src/services/scripting/_py_sandbox.py](../../src/services/scripting/_py_sandbox.py)
runs when `_use_pyodide()` is false. Three layers of defence:

- OS-level resource limits.
- RestrictedPython AST gate (no `import`, no `exec`, no `eval`).
- Pruned `_SAFE_BUILTINS` and curated `_SAFE_STDLIB` (flat helpers like
  `json_loads`, `re_*`, `hashlib_*`, `b64*`, `uuid_v4`, `datetime_*`,
  `url_*`, `math_*`).

`pm.require` is **not available** in this fallback — only the curated
helpers above.

## Bundle assembly (JS path)

`_build_bundle_text` in [deno_runtime.py](../../src/services/scripting/deno_runtime.py)
concatenates parts in this order:

1. `import { readSync, writeSync } from "node:fs";`
2. `_pm_require_imports_block(specs)` — generated
   `import * as __pm_req_<id> from 'npm:...';` lines plus a
   `globalThis.__pm_require_modules` registry consumed by the
   `pm.require` shim in [pm_bootstrap.js](../../data/scripts/pm_bootstrap.js).
3. Polyfills ([data/scripts/vendor/polyfills.js](../../data/scripts/vendor/polyfills.js)).
4. Vendor allowlist files for any `require('name')` calls.
5. `var __pm_context = { ... };` (JSON-encoded host context).
6. [data/scripts/pm_bootstrap.js](../../data/scripts/pm_bootstrap.js).
7. The user script.
8. [data/scripts/deno_drain.mjs](../../data/scripts/deno_drain.mjs).

The host writes that concatenated text to a temp file under a unique directory:
`bundle.mjs` when the script language is `javascript`, or `bundle.ts` when it
is `typescript`, so Deno parses and type-strips the latter. The inline Esprima
linter does not run on TypeScript (annotations would produce false positives)
until a TS-aware parser is wired in; debug bundles follow the same filename rule.

## Pyodide entry script (Python path)

[data/scripts/pyodide_run.mjs](../../data/scripts/pyodide_run.mjs) flow:

1. Read one stdin JSON line: `{user_script, context, pm_require}`.
2. `loadPyodide({ indexURL: vendor_pyodide/, packageCacheDir: <pkgs dir> })` — the host sets `PM_PYODIDE_CACHE` (see [pyodide_runtime.py](../../src/services/scripting/pyodide_runtime.py)).
3. For each spec in `pm_require`: load `micropip` and `await micropip.install(spec)`.
4. Register the `postmark_ipc` JS module for synchronous `pm.send_request` IPC; set `__pm_context_json`; `runPythonAsync` on
   [data/scripts/pm_bootstrap.py](../../data/scripts/pm_bootstrap.py); call `init_pm()`.
5. `await pyodide.runPythonAsync(...)` runs `run_user_script(<user source>)` from `pm_bootstrap.py` (not a bare top-level `exec` of the script string alone).
6. `pyodide.runPython("import json; json.dumps(collect_pm_output())")`; merge Python-side `console_logs` with Pyodide stdout/stderr callbacks; write one `{"__done__": true, ...}` line to stdout.

## IPC protocol (stdin/stdout JSON lines)

Subprocess to host:

```json
{"__ipc__": "sendRequest", "spec": { "method": "GET", "url": "..." }}
```

```json
{"__done__": true,
 "test_results": [...],
 "console_logs": [...],
 "variable_changes": {...},
 "request_mutations": null,
 "next_request": null,
 "skip_request": false}
```

Host to subprocess (in response to a `sendRequest`): one JSON line
containing the response body, written to the subprocess's stdin.

The canonical mapping from `__done__` to `ScriptOutput` lives in
`_apply_done_line` in [deno_runtime.py](../../src/services/scripting/deno_runtime.py).

## Permission boundary

| Flag                                                              | Capability                                  |
| ----------------------------------------------------------------- | ------------------------------------------- |
| `--no-prompt`                                                     | Refuse all unspecified permissions.         |
| `--no-lock`                                                       | Ignore a user-level `deno.lock` that may be incompatible with the bundle. |
| `--allow-read=<dirs>`                                             | Read access to listed directories only.     |
| `--allow-write=<dir>`                                             | Write access scoped to the cache directory. |
| `--allow-env`                                                     | Read process env vars (no writes).          |
| `--allow-net=registry.npmjs.org,jsr.io,deno.land` (JS, opt-in)    | Outbound to npm/jsr only.                   |
| `--allow-net=pypi.org,files.pythonhosted.org` (Python, opt-in)    | Outbound to PyPI only.                      |
| `--node-modules-dir=auto` (JS, opt-in)                            | Allow Deno to materialise a node_modules.  |

Rules: never widen `--allow-net` to a wildcard; never drop
`--no-prompt`; only widen `--allow-write` to the cache directory.

## Caching and offline behaviour

- JS: `~/.cache/postmark/deno_cache/.deno_dir/` (Linux). npm and jsr
  packages cache on first use; subsequent runs are offline.
- Python: `~/.cache/postmark/pyodide_cache/` (micropip wheels under `pkgs/`,
  Deno metadata under `deno_dir/`). micropip wheels cache on
  first use; subsequent runs are offline. The Pyodide runtime itself is
  shipped under `data/scripts/vendor_pyodide/` and never fetched.
- Safe to delete either cache to force a re-fetch.

## Debug variant

[src/services/scripting/debug/deno_debug.py](../../src/services/scripting/debug/deno_debug.py)
mirrors `deno_runtime.py` but inserts `--inspect-brk=127.0.0.1:<port>`
into the Deno argv and compensates for the extra header line in
`user_script_first_line_0_in_debug_bundle`.

There is no Pyodide-side debug variant yet — Pyodide-side breakpoints
are an open follow-up.

## Error model

Bundle-time errors (e.g. invalid `pm.require` versions) raise
`RuntimeError("Script bundling failed: ...")` from `_build_bundle_text`,
caught by `DenoRuntime.execute` and converted to a single failed
"runtime error" test result via `_error_output`.

Subprocess errors (uncaught exceptions, missing `__done__`) are turned
into the same shape; stderr is appended to the error message when
present.

## Where to extend next

- Add or remove an external package: see
  [scripting/external-packages.md](../scripting/external-packages.md).
- Add a new scripting language: see
  [guides/adding-script-language.md](../guides/adding-script-language.md).
