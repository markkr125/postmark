# Python API Reference

Complete reference for the `pm` object available in Python scripts.
Python scripts use Pythonic naming (`snake_case`) and RestrictedPython
compilation.

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

| Property | Type | Mutable | Description |
|----------|------|---------|-------------|
| `pm.request.url` | `str` | pre-request | Full request URL |
| `pm.request.method` | `str` | pre-request | HTTP method |
| `pm.request.headers` | `dict[str, str]` | pre-request | Headers dictionary |
| `pm.request.body` | `str` | pre-request | Request body |

```python
# Pre-request: set auth header
pm.request.headers["Authorization"] = "Bearer " + pm.variables.get("token")
```

## `pm.response`

The HTTP response (`None` in pre-request scripts).

| Property | Type | Description |
|----------|------|-------------|
| `pm.response.code` | `int` | HTTP status code |
| `pm.response.status` | `str` | Status text |
| `pm.response.headers` | `dict[str, str]` | Response headers |
| `pm.response.response_time` | `float` | Elapsed time in ms |
| `pm.response.response_size` | `int` | Response size in bytes |

| Method | Returns | Description |
|--------|---------|-------------|
| `json()` | `dict \| list` | Parse body as JSON |
| `text()` | `str` | Body as string |

```python
pm.test("JSON response", lambda: pm.expect(pm.response.json()).to.be.a("dict"))
```

## `pm.variables`

Current-scope variables.

| Method | Returns | Description |
|--------|---------|-------------|
| `get(key)` | `str \| None` | Get variable value |
| `set(key, value)` | — | Set variable |
| `has(key)` | `bool` | Check if variable exists |
| `unset(key)` | — | Remove variable |
| `to_dict()` | `dict[str, str]` | All variables as dict |
| `replace_in(template)` | `str` | Substitute `{{var}}` patterns |

```python
pm.variables.set("ts", datetime_now())
url = pm.variables.replace_in("{{base_url}}/users")
```

## `pm.environment`

Environment-scoped variables.  Same methods as `pm.variables`.

## `pm.collection_variables`

Collection-scoped variables.  Same methods as `pm.variables`.

## `pm.globals`

Global variables persisted to disk across all collections and sessions.
Same methods as `pm.variables`.

## `pm.test(name, fn)`

Register a named test.  `fn` is a no-arg callable — exceptions mark
the test as failed.

```python
pm.test("Status 200", lambda: pm.expect(pm.response.code).to.equal(200))

def check_body():
    data = pm.response.json()
    pm.expect(data).to.have.property("id")
pm.test("Has ID", check_body)
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
| `.status(code)` | HTTP status code |
| `.header(name, [val])` | Response header check |

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

| Method | Returns | Description |
|--------|---------|-------------|
| `get(name)` | `str \| None` | Get cookie value by name |
| `get_all()` | `list[dict]` | All cookies as `[{"name": ..., "value": ...}]` |

```python
pm.test("Has session", lambda: pm.expect(pm.cookies.get("sid")).to.exist)
```

## `pm.send_request(spec, callback=None)`

Send an HTTP sub-request from within a script.  Communication uses
IPC — the sandbox subprocess has no direct network access.

| Parameter | Type | Description |
|-----------|------|-------------|
| `spec` | `str \| dict` | URL string or request spec dict |
| `callback` | callable | Optional `fn(err, response)` callback |

**Spec dict fields:** `url`, `method`, `header`/`headers`, `body`.

**Limits:** 10 calls per execution, http/https only, 10 s timeout.

```python
pm.send_request("https://api.example.com/token", lambda err, resp: (
    pm.variables.set("token", resp["body"]) if not err else None
))
```

## `pm.execution`

Runner flow control — available in both pre-request and test scripts.

| Method | Description |
|--------|-------------|
| `set_next_request(name)` | Override the next request in the collection runner |
| `skip_request()` | Skip the current request's HTTP send |

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

## `pm.iteration_data`

Data-driven iteration row — populated when the Collection Runner is
configured with a CSV or JSON data file.

| Method | Returns | Description |
|--------|---------|-------------|
| `get(key)` | `str \| None` | Get value by column/key name |
| `to_object()` | `dict` | All row data as a dict |
| `has(key)` | `bool` | Check if key exists in current row |

```python
user_id = pm.iteration_data.get("user_id")
pm.request.url = pm.variables.replace_in("{{base_url}}/users/") + user_id
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

## Blocked Operations

The following are blocked by RestrictedPython and the restricted
builtins whitelist:

- `import` statements
- `open()`, `exec()`, `eval()`, `__import__()`
- `getattr()` on `_`-prefixed attributes
- File I/O, network I/O, OS access
- `subprocess`, `os`, `sys` module access
