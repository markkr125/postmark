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
- Omitting `@version` (`npm:lodash`) is allowed — Deno resolves the registry
  **current** release at run time. LSP pins the same via a registry lookup for
  IntelliSense.
- When you include `@version`, it must be exact `X.Y.Z` — no ranges (`^`,
  `~`, `>=`), no tags (`latest`, `next`).

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

## LSP types for `pm.require` (JS / TS)

When script LSP is enabled, Postmark always:

1. Copies **`stubs/pm.d.ts`** into the Deno workspace (base `pm.*` API; `pm.require` fallback is `unknown`).
2. Scans the open script for `pm.require('npm:…')` / `pm.require('jsr:…')` string literals and writes **`pm_require_index.ts`** with `import type * as … from "npm:…"` plus **`declare global { namespace pm { … } }`** overloads so Deno narrows each literal specifier to that package's types.
3. Runs **`deno cache`** for newly seen specifiers (needs a configured Deno binary).

Unversioned `npm:lodash` uses the registry **latest** for LSP types (npm
`dist-tags.latest` / JSR `meta.json`). Pin `npm:lodash@4.17.21` when you need
a fixed version across machines and CI.

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

## Private package registries

`pm.require("npm:…")`, `pm.require("jsr:…")` and Python `pm.require(…)` can
be routed through your own private mirrors. Configure them from **Settings →
Scripting → Private package registries**. Postman gates this functionality
behind their Enterprise plan ($49/user/month) and supports npm + JSR only.
Postmark ships the same plumbing **for free**, with PyPI included.

### Where credentials are stored

By default secrets go into the OS keychain via the
[`keyring`](https://pypi.org/project/keyring/) library — macOS Keychain,
GNOME Keyring / KWallet, or Windows Credential Manager. When keyring is
unavailable Postmark falls back to a Fernet-encrypted JSON blob under the
per-user config dir (`~/.config/postmark/scripting_secrets.enc` on Linux,
the platform-equivalent elsewhere), with a key derived from the machine ID.
The Settings page shows which backend is active and surfaces a "less safe"
warning on the file fallback. **Tokens never appear in `QSettings`.**

### npm scoped registries

Each row in the registries table maps a single `@scope` to a registry URL
plus optional authentication. The runtime emits a per-execution `.npmrc`
into the Deno bundle working directory **whenever a script triggers
network mode** — i.e. the bundle contains a literal
`pm.require("npm:…")` or `pm.require("jsr:…")` specifier that Postmark
detects statically. Scripts with no `pm.require` install (pure
`pm.test` / variable manipulation) run with networking disabled and no
`.npmrc` is written. The file is chmod `0600` and Deno reads it from the
project root per the
[Deno private NPM registries](https://docs.deno.com/runtime/manual/node/private_registries/)
docs:

```
@mycompany:registry=https://npm.mycorp.io/
//npm.mycorp.io/:_authToken=<resolved from secret store>
```

Token auth emits `_authToken=` (the modern key used by Verdaccio, Nexus,
Cloudsmith, Artifactory, GitHub Packages). Basic auth emits
`_auth=<base64(user:password)>`. The "Override default npm registry"
line edit adds a `registry=…` line that replaces `registry.npmjs.org` for
any unscoped specifier.

Environment-variable expansion inside `.npmrc` is unreliable on Deno
(see [supabase/cli#4927](https://github.com/supabase/cli/issues/4927));
Postmark resolves tokens itself before writing the file rather than
relying on `${NPM_TOKEN}` placeholders.

### JSR private registries

JSR.io [does not host private packages](https://github.com/jsr-io/jsr/issues/203).
Enterprises run JSR through an npm-compatible upstream proxy
(Cloudsmith, Artifactory). Add the proxy as a scope-mapped row with **JSR**
selected in the *Type* column; the on-disk `.npmrc` format is identical
because both go through the same Deno npm machinery.

### Private PyPI (Pyodide runtime)

Set **Primary index URL** to replace the public PyPI mirror — Postmark
calls `micropip.set_index_urls([…])` before the first `pm.require`
install. Use **Extra index URL** sparingly: pip docs warn that
`--extra-index-url` enables dependency-confusion attacks, and we surface
the same warning in the dialog. Authentication is URL-embedded
(`https://user:token@pypi.mycorp.io/simple/`) since `micropip` has no
`.netrc` parsing.

The RestrictedPython subprocess runtime (no Pyodide) has no install
path at all — private PyPI applies only when Pyodide is the active Python
runtime.

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
