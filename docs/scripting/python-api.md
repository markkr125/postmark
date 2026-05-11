# Python API Reference

Complete reference for the `pm` object available in Python scripts.
Python scripts use Pythonic naming (`snake_case`) **and** Postman
camelCase aliases — `pm.collection_variables` and
`pm.collectionVariables` are the same scope. The Pyodide and
RestrictedPython runtimes share this surface.

> See [Postman API parity](postman-parity.md) for the full matrix and
> [Snippets](snippets.md) for the in-editor snippet palette.

> **Two Python runtimes:**
> - [`pm_bootstrap.py`](../../data/scripts/pm_bootstrap.py) for
>   Pyodide (default when Deno + Pyodide assets are available).
> - [`_py_sandbox.py`](../../src/services/scripting/_py_sandbox.py) for
>   the RestrictedPython subprocess fallback.
> Both runtimes mirror each other's `pm.*` shape.

## `pm.info`

Read-only execution metadata.

| Property | Type | Description |
|----------|------|-------------|
| `pm.info.request_name` | `str` | Name of the current request |
| `pm.info.request_id` | `str` | Database ID of the current request |
| `pm.info.iteration` | `int` | Current iteration index (runner only) |
| `pm.info.iteration_count` | `int` | Total iterations (runner only) |

## `pm.request`

The current HTTP request.  Mutable in pre-request scripts only.

| Property              | Type            | Mutable      | Description                                                              |
|-----------------------|-----------------|--------------|--------------------------------------------------------------------------|
| `pm.request.url`      | `_PmUrl`        | pre-request  | Wrapped URL with `getHost/getPath/getQueryString/protocol/host/port/path` and a mutable `query` `_HeaderList`. String-coerces to the full URL. |
| `pm.request.method`   | `str`           | pre-request  | HTTP method.                                                              |
| `pm.request.headers`  | `_HeaderList`   | pre-request  | See below — case-insensitive `get/has/find`, dict-style `[]` sugar.       |
| `pm.request.body`     | `_PmRequestBody`| pre-request  | Discriminated union — `mode/raw/urlencoded/formdata/graphql/file`.         |

```python
# Pre-request: set auth header (dict-style sugar on _HeaderList).
pm.request.headers["Authorization"] = "Bearer " + pm.variables.get("token")

# Or the Postman-canonical form:
pm.request.headers.upsert({"key": "Authorization", "value": "Bearer " + pm.variables.get("token")})

# URL inspection / mutation.
print(pm.request.url.getHost())                      # "api.example.com"
pm.request.url.query.add({"key": "page", "value": "2"})
```

### `_HeaderList`

Same shape as the JS `HeaderList`. Used for `pm.request.headers`,
`pm.response.headers`, and `body.urlencoded` / `body.formdata`.

| Method                        | Description                                                                  |
|-------------------------------|------------------------------------------------------------------------------|
| `get(name)`                   | Case-insensitive value lookup.                                                |
| `has(name)`                   | Case-insensitive presence check.                                              |
| `find(name)`                  | `{"key", "value"}` dict (or `None`).                                          |
| `idx(n)`                      | Entry at index `n`.                                                           |
| `each(fn)`                    | Iterate `fn(entry)` in insertion order.                                        |
| `all()`                       | `[{"key", "value"}, …]`.                                                      |
| `to_object()` / `toObject()`  | `{key: value}` dict.                                                          |
| `add({"key", "value"})`       | Append (mutable only). Response headers raise.                                |
| `remove(name)`                | Remove all entries with that case-insensitive name.                            |
| `upsert({"key", "value"})`    | Update existing or append.                                                    |
| `headers["Name"]`             | `get(...)` shortcut.                                                          |
| `headers["Name"] = "v"`       | `upsert(...)` shortcut.                                                       |
| `name in headers`             | `has(...)` shortcut.                                                          |
| `len(headers)` / `for h in …` | Length and iteration.                                                          |

### `_PmRequestBody`

