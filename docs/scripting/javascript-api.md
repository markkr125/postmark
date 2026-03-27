# JavaScript API Reference

Complete reference for the `pm` object available in JavaScript scripts.

## `pm.info`

Read-only execution metadata.

| Property | Type | Description |
|----------|------|-------------|
| `requestName` | `string` | Name of the current request |
| `requestId` | `string` | Database ID of the current request |
| `iteration` | `number` | Current iteration index (runner only) |
| `iterationCount` | `number` | Total iterations (runner only) |

```javascript
console.log("Running: " + pm.info.requestName);
```

## `pm.request`

The current HTTP request.  **Mutable in pre-request scripts** — changes
are applied before sending.  **Frozen in test scripts.**

| Property | Type | Mutable | Description |
|----------|------|---------|-------------|
| `url` | `string` | pre-request | Full request URL |
| `method` | `string` | pre-request | HTTP method |
| `headers` | `HeaderList` | pre-request | Request headers |
| `body` | `string` | pre-request | Request body text |

### HeaderList Methods

| Method | Description |
|--------|-------------|
| `headers.get(name)` | Get header value (case-insensitive) |
| `headers.has(name)` | Check if header exists |
| `headers.toObject()` | Convert to `{key: value}` object |
| `headers.add({key, value})` | Add header (pre-request only) |
| `headers.remove(name)` | Remove header (pre-request only) |
| `headers.upsert({key, value})` | Add or update header (pre-request only) |

```javascript
// Pre-request: add auth header
pm.request.headers.upsert({
    key: "Authorization",
    value: "Bearer " + pm.variables.get("token")
});
```

## `pm.response`

The HTTP response (available in test scripts only; `null` in
pre-request).

| Property | Type | Description |
|----------|------|-------------|
| `code` | `number` | HTTP status code |
| `status` | `string` | Status text |
| `headers` | `HeaderList` | Response headers (read-only) |
| `responseTime` | `number` | Elapsed time in ms |
| `responseSize` | `number` | Response size in bytes |
| `body` | `string` | Raw response body |

| Method | Returns | Description |
|--------|---------|-------------|
| `json()` | `object` | Parse body as JSON |
| `text()` | `string` | Body as string |

```javascript
pm.test("Response is JSON", function() {
    var data = pm.response.json();
    pm.expect(data).to.be.an("object");
});
```

## `pm.variables`

Current-scope variables (merged collection + environment + local).

| Method | Returns | Description |
|--------|---------|-------------|
| `get(key)` | `string \| undefined` | Get variable value |
| `set(key, value)` | — | Set variable (persists as local override) |
| `has(key)` | `boolean` | Check if variable exists |
| `unset(key)` | — | Remove variable |
| `toObject()` | `object` | All variables as `{key: value}` |
| `replaceIn(template)` | `string` | Substitute `{{var}}` patterns |

```javascript
pm.variables.set("timestamp", Date.now().toString());
var url = pm.variables.replaceIn("{{base_url}}/users");
```

## `pm.environment`

Environment-scoped variables only.  Same methods as `pm.variables`.

## `pm.collectionVariables`

Collection-scoped variables only.  Same methods as `pm.variables`.

## `pm.globals`

Global variables persisted to disk across all collections and sessions.
Same methods as `pm.variables`.

## `pm.test(name, fn)`

Register a named test assertion.  `fn` is called immediately — if it
throws, the test is marked as failed.

```javascript
pm.test("Status code is 200", function() {
    pm.expect(pm.response.code).to.equal(200);
});
```

## `pm.expect(value)`

Create a Chai BDD-style assertion chain.

### Chainable No-ops

These words exist only for readability and do nothing:
`to`, `be`, `been`, `is`, `that`, `which`, `and`, `has`, `have`,
`with`, `at`, `of`, `same`, `but`, `does`, `deep`.

### Negation

`.not` — inverts the next assertion.

```javascript
pm.expect(404).to.not.equal(200);
```

### Assertions

