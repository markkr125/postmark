# Postman API Parity

Postmark's `pm.*` surface tracks the official Postman sandbox so that
scripts pasted from Postman run unmodified. This page is the canonical
parity matrix — what works, what differs, what's intentionally not
shipped.

> **Source of truth for supported names:**
> [`src/services/scripting/pm_api_schema.py`](../../src/services/scripting/pm_api_schema.py).
> A drift test
> ([`tests/unit/services/test_pm_api_schema_drift.py`](../../tests/unit/services/test_pm_api_schema_drift.py))
> walks the schema and asserts every entry resolves at runtime in the
> Deno bundle. Adding a new schema entry without a runtime
> implementation breaks CI.

> **Three runtimes mirror the same shape:**
> - Deno + JavaScript / TypeScript:
>   [`data/scripts/pm_bootstrap.js`](../../data/scripts/pm_bootstrap.js)
> - Pyodide + Python:
>   [`data/scripts/pm_bootstrap.py`](../../data/scripts/pm_bootstrap.py)
> - RestrictedPython subprocess (Python fallback):
>   [`src/services/scripting/_py_sandbox.py`](../../src/services/scripting/_py_sandbox.py)

## Quick reference

| Postman surface           | Postmark JS | Postmark Py | Notes                                                                                  |
|---------------------------|-------------|-------------|----------------------------------------------------------------------------------------|
| `pm.info.*`               | ✅           | ✅           | `requestName`, `requestId`, `iteration`, `iterationCount`. Python adds snake_case alts.|
| `pm.request.url` (Url)    | ✅           | ✅           | `toString/getHost/getPath/getQueryString/protocol/host/port/path` + mutable `query`.   |
| `pm.request.headers` (HeaderList) | ✅   | ✅           | Case-insensitive `get/has/find`, `add/remove/upsert` (mutable in pre-request only).    |
| `pm.request.body` (RequestBody) | ✅     | ✅           | Discriminated `mode/raw/urlencoded/formdata/graphql/file`.                             |
| `pm.response.*`           | ✅           | ✅           | `code/status/headers/responseTime/responseSize/body/text()/json()`.                    |
| `pm.response.reason()`    | ✅           | ✅           | Canonical reason phrase derived from `code`.                                            |
| `pm.response.mime()`      | ✅           | ✅           | Parses `Content-Type` to `{type, charset}`.                                             |
| `pm.response.dataURI()`   | ✅           | ✅           | Body encoded as `data:` URI.                                                            |
| `pm.response.size()`      | ✅           | ✅           | Falls back to `len(body)` when `responseSize` missing.                                  |
| `pm.response.cookies`     | ✅           | ✅           | Mirrors `pm.cookies` parsed from `Set-Cookie`.                                          |
| `pm.response.originalRequest` | ✅       | ✅           | Wrapped request that produced this response (immutable).                                |
| `pm.variables` (resolved) | ✅           | ✅           | Read-through: local → iterationData → environment → collection → globals. Writes local. |
| `pm.environment.*`        | ✅           | ✅           | `get/set/has/unset/clear/toObject/replaceIn`.                                           |
| `pm.collectionVariables.*`| ✅           | ✅           | Same surface. Python also exposes `pm.collection_variables`.                            |
| `pm.globals.*`            | ✅           | ✅           | Same surface.                                                                           |
| `pm.iterationData.*`      | ✅           | ✅           | `get/has/toObject`. Python: also `pm.iteration_data`.                                   |
| `pm.test(name, fn)`       | ✅           | ✅           | Records pass/fail/skipped; sync only.                                                   |
| `pm.test.skip(name, fn)`  | ✅           | ✅           | Records skipped without invoking `fn`.                                                  |
| Inline `ctx.skip()`       | ✅           | ✅           | Callback receives a context object with a `.skip()` method.                              |
| `pm.expect(...)` (chai)   | ✅ subset    | ✅ subset    | Common assertions implemented. Some chai extensions still missing — see below.          |
| `pm.execution.setNextRequest` | ✅       | ✅           | Python: also `set_next_request`.                                                        |
| `pm.execution.skipRequest` | ✅          | ✅           | Python: also `skip_request`.                                                            |
| `pm.execution.location`   | ✅           | ✅           | `current` is the folder/collection path.                                                 |
| `pm.cookies.get/getAll`   | ✅           | ✅           | Python: also `get_all`.                                                                  |
| `pm.cookies.jar()`        | ⚠️           | ⚠️           | `getAll`/`get` work; `set/unset/clear` raise documented "not yet supported" error.       |
| `pm.sendRequest` callback | ✅           | ✅           | Both runtimes invoke `(err, response)` callback.                                         |
| `pm.sendRequest` Promise  | ✅           | ❌           | JS returns `Promise.resolve(response)` so `await` works. Python is sync — no await.      |
| `pm.require("name")`      | ✅           | ✅           | Bare names map to bundled vendor table (`crypto-js`, `lodash`, `moment`, …).             |
| `pm.visualizer.set(...)`  | ❌           | ❌           | Stub raises `RuntimeError("not supported in postmark — see ...")`. Documented.           |
| Legacy `responseBody`     | ✅           | ✅           | Plus `responseCode`, `responseHeaders`, `tests`, `xml2Json` globals.                     |
| Legacy `postman.*` shim   | ✅           | ✅           | `setEnvironmentVariable`, `getEnvironmentVariable`, etc.                                |