| Member       | Description                                                                |
|--------------|----------------------------------------------------------------------------|
| `mode`       | `"raw" \| "urlencoded" \| "formdata" \| "graphql" \| "file" \| ""`.         |
| `raw`        | String body for `mode == "raw"`.                                           |
| `urlencoded` | Mutable `_HeaderList`.                                                     |
| `formdata`   | Mutable `_HeaderList`.                                                     |
| `graphql`    | `{query, variables, operationName}` dict (or `None`).                       |
| `file`       | File spec dict (or `None`).                                                |

```python
if pm.request.body.mode == "urlencoded":
    pm.request.body.urlencoded.upsert({"key": "page", "value": "2"})
```

## `pm.response`

The HTTP response (`None` in pre-request scripts).

| Property                      | Type                | Description                                                                  |
|-------------------------------|---------------------|------------------------------------------------------------------------------|
| `pm.response.code`            | `int`               | HTTP status code.                                                             |
| `pm.response.status`          | `str`               | Status text from host (may differ from canonical reason — see `reason()`).    |
| `pm.response.headers`         | `_HeaderList`       | Response headers (read-only).                                                 |
| `pm.response.response_time`   | `float`             | Elapsed time in ms. Also `pm.response.responseTime` (alias).                  |
| `pm.response.response_size`   | `int`               | Response size in bytes. Also `pm.response.responseSize` (alias).              |
| `pm.response.cookies`         | `_PmCookies`        | Cookies parsed from this response's `Set-Cookie` headers.                     |
| `pm.response.originalRequest` | `_PmRequest \| None`| Wrapped (immutable) request that produced this response.                      |

| Method                        | Returns          | Description                                                                  |
|-------------------------------|------------------|------------------------------------------------------------------------------|
| `json()`                      | `dict \| list`   | Parse body as JSON.                                                           |
| `text()`                      | `str`            | Body as string.                                                               |
| `reason()`                    | `str`            | Canonical HTTP reason phrase for `code` (e.g. `200 → "OK"`).                  |
| `mime()`                      | `dict`           | `{"type", "charset"}` parsed from `Content-Type`.                            |
| `dataURI()`                   | `str`            | Body encoded as `data:<mime>;base64,<...>`.                                  |
| `size()`                      | `int`            | `response_size` if known, otherwise `len(body)`.                              |

```python
def check():
    data = pm.response.json()
    pm.expect(data).to.be.a("dict")
pm.test("JSON response", check)

def reason_check():
    pm.expect(pm.response.reason()).to.equal("OK")
pm.test("Reason phrase", reason_check)
```

## `pm.variables`

**Resolved scope** — reads cascade across every scope; writes land in
local. Read precedence (highest first):
**local → iteration_data → environment → collection_variables → globals**.
This matches Postman's `pm.variables` semantics.

| Method                        | Returns           | Description                                                            |
|-------------------------------|-------------------|------------------------------------------------------------------------|
| `get(key)`                    | `str \| None`     | First-match across scopes.                                              |
| `set(key, value)`             | —                 | Writes to local; subsequent reads see the override.                     |
| `has(key)`                    | `bool`            | Resolves through scopes.                                                |
| `unset(key)`                  | —                 | Removes the local override only.                                         |
| `clear()`                     | —                 | Empties the local layer (does not touch other scopes).                   |
| `to_object()` / `toObject()`  | `dict[str, Any]`  | Merged view across all scopes (last-write-wins, local on top).           |
| `replace_in(t)` / `replaceIn(t)` | `str`         | Substitute `{{var}}` patterns from the merged view.                     |

```python
pm.variables.set("ts", datetime_now())
url = pm.variables.replace_in("{{base_url}}/users")
```

## Single-scope variables

Each scope is a `_VariableScope` exposing
`get/set/has/unset/clear/to_dict/toObject/replace_in/replaceIn`.

| Scope object                 | camelCase alias            | Description                                                        |
|------------------------------|----------------------------|--------------------------------------------------------------------|
| `pm.environment`             | (same)                     | Environment-scoped variables.                                       |
| `pm.collection_variables`    | `pm.collectionVariables`   | Collection-scoped variables.                                        |
| `pm.globals`                 | (same)                     | Global variables persisted to disk across all collections.          |
| `pm.iteration_data`          | `pm.iterationData`         | Read-only data row from the Collection Runner.                      |

