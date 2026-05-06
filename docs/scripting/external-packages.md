# External packages in scripts

This document covers how `pm.require` works in JavaScript and Python
scripts, and how to add new vendored libraries to the JS allowlist.

## Quick reference

```javascript
// JavaScript — npm and jsr (Postman-style)
const _ = pm.require('npm:lodash@4.17.21');
const fs = pm.require('jsr:@std/fs@1.0.0');
const z = pm.require('npm:zod');               // latest, not for prod

// JavaScript — legacy vendored allowlist (no network needed)
const moment = require('moment');
```

```python
# Python — PyPI via Pyodide + micropip
jmespath = pm.require("jmespath")
result = jmespath.search("a.b", {"a": {"b": 7}})

jose = pm.require("python-jose==3.3.0")        # exact version
```

## JavaScript: pm.require for npm and JSR

Specifier shapes:

- `npm:NAME`
- `npm:NAME@X.Y.Z`
- `npm:@SCOPE/NAME@X.Y.Z`
- `jsr:NAME@X.Y.Z`

Rules:

- The call **must** be a string literal — host-side regex detection
  happens at bundle build time. `const s = "npm:lodash"; pm.require(s);`
  will fail with "package was not bundled".
- Versions must be exact `X.Y.Z` — no ranges (`^`, `~`, `>=`), no tags
  (`latest`, `next`).

Resolution flow:

1. Detector regex `_PM_REQUIRE_RE` in
   [src/services/scripting/js_runtime.py](../../src/services/scripting/js_runtime.py)
   captures every `pm.require('reg:name@ver')` literal.
2. `_pm_require_imports_block` emits one
   `import * as __pm_req_<id> from 'npm:NAME@X.Y.Z';` line per spec
   plus a `globalThis.__pm_require_modules` registry mapping the
   original specifier string to the imported module.
3. The runtime shim
   [data/scripts/pm_bootstrap.js](../../data/scripts/pm_bootstrap.js)
   `pm.require(specifier)` looks up the registry and returns the module
   (`module.default ?? module`).
4. Permission flags only widen when at least one spec is present:
   `--allow-net=registry.npmjs.org,jsr.io,deno.land --node-modules-dir=auto`.

Bundling errors surface as a runtime error result. Example:

```text
pm.require: version must be exact (got '^1.0').
Ranges and tags like '^1.0' or 'latest' are not supported.
```

## JavaScript: legacy require() for vendored modules

The `require()` shim falls back to a fixed allowlist for offline-friendly
libraries. Names available today:

- `crypto-js`
- `lodash`
- `moment`
- `chai`
- `tv4`
- `ajv`
- `xml2js`
- `csv-parse/sync`
- `uuid`

These are vendored under [data/scripts/vendor/](../../data/scripts/vendor/)
and mapped in `_REQUIRE_MAP` in
[src/services/scripting/js_runtime.py](../../src/services/scripting/js_runtime.py).
See "Adding a new vendored library (JS)" below for the full recipe.

## Python: pm.require via Pyodide + micropip

Specifier shapes:

- `"pkg"` — latest version on PyPI.
- `"pkg==X.Y.Z"` — exact version.

Rules:

- Calls must be string literals (same reason as the JS path).
- Versions must be exact (e.g. `==1.0.0`); no ranges or tags.
- Only pure-Python wheels and Pyodide-built C-extension wheels work.
  Other native wheels (e.g. anything depending on `rpds-py`) cannot
  load.

Resolution flow:

1. `detect_pm_require_py_specs` in
   [src/services/scripting/py_runtime.py](../../src/services/scripting/py_runtime.py)
   collects every `pm.require("pkg")` or `pm.require("pkg==X.Y.Z")`
   literal.
2. `PyodideRuntime.execute` writes the spec list onto stdin to
   [data/scripts/pyodide_run.mjs](../../data/scripts/pyodide_run.mjs).
3. The Pyodide entry script awaits `micropip.install(spec)` for each
   spec before running the user script.
4. The Python-side `pm.require` shim in
   [data/scripts/pm_bootstrap.py](../../data/scripts/pm_bootstrap.py)
   imports and returns the module.
5. Permission flag changes when at least one spec is present:
   `--allow-net=pypi.org,files.pythonhosted.org`.

## Python: legacy curated helpers (RestrictedPython fallback)

When Deno is unavailable or Pyodide assets are missing, Python scripts
run under [src/services/scripting/_py_sandbox.py](../../src/services/scripting/_py_sandbox.py).
`pm.require` is **not available** in this mode. Curated helpers in
`_SAFE_STDLIB`:

- `json_loads`, `json_dumps`
- `re_match`, `re_search`, `re_findall`, `re_sub`
- `hashlib_md5`, `hashlib_sha256`, `hashlib_hmac_sha256`
- `b64encode`, `b64decode`
- `uuid_v4`
- `datetime_now`, `datetime_utcnow`
- `url_quote`, `url_urlencode`
- `math_ceil`, `math_floor`, `math_sqrt`, `math_pow`, `math_log`,
  `math_pi`, `math_e`

These are flat names available without `import`.

## Versioning rules

Both languages require exact `X.Y.Z`. No `^`, `~`, `>=`, no tags like
`latest` or `next`. Mirrors Postman's external-package-registries docs.

## Caching

| Language | Cache path                                              |
| -------- | ------------------------------------------------------- |
| JS       | `~/.cache/postmark/deno_cache/.deno_dir/`               |
| Python   | `~/.cache/postmark/pyodide_cache/`                      |

First call hits the network; subsequent runs are offline. Safe to
delete either cache to force a re-fetch.

## Sandbox limits

- Package size cap inherited from registry behaviour (Postman: 50 MB).
- JS: no top-level `await` in user scripts.
- Python (Pyodide): C-extension packages must ship Pyodide-built wheels.
- Sub-requests via `pm.sendRequest`: max 10 per script run.

## How resolution works internally

JS path (per script run):

1. Host calls `_detect_pm_require_specs(script)`.
2. Host calls `_pm_require_imports_block(specs)` and prepends the
   result to the bundle.
3. Host launches `deno run` with conditional `--allow-net` /
   `--node-modules-dir=auto` flags.
4. Deno resolves each `npm:NAME@X.Y.Z` import (cache hit or fetch).
5. The user script's `pm.require('npm:NAME@X.Y.Z')` returns the entry
   from the registry the host injected at step 2.

Python path (per script run):

1. Host calls `detect_pm_require_py_specs(script)`.
2. Host launches `deno run pyodide_run.mjs` with conditional
   `--allow-net=pypi.org,files.pythonhosted.org`.
3. The Deno entry awaits `micropip.install(spec)` for each detected
   spec before user code runs.
4. The user script's `pm.require("pkg")` returns
   `importlib.import_module("pkg")`.

## Adding a new vendored library (JS)

Use this recipe when adding a new `lodash`-class library that should be
available offline without `pm.require`.

1. Drop the JS source file into [data/scripts/vendor/](../../data/scripts/vendor/).
2. Add an entry to `_REQUIRE_MAP` in
   [src/services/scripting/js_runtime.py](../../src/services/scripting/js_runtime.py).
3. (Optional) Add the global identifier to `_GLOBAL_IMPLIES` if users
   typically use it without `require`.
4. Append the version to
   [data/scripts/vendor/VERSIONS.md](../../data/scripts/vendor/VERSIONS.md).
5. Add a test class to
   [tests/unit/services/test_script_vendor_libs.py](../../tests/unit/services/test_script_vendor_libs.py)
   following the `TestLodash` / `TestMoment` pattern.