Legend: ✅ supported · ⚠️ partial (read works, mutate stubs) · ❌ not
supported (intentional).

## Detailed shapes

### `Url` (`pm.request.url`)

| Member            | Description                                                                                              |
|-------------------|----------------------------------------------------------------------------------------------------------|
| `toString()`      | Full URL string.                                                                                          |
| `getHost()`       | Hostname (no port).                                                                                       |
| `getPath()`       | Pathname.                                                                                                 |
| `getQueryString()`| Raw query string (no leading `?`).                                                                        |
| `protocol`        | Scheme without trailing `:`.                                                                               |
| `host`            | Same as `getHost()`.                                                                                       |
| `port`            | String port (or empty when default).                                                                       |
| `path`            | Same as `getPath()`.                                                                                       |
| `query`           | Mutable `HeaderList` of query params. `query.add({key, value})` / `query.get(name)` / `query.toObject()`. |

### `HeaderList` (`pm.request.headers`, `pm.response.headers`, `body.urlencoded`, `body.formdata`)

| Member                       | Description                                                                                |
|------------------------------|--------------------------------------------------------------------------------------------|
| `get(name)`                  | Case-insensitive value lookup; `None` / `null` if absent.                                   |
| `has(name)`                  | Case-insensitive presence check.                                                            |
| `find(name)`                 | Returns `{key, value}` or `None`.                                                           |
| `idx(n)`                     | Returns `{key, value}` at index `n` (or `None`).                                            |
| `each(fn)`                   | Iterate `(entry) -> None` in insertion order.                                               |
| `all()`                      | Materialise as `[{key, value}, …]`.                                                         |
| `toObject()`                 | `{key: value}` dict (last write wins on duplicates).                                        |
| `add({key, value})`          | Append (mutable only). Raises on response headers.                                          |
| `remove(name)`               | Remove all entries with that case-insensitive name (mutable only).                          |
| `upsert({key, value})`       | Update existing or append (mutable only).                                                   |
| Python sugar                 | `headers["Name"]` reads, `headers["Name"] = "v"` upserts; `len(headers)`; `for h in headers`. |

### `RequestBody` (`pm.request.body`)

| Member         | Description                                                                |
|----------------|----------------------------------------------------------------------------|
| `mode`         | One of `"raw" \| "urlencoded" \| "formdata" \| "graphql" \| "file" \| ""`.  |
| `raw`          | String body for `mode="raw"`.                                              |
| `urlencoded`   | `HeaderList` of form fields (mutable).                                     |
| `formdata`     | `HeaderList` of multipart fields (mutable).                                |
| `graphql`      | `{query, variables, operationName}` dict (or `None`).                       |
| `file`         | File spec dict (or `None`).                                                |
| `toString()`   | Returns `raw` (compatibility with code that string-concatenates the body).  |

### `Response` (`pm.response`)