## `pm.test(name, fn)`

Register a named test. `fn` may accept zero or one positional argument
— if it accepts one, the runtime passes a context object with a
`.skip()` method. Calling `ctx.skip()` short-circuits the body and
records the test as skipped.

```python
pm.test("Status 200", lambda: pm.expect(pm.response.code).to.equal(200))

def check_body():
    data = pm.response.json()
    pm.expect(data).to.have.property("id")
pm.test("Has ID", check_body)

def maybe_check(ctx):
    if not pm.environment.get("token"):
        ctx.skip()
    pm.expect(pm.environment.get("token")).to.have.length_of.above(0)
pm.test("Token shape", maybe_check)
```

### `pm.test.skip(name, fn)`

Record `name` as skipped without invoking `fn`. Useful for keeping a WIP
assertion in the file without it failing.

```python
pm.test.skip("Body schema (WIP)", lambda: None)
```

## `pm.expect(value)`

Create an assertion chain (Chai BDD-style with Python naming).

### Chainable No-ops

`to`, `be`, `been`, `have`, `has_`, `at`, `of`, `same`, `deep`.

### Negation

`not_` — inverts the next assertion.

```python
pm.expect(404).not_.equal(200)
```

### Assertions

| Method | Description |
|--------|-------------|
| `.equal(val)` | Equality |
| `.eql(val)` / `.deep_equal(val)` | Deep equality (JSON comparison) |
| `.a(type_name)` / `.an(type_name)` | Type check (`"string"`, `"int"`, `"list"`, etc.) |
| `.include(val)` / `.contain(val)` | Substring, element, or key |
| `.has_property(name, [val])` / `.property(name, [val])` | Dict key check |
| `.length_of(n)` | Length assertion |
| `.above(n)` | Greater than |
| `.below(n)` | Less than |
| `.least(n)` | `>=` comparison |
| `.most(n)` | `<=` comparison |
| `.match(pattern)` | Regex match (`re.search`) |
| `.status(code|reason)` | HTTP status code. Accepts numeric (`201`) or canonical reason phrase (`"Created"`). |
| `.header(name, [val])` | Response header check |
| `.body(string|Pattern)` | Response body equals string OR regex `Pattern` matches. |
| `.one_of([...])` / `.oneOf([...])` | Value is `==` to one of the items in the list. |
| `.json_body(path, [val])` / `.jsonBody(...)` | Lodash-style path: `a.b[0].c`. |

### Boolean/Existence Properties

| Property | Description |
|----------|-------------|
| `.true` | Value is `True` |
| `.false` | Value is `False` |
| `.none` | Value is `None` |
| `.exist` | Value is not `None` |
| `.empty` | Length is 0 |

## `pm.cookies`

Cookie jar parsed from response `Set-Cookie` headers.
`pm.response.cookies` is an alias to the same object.

| Method                         | Returns       | Description                                               |
|--------------------------------|---------------|-----------------------------------------------------------|
| `get(name)`                    | `str \| None` | Get cookie value by name.                                  |
| `get_all()` / `getAll()`       | `list[dict]`  | All cookies as `[{"name", "value"}, …]`.                  |
| `jar()`                        | `_CookieJar`  | See below.                                                 |

```python
pm.test("Has session", lambda: pm.expect(pm.cookies.get("sid")).to.exist)
```

### `pm.cookies.jar()`

Postman-style `CookieJar`. Reads work; mutators raise documented errors
pending host-side cookie storage.

| Method                                  | Behaviour                                                                                  |
|-----------------------------------------|--------------------------------------------------------------------------------------------|
| `get(url, name[, callback])`            | Returns the cookie value parsed from this response's `Set-Cookie`. Optional callback fires.|
| `getAll(url[, callback])`               | Returns all known cookies for this response.                                                |
| `set(...)`                              | Raises `RuntimeError("pm.cookies.jar().set is not yet supported in postmark")`.             |
| `unset(...)`                            | Raises with the analogous error.                                                             |
| `clear(...)`                            | Raises with the analogous error.                                                             |