| Method | Description |
|--------|-------------|
| `.equal(val)` | Strict equality (`===`) |
| `.eql(val)` | Deep equality (JSON comparison) |
| `.a(type)` / `.an(type)` | Type check (`typeof` or `"array"`) |
| `.include(val)` | Substring, array element, or object key |
| `.property(name, [val])` | Own property check, optional value |
| `.lengthOf(n)` | `.length === n` |
| `.above(n)` | Greater than |
| `.below(n)` | Less than |
| `.least(n)` | Greater than or equal (`>=`) |
| `.most(n)` | Less than or equal (`<=`) |
| `.match(regex)` | RegExp test |
| `.status(code)` | HTTP status code assertion |
| `.header(name, [val])` | Response header assertion |
| `.jsonBody(path, [val])` | JSONPath dot-notation assertion |

### Boolean/Existence Properties

| Property | Description |
|----------|-------------|
| `.true` | Value is `true` |
| `.false` | Value is `false` |
| `.null` | Value is `null` |
| `.undefined` | Value is `undefined` |
| `.NaN` | Value is `NaN` |
| `.exist` | Value is not `null` and not `undefined` |
| `.empty` | String/array length is 0, or object has no keys |

### Examples

```javascript
pm.expect(pm.response.code).to.equal(200);
pm.expect(data).to.have.property("id");
pm.expect(data.items).to.have.lengthOf(10);
pm.expect(data.name).to.be.a("string");
pm.expect(pm.response).to.have.status(201);
pm.expect(pm.response).to.have.header("Content-Type", "application/json");
```

## `pm.sendRequest(spec, callback)`

Send an HTTP sub-request from within a script.  The request is executed
by the host process (not the V8 isolate), so network access is
controlled and rate-limited.

| Parameter | Type | Description |
|-----------|------|-------------|
| `spec` | `string \| object` | URL string or request spec object |
| `callback` | `function(err, response)` | Called with the result |

**Spec object fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `string` | — | Target URL (http/https only) |
| `method` | `string` | `"GET"` | HTTP method |
| `header` | `[{key, value}]` | `[]` | Request headers |
| `body` | `string \| {mode, raw}` | — | Request body |

**Limits:** 10 calls per script execution, http/https only, 10 s
timeout per sub-request.

```javascript
pm.sendRequest("https://api.example.com/token", function(err, response) {
    if (!err) {
        pm.variables.set("token", response.json().token);
    }
});
```

## `pm.cookies`

Cookie jar parsed from response `Set-Cookie` headers.

| Method | Returns | Description |
|--------|---------|-------------|
| `get(name)` | `string \| undefined` | Get cookie value by name |
| `getAll()` | `[{name, value}]` | All parsed cookies |

```javascript
pm.test("Session cookie set", function() {
    pm.expect(pm.cookies.get("session_id")).to.exist;
});
```

## `pm.execution`

Runner flow control — available in both pre-request and test scripts.

| Method | Description |
|--------|-------------|
| `setNextRequest(name)` | Override the next request in the collection runner |
| `skipRequest()` | Skip the current request's HTTP send |

`setNextRequest(name)` sets the next request to execute by name.  Pass
`null` to stop the runner after the current request.  Only effective
inside the Collection Runner — ignored for single-request sends.

`skipRequest()` prevents the HTTP request from being sent.  The result
is recorded with status `0` and marked as skipped.

```javascript
// Pre-request: skip requests that are drafts
if (pm.info.requestName.startsWith("DRAFT")) {
    pm.execution.skipRequest();
}

// Test: jump to a specific request
pm.test("Chain to login", function() {
    if (pm.response.code === 401) {
        pm.execution.setNextRequest("Login");
    }
});
```

## `pm.iterationData`

Data-driven iteration row — populated when the Collection Runner is
configured with a CSV or JSON data file.

| Method | Returns | Description |
|--------|---------|-------------|
| `get(key)` | `any` | Get value by column/key name |
| `toObject()` | `object` | All row data as a plain object |
| `has(key)` | `boolean` | Check if key exists in current row |

```javascript
// Use iteration data for parameterised requests
var userId = pm.iterationData.get("user_id");
pm.request.url = pm.variables.replaceIn("{{base_url}}/users/") + userId;
```

## `console`

Console output captured and routed to the Console panel.  Rate-limited
to 200 messages per script execution.

| Method | Description |
|--------|-------------|
| `console.log(...)` | Log message |
| `console.warn(...)` | Warning message |
| `console.error(...)` | Error message |
| `console.info(...)` | Info message |

```javascript
console.log("Request URL:", pm.request.url);
console.warn("Slow response:", pm.response.responseTime, "ms");
```