| Member               | Description                                                                              |
|----------------------|------------------------------------------------------------------------------------------|
| `code`               | HTTP status code (int).                                                                  |
| `status`             | Status text from host (may differ from canonical reason phrase — see `reason()`).         |
| `headers`            | Read-only `HeaderList`.                                                                  |
| `responseTime`       | Elapsed ms.                                                                              |
| `responseSize`       | Bytes (when host provides it).                                                            |
| `body`               | Raw body string. Python: private `_body`; access via `.text()` or `.json()`.              |
| `text()`             | Body as string.                                                                          |
| `json([reviver])`    | Parse as JSON. **`reviver` argument is ignored** in postmark.                            |
| `reason()`           | Canonical HTTP reason phrase for `code` (e.g. `200 → "OK"`).                              |
| `mime()`             | Parse `Content-Type` → `{type, charset}`.                                                |
| `dataURI()`          | Body encoded as `data:<mime>;base64,<...>`.                                              |
| `size()`             | `responseSize` if known, otherwise `len(body)`.                                          |
| `cookies`            | `pm.cookies`-shaped accessor parsed from this response's `Set-Cookie` headers.            |
| `originalRequest`    | Wrapped `_PmRequest` (immutable) representing the request that produced this response.    |
| `to`                 | Fresh chai chain rooted at the response (e.g. `pm.response.to.have.status(200)`).         |

### `pm.test`

| Form                                | Behaviour                                                                       |
|-------------------------------------|---------------------------------------------------------------------------------|
| `pm.test(name, fn)`                 | Run `fn`; failure if it throws. Records `{name, passed, error, duration_ms}`.   |
| `pm.test.skip(name, fn)`            | Record skipped result without invoking `fn`.                                    |
| Inline `ctx.skip()` inside callback | First positional arg of the callback is a context object with a `.skip()` method. Calling it short-circuits the callback and records the test as skipped. |

The Python callback may accept zero or one positional argument; the
runtime calls with the ctx and falls back to no-arg if a `TypeError` is
raised.

### `pm.expect(value)` chain

Implemented operators (both runtimes):

`equal/equals/eq`, `eql` (deep equal via JSON stringify), `a/an`,
`include/includes/contain/contains`, `property/has_property`,
`lengthOf/length` / `length_of`, `above/greaterThan/gt`,
`below/lessThan/lt`, `least/gte/at_least`, `most/lte/at_most`, `match`,
`status` (numeric or canonical reason phrase), `header(name[, value])`,
`body(string|RegExp)`, `oneOf([...])` / `one_of([...])`,
`jsonBody(path[, value])` (lodash-style `a.b[0].c` paths), `not_`/`not`
negation, plus boolean properties `true`/`false`/`null`/`undefined`/
`NaN`/`exist`/`empty` / Python `none`.

**Not yet shipped** (call sites raise `AttributeError` / `TypeError`):
`closeTo`, `keys`, `members`, `instanceof`/`instanceOf`, `throw`,
`nested.property`, `within`, `string`, `satisfy`. `eql` uses JSON
stringify deep equality (key order independent for dicts; doesn't
handle `undefined`, `BigInt`, NaN identity correctly).

### `pm.cookies.jar()`

| Method                          | Behaviour                                                                                   |
|---------------------------------|---------------------------------------------------------------------------------------------|
| `get(url, name[, callback])`    | Returns the cookie value parsed from this response's `Set-Cookie`. Optional callback fires. |
| `getAll(url[, callback])`       | Returns all known cookies for this response.                                                 |
| `set(...)`                      | Raises `RuntimeError("pm.cookies.jar().set is not yet supported in postmark")`.              |
| `unset(...)`                    | Raises with the analogous error.                                                              |
| `clear(...)`                    | Raises with the analogous error.                                                              |

The `url` argument is currently ignored — there's no host-side cookie
jar to scope by domain/path. Reads return what we know from this
response only.

### `pm.require`

Bare specifiers (`pm.require("crypto-js")`, `pm.require("lodash")`)
resolve via the bundled vendor table:
`tv4`, `xml2js`, `crypto-js`, `chai`, `lodash`, `moment`, `cheerio`,
`csv-parse/lib/sync`, `ajv`, `atob`, `btoa`, `uuid`. JS also accepts
`npm:` and `jsr:` prefixed specifiers via Deno's import system. Python
falls through to `importlib.import_module` for stdlib / pip packages.

### Legacy v1 globals

Available at the top level of every script (no `pm.` prefix):

| Global             | Type                                  | Source                                              |
|--------------------|---------------------------------------|------------------------------------------------------|
| `responseBody`     | `string`                              | `pm.response.body` (or `""` in pre-request).         |
| `responseCode`     | `{code, name}` object                 | `{code: pm.response.code, name: pm.response.reason()}`. |
| `responseHeaders`  | `{key: value}` plain object/dict      | `pm.response.headers.toObject()`.                    |
| `tests`            | `{}` mutable object                   | Postman v1 — assignments here are picked up by some test runners. |
| `xml2Json(xml)`    | function `(string) -> object \| null` | XML → nested object via `xml2js` (JS) / ElementTree (Python). |
| `postman.*`        | object with v1 helpers                | `setEnvironmentVariable`, `getEnvironmentVariable`, `clearEnvironmentVariable`, `setGlobalVariable`, `getGlobalVariable`, `clearGlobalVariable`, `setNextRequest`. |