## `pm.send_request(spec, callback=None)` / `pm.sendRequest(...)`

Send an HTTP sub-request. Synchronous — returns a wrapped `_PmResponse`
with the same shape as `pm.response` (so `.code`, `.json()`,
`.headers.get(...)`, `.text()`, `.reason()`, `.mime()` etc. all work
identically).

> **No `await`:** pyodide and the RestrictedPython subprocess have no
> event loop. The call returns immediately with the response. Don't
> wrap it in `await` — that's a JS-only path.

| Parameter | Type             | Description                                                 |
|-----------|------------------|-------------------------------------------------------------|
| `spec`    | `str \| dict`    | URL string or request spec dict.                            |
| `callback`| callable         | Optional `fn(err, response)` — fires synchronously with the wrapped `_PmResponse`. |

**Spec dict fields:** `url`, `method`, `header`/`headers`, `body`.

**Limits:** 10 calls per execution, http/https only, 10 s timeout.

```python
resp = pm.send_request("https://api.example.com/token")
pm.environment.set("token", resp.json()["token"])

# Callback form (Postman parity):
def on_response(err, resp):
    if not err:
        pm.environment.set("token", resp.json()["token"])
pm.send_request("https://api.example.com/token", on_response)
```

## `pm.execution`

Runner flow control — available in both pre-request and test scripts.
Both snake_case (Pythonic) and camelCase (Postman) names work.

| Member                                                  | Description                                                       |
|---------------------------------------------------------|-------------------------------------------------------------------|
| `set_next_request(name)` / `setNextRequest(name)`       | Override the next request in the collection runner.               |
| `skip_request()` / `skipRequest()`                      | Skip the current request's HTTP send.                              |
| `location.current`                                       | Folder/collection path of the current request (string).            |

`set_next_request(name)` sets the next request to execute by name.
Pass `None` to stop the runner after the current request.  Only
effective inside the Collection Runner — ignored for single sends.

`skip_request()` prevents the HTTP request from being sent.

```python
# Pre-request: conditionally skip
if pm.info.request_name.startswith("DRAFT"):
    pm.execution.skip_request()

# Test: chain to another request
pm.test("Chain on 401", lambda: (
    pm.execution.set_next_request("Login")
    if pm.response.code == 401
    else None
))
```

## `pm.iteration_data` / `pm.iterationData`

Data-driven iteration row — populated when the Collection Runner is
configured with a CSV or JSON data file. The camelCase alias
`pm.iterationData` is the same object.

| Method                          | Returns       | Description                                       |
|---------------------------------|---------------|---------------------------------------------------|
| `get(key)`                      | `str \| None` | Get value by column/key name.                      |
| `to_object()` / `toObject()`    | `dict`        | All row data as a dict.                           |
| `has(key)`                      | `bool`        | Check if key exists in current row.                |

```python
user_id = pm.iteration_data.get("user_id")
pm.request.url = pm.variables.replace_in("{{base_url}}/users/") + user_id
```

## `pm.require(spec)`

Postman-style module loader. Bare specifiers map to known vendor
names; otherwise falls through to `importlib.import_module`. Useful
when porting JS scripts that call `pm.require("crypto-js")` etc. —
reads succeed if the package is present in the sandbox; otherwise a
`RuntimeError` with the failed candidates list is raised.

```python
moment = pm.require("moment")          # if installed in pyodide
chai = pm.require("chai")              # likewise
```

## `pm.visualizer.set(template, data, options=None)` — not supported

Always raises:

```text
pm.visualizer.set is not supported in postmark —
see data/snippets/README.md (Out of scope) for the rationale.
```

The explicit raise (rather than a no-op) makes it obvious to users that
the call did nothing and prompts them to remove or replace it.

## Legacy v1 globals

These exist as top-level names (no `pm.` prefix) for compatibility with
very old Postman scripts. New code should use the modern `pm.*` API.

