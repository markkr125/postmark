# Script snippet palette (`data/snippets/`)

## What lives here

This directory holds **declarative JSON** files that power the **Snippets** popover in the request and folder **Scripts** editors (Pre-request and Post-response). Each file defines named categories and one-click insertable code bodies for a single editor language.

## Adding a new language — step by step

1. **Pick the language id** used by `CodeEditorWidget.language` (e.g. `go`, `javascript`, `python`). The id must match the JSON filename: `data/snippets/<language>.json`.
2. **Copy a starter file** — duplicate [`javascript.json`](javascript.json) to `<language>.json` so you keep the category structure.
3. **Edit the JSON** — replace `language`, category names, snippet titles, and bodies per the schema below. Use `_comment` keys (any name starting with `_`) for notes; the loader ignores them.
4. **Restart Postmark** — snippet files are read once per process (`functools.lru_cache`). No Python code changes are required for the loader to pick up a new file.

## JSON schema

Top-level shape:

```json
{
  "language": "javascript",
  "categories": [
    {
      "name": "Workflows",
      "snippets": [
        {
          "name": "Send an HTTP request",
          "body": "pm.sendRequest({ ... });"
        }
      ]
    }
  ]
}
```

### Worked example (minimal)

```json
{
  "_comment": "Optional documentation — ignored by the loader.",
  "language": "javascript",
  "categories": [
    {
      "name": "Examples",
      "snippets": [
        { "name": "Log to console", "body": "console.log('hello');" }
      ]
    }
  ]
}
```

## Field semantics

| Field | Required | Purpose |
|-------|------------|---------|
| `language` | No (v1) | Documentary label; may match the filename basename. |
| `categories` | Yes (non-empty for useful files) | Ordered list of groups. |
| `categories[].name` | Per category | Shown as a **non-selectable** bold header in the list. |
| `categories[].snippets` | Per category | Ordered snippet rows under that header. |
| `categories[].snippets[].name` | Yes | Visible row label in the popover. |
| `categories[].snippets[].body` | Yes | Inserted **verbatim** at the text cursor when the row is chosen. |
| `categories[].contexts` | No | Optional list filtering where the category appears: `"pre"` (pre-request editor), `"post"` (post-response / test editor), `"local"` (local script tabs). When omitted, the category shows in **request** pre/post editors only (not local scripts). Built-in snippets whose bodies contain `pm.response` are also hidden on local scripts. |

Any key whose name starts with **`_`** (e.g. `_comment`) is **metadata** and is ignored by the parser at the document root and inside category or snippet objects (see [`loader.py`](../../src/ui/widgets/snippets/loader.py)).

## Insertion semantics

When the user picks a snippet, the UI calls `QTextCursor.insertText(body)` on the active script editor. That **replaces the current selection** if there is one, otherwise inserts at the caret. Newlines in `body` are preserved exactly as written in JSON (use `\n` in JSON strings).

## Language fallback

- **`typescript`** uses **`javascript.json`** — TypeScript scripts share the same Deno/JS `pm.*` surface as JavaScript, so no separate `typescript.json` is shipped in v1.
- Future fallbacks can be documented here alongside any new mappings in `loader._resolve_language()`.

## Caching

`load_snippets()` is memoised per resolved language. Restart the application after editing JSON to reload.

## Shipped categories

Both [`javascript.json`](javascript.json) (TypeScript resolves here too) and [`python.json`](python.json) include:

| Category | Contexts | Purpose |
|---|---|---|
| **Send requests** | `pre + post + local` | `pm.sendRequest` / `pm.send_request` patterns. |
| **Variables** | `pre + post + local` | Get / set / unset across the four scopes (globals, collection, environment, local). |
| **Request setup** | `pre + local` | Auth headers, dynamic IDs, timestamps, login flows. Hidden from the post-response editor. |
| **Tests** | `post` only | Postman-style assertions using `pm.response`. Hidden from pre-request and local script editors. |
| **Import npm / JSR** / **Import PyPI** | `pre + post + local` | `pm.require` examples; rows that use `pm.response` are omitted on local scripts. |

Snippet bodies should stay aligned with the **`pm` test surface** in [`data/scripts/pm_bootstrap.js`](../../data/scripts/pm_bootstrap.js) (Deno) and [`data/scripts/pm_bootstrap.py`](../../data/scripts/pm_bootstrap.py) (Pyodide). User Python in the **RestrictedPython subprocess** path uses the mirrored assertions in [`src/services/scripting/_py_sandbox.py`](../../src/services/scripting/_py_sandbox.py); ship **sandbox-safe** snippets only: use injected globals such as `json_loads`, `json_dumps`, `b64encode`, `uuid_v4`, and `datetime_now` instead of raw `import json`, `import base64`, `from datetime import …`, or `jsonschema` unless the allowlist is explicitly extended.

## Python differences from JavaScript

When porting a JS snippet to Python, the runtime maps cleanly for assertions but diverges on a few sandbox details:

| Concept | JavaScript | Python |
|---|---|---|
| Pickable lambdas | `function () { ... }` | `def _t(): ...; pm.test("name", _t)` (RestrictedPython forbids inline `lambda` for `pm.test`). |
| Variable declaration | `const`, `let` (no `var`) | Plain assignment; no declaration keyword. |
| Base64 encode | `btoa(...)` | `b64encode(...)` (sandbox builtin, returns `bytes` — call `.decode()` for a `str`). |
| UUID v4 | `pm.require("uuid").v4()` | `uuid_v4()` (sandbox builtin; no `import uuid`). |
| ISO timestamp | `new Date().toISOString()` | `datetime_now()` (sandbox builtin; no `import datetime`). |
| JSON encode/decode | `JSON.stringify(x)` / `JSON.parse(s)` | `json_dumps(x)` / `json_loads(s)` (sandbox builtins; no `import json`). |
| Header mutation | `pm.request.headers.add({key, value})` | `pm.request.headers["Name"] = "value"` (dict assignment). |
| Schema validation | `pm.expect(x).to.have.jsonSchema({...})` | Built-in subset validator; `pm.require("tv4")` / `pm.require("ajv")` for full draft-07. |

## Postman API parity

Both runtimes track Postman's `pm.*` surface (Deno JS via
[`pm_bootstrap.js`](../../data/scripts/pm_bootstrap.js); Pyodide and the
RestrictedPython subprocess via
[`pm_bootstrap.py`](../../data/scripts/pm_bootstrap.py) and
[`_py_sandbox.py`](../../src/services/scripting/_py_sandbox.py)):

- **Headers** — `pm.request.headers` and `pm.response.headers` are real
  `HeaderList` objects in both languages: case-insensitive `get/has/find`,
  ordered iteration via `each/all/idx`, `add/remove/upsert` (mutable on
  pre-request; immutable on response — raises on writes).
- **Url** — `pm.request.url` is a wrapped `Url` with `toString/getHost/
  getPath/getQueryString/protocol/host/port/path` plus a mutable `query`
  HeaderList (`url.query.add({key, value})`).
- **Request body** — discriminated union with `mode/raw/urlencoded/
  formdata/graphql/file`. Form-style modes use `HeaderList`.
- **Response** — `originalRequest`, `cookies`, `reason()`, `mime()`,
  `dataURI()`, `size()`, plus the existing `code/status/headers/body/
  responseTime/responseSize/text()/json()`.
- **Variables** — `pm.variables` is a *resolved* read-through scope:
  local → iterationData → environment → collectionVariables → globals.
  Writes land in local. `clear()` works on every scope.
- **`pm.test`** — `pm.test(name, fn)` plus `pm.test.skip(name, fn)` and
  inline `ctx.skip()` (callback receives a context object).
- **`pm.execution.location.current`** — folder/collection path of the
  current request.
- **`pm.require("lodash")`** — bare names map to bundled vendor modules
  (Python uses importlib with the same names).
- **Cookies** — `pm.cookies.jar()` returns a CookieJar shape; reads work
  (`getAll(url)` / `get(url, name)`); `set/unset/clear` raise a documented
  "not yet supported" error pending host-side cookie storage.
- **`pm.visualizer.set`** — explicitly throws "not supported in postmark"
  in both runtimes, by design (see Out of scope below).
- **Legacy v1 globals** — `responseBody`, `responseCode`,
  `responseHeaders`, `tests`, `xml2Json` exposed as user-script globals.
  Python scripts also get a `postman` shim with `setEnvironmentVariable`
  / `getResponseHeader` etc.
- **camelCase aliases (Python)** — `pm.collectionVariables`,
  `pm.iterationData`, `pm.sendRequest`, `pm.execution.setNextRequest`
  etc. are exposed alongside the snake_case names so pasted Postman JS
  translates cleanly.

### Known incompatibilities (intentional)

- `pm.visualizer.set(...)` always raises — see Out of scope.
- `pm.cookies.jar().set/unset/clear` raise a documented error pending
  host-side cookie store work.
- Python `pm.send_request` is **synchronous** (returns the wrapped
  `_PmResponse` immediately) — pyodide / RestrictedPython have no event
  loop, so `await` is unnecessary and not supported.
- Some chai operators (`closeTo`, `keys`, `members`, `instanceof`,
  `throw`, `nested.property`, `within`, `string`, `satisfy`) and a
  structural deep-equal `eql` are not yet implemented in either runtime.

## Postman idioms not shipped (v1)

- **Legacy `responseBody` string** — prefer `pm.response.text()` / `pm.response.json()` (and Python equivalents on `pm.response`).

## Out of scope (v1)

- Placeholders, tab stops, or cursor marks inside `body`.
- User-editable snippets or per-collection overrides.
- Hot reload without restart.

## Validation

After changing JSON or loader code, run:

```bash
poetry run pytest tests/ui/widgets/test_snippets_popup.py -x
```

All tests in that module should pass (exact count may grow with the test matrix).

## Related source

| Piece | Location |
|-------|-----------|
| Loader (`load_snippets`, `has_snippets`) | [`loader.py`](../../src/ui/widgets/snippets/loader.py) |
| Popover UI | [`popup.py`](../../src/ui/widgets/snippets/popup.py) |
| **Snippets** toolbar control | [`scripts_mixin.py`](../../src/ui/request/request_editor/scripts/scripts_mixin.py) (`_build_script_status_bar`) |

## Documentation acceptance (self-audit)

When extending snippets, confirm:

- This README stays at least **80 lines** if new sections are added (keep the runbook discoverable).
- JSON files retain a top-level `_comment` where non-obvious choices need explanation.
- TypeScript behaviour remains documented under **Language fallback**.