These exist for compatibility with very old Postman scripts. New code
should use the modern `pm.*` API.

### `pm.visualizer.set(template, data, options)` — stub

Always raises:

```text
pm.visualizer.set is not supported in postmark —
see data/snippets/README.md (Out of scope) for the rationale.
```

The explicit raise (rather than a no-op) makes it obvious to users that
the call did nothing and prompts them to remove or replace it.

## Migration notes for users coming from Postman

| You wrote in Postman                                         | Use in Postmark                                                                              |
|--------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| `pm.request.url.query.add({key, value: "page=2"})`           | Same — `Url.query` is a real mutable `HeaderList`.                                            |
| `pm.request.body.mode === "urlencoded"`                       | Same — `body` is a discriminated union.                                                       |
| `pm.response.headers.get("Content-Type")`                     | Same in JS. Same in Python — case-insensitive `_HeaderList`, not a plain dict.                |
| `pm.response.cookies.get("token")`                            | Supported.                                                                                    |
| `pm.variables.get("baseUrl")` after setting on `environment`  | Returns env value (read-through).                                                             |
| `pm.test.skip("WIP", function () { ... })`                    | Supported — records skipped result without running the body.                                  |
| `pm.cookies.jar().set(url, ...)`                               | Throws documented "not yet supported" error. Use `pm.environment.set(...)` to store cookies.  |
| `pm.visualizer.set("<h1>{{name}}</h1>", data)`                 | Throws documented "not supported" error. Visualizer is out of scope.                          |
| `var data = pm.response.json();`                              | Use `const`/`let` (modern JS) — Postmark uses Deno LSP that warns on `var`.                   |

## Drift test contract

Anything you add to `pm_api_schema.py` is asserted to exist on the
runtime `pm` object by
[`tests/unit/services/test_pm_api_schema_drift.py`](../../tests/unit/services/test_pm_api_schema_drift.py).
The test bundles a probe script through Deno and checks `typeof
pm.<dotted.path>`. If a schema entry doesn't resolve, the test fails
with a list of missing names.

This is the contract that prevents `pm.environment.clear()` from
silently passing the linter while throwing at runtime — exactly the
class of bug that motivated the test in the first place.

## Tests

| Test file                                                                                                                | Coverage                                                                                                                                                                                                       |
|--------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`tests/unit/services/test_pm_api_schema_drift.py`](../../tests/unit/services/test_pm_api_schema_drift.py)             | Schema ↔ runtime parity on the JS bootstrap (every dotted path resolves).                                                                                                                                      |
| [`tests/unit/services/test_pm_python_parity.py`](../../tests/unit/services/test_pm_python_parity.py)                   | 24 tests covering Python `_HeaderList`, `_PmUrl`, request body union, response helpers (`reason`/`mime`/`dataURI`/`size`/`originalRequest`/`cookies`), resolved `pm.variables`, `pm.test.skip`, `pm.execution.location`, `pm.cookies.jar()`, legacy globals, `pm.visualizer.set` raises, camelCase aliases. |
| [`tests/unit/services/test_script_sandbox.py`](../../tests/unit/services/test_script_sandbox.py)                       | Python sandbox security + chai chain (`status`/`body`/`oneOf` etc.).                                                                                                                                            |

## Out of scope (intentional)

- `pm.visualizer.set` — stubbed throw, documented above.
- `pm.cookies.jar()` mutation methods (`set/unset/clear`) — pending host-side cookie jar.
- Python `pm.send_request` `await` — pyodide / RestrictedPython have no event loop.
- Some chai operators (`closeTo`/`keys`/`members`/`instanceof`/`throw`/`nested.property`/`within`/`string`/`satisfy`) and a structural deep-equal `eql` — current `eql` uses JSON stringify.

## Related

- [JavaScript API Reference](javascript-api.md) — full per-method JS API.
- [Python API Reference](python-api.md) — full per-method Python API.
- [Snippets](snippets.md) — author-facing snippet palette docs.
- [Examples](examples.md) — practical recipes.
- [Security](security.md) — sandbox model.