| Global             | Type                                       | Maps to                                                |
|--------------------|--------------------------------------------|---------------------------------------------------------|
| `responseBody`     | `str`                                      | `pm.response.text()` (or `""` in pre-request).          |
| `responseCode`     | `dict` `{"code", "name"}`                  | `{"code": pm.response.code, "name": pm.response.reason()}`. |
| `responseHeaders`  | `dict[str, str]`                           | `pm.response.headers.to_object()`.                      |
| `tests`            | `dict`                                     | Postman v1 — assignments here are picked up by old runners. |
| `xml2Json(xml)`    | `function(str) -> dict \| None`            | XML → nested dict via stdlib `xml.etree.ElementTree`.   |
| `postman`          | object (see below)                         | Postman v1 helper namespace.                             |

### Postman v1 `postman.*` shim

| Method                             | Maps to                                       |
|------------------------------------|-----------------------------------------------|
| `setEnvironmentVariable(key, val)` | `pm.environment.set(key, str(val))`           |
| `getEnvironmentVariable(key)`      | `pm.environment.get(key)`                     |
| `clearEnvironmentVariable(key)`    | `pm.environment.unset(key)`                   |
| `setGlobalVariable(key, val)`      | `pm.globals.set(key, str(val))`               |
| `getGlobalVariable(key)`           | `pm.globals.get(key)`                         |
| `clearGlobalVariable(key)`         | `pm.globals.unset(key)`                       |
| `setNextRequest(name)`             | `pm.execution.set_next_request(name)`         |

```python
# Legacy v1 — works, but prefer the pm.* form below.
postman.setEnvironmentVariable("token", responseBody)

# Modern equivalent:
pm.environment.set("token", pm.response.text())
```

## Available Standard Library

Scripts cannot use `import`.  Instead, pre-imported functions are
available as top-level names:

| Name | From | Description |
|------|------|-------------|
| `json_loads(s)` | `json` | Parse JSON string |
| `json_dumps(obj)` | `json` | Serialize to JSON string |
| `re_match(pattern, s)` | `re` | Match at start |
| `re_search(pattern, s)` | `re` | Search anywhere |
| `re_findall(pattern, s)` | `re` | Find all matches |
| `re_sub(pattern, repl, s)` | `re` | Regex replace |
| `math_ceil(x)` | `math` | Ceiling |
| `math_floor(x)` | `math` | Floor |
| `math_sqrt(x)` | `math` | Square root |
| `math_pow(x, y)` | `math` | Power |
| `math_log(x)` | `math` | Natural log |
| `math_pi` | `math` | Pi constant |
| `math_e` | `math` | Euler's number |
| `b64encode(data)` | `base64` | Base64 encode |
| `b64decode(data)` | `base64` | Base64 decode |
| `hashlib_md5(data)` | `hashlib` | MD5 hex digest |
| `hashlib_sha256(data)` | `hashlib` | SHA-256 hex digest |
| `hashlib_hmac_sha256(data, key)` | `hmac` | HMAC-SHA256 hex digest |
| `uuid_v4()` | `uuid` | Random UUID v4 string |
| `datetime_now()` | `datetime` | Current UTC ISO timestamp |
| `datetime_utcnow()` | `datetime` | Alias for `datetime_now()` |
| `url_quote(s)` | `urllib.parse` | URL-encode string |
| `url_urlencode(d)` | `urllib.parse` | URL-encode dict |

## `print()`

`print()` output is captured and routed to the Console panel as
`console.log` messages.  Rate-limited to 200 messages per execution.

```python
print("Request URL:", pm.request.url)
print("Response:", pm.response.code)
```

## Exception types

For Postman parity, common exception classes are exposed as builtins so
`try/except` works without imports:

`Exception`, `ValueError`, `RuntimeError`, `KeyError`, `TypeError`,
`IndexError`, `AssertionError`, `AttributeError`.

```python
try:
    data = pm.response.json()
except ValueError:
    pm.test("Body is JSON", lambda: pm.expect(False).to.be.true)
```

## Blocked Operations

The following are blocked by RestrictedPython and the restricted
builtins whitelist:

- `import` statements
- `open()`, `exec()`, `eval()`, `__import__()`
- `getattr()` on `_`-prefixed attributes
- File I/O, network I/O, OS access
- `subprocess`, `os`, `sys` module access
