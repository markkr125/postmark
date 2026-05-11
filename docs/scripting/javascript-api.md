# JavaScript API Reference

Complete reference for the `pm` object available in JavaScript and
TypeScript scripts. Postmark's surface tracks the official Postman
sandbox API — see [Postman API parity](postman-parity.md) for the full
matrix and migration notes.

> Inserted at the cursor by the [Snippets](snippets.md) palette.

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

| Property | Type           | Mutable     | Description                                                            |
|----------|----------------|-------------|------------------------------------------------------------------------|
| `url`    | `Url`          | pre-request | Wrapped Postman `Url` object (see below). String-coerces to full URL.  |
| `method` | `string`       | pre-request | HTTP method.                                                            |
| `headers`| `HeaderList`   | pre-request | Request headers (see below).                                            |
| `body`   | `RequestBody`  | pre-request | Discriminated union — `mode/raw/urlencoded/formdata/graphql/file`.      |

### `Url` (`pm.request.url`)

| Member             | Description                                                                            |
|--------------------|----------------------------------------------------------------------------------------|
| `toString()`       | Full URL string. The object string-coerces to this in template literals.                |
| `getHost()`        | Hostname (no port).                                                                     |
| `getPath()`        | Pathname.                                                                               |
| `getQueryString()` | Raw query string (no leading `?`).                                                      |
| `protocol`         | Scheme without trailing `:`.                                                             |
| `host`             | Same as `getHost()`.                                                                     |
| `port`             | String port (or empty when default).                                                     |
| `path`             | Same as `getPath()`.                                                                     |
| `query`            | Mutable `HeaderList` of query params. `query.add({key, value})`, `query.toObject()`, … |

```javascript
const u = pm.request.url;
console.log(u.getHost());                           // "api.example.com"
u.query.upsert({ key: "page", value: "2" });
console.log(u.toString());                          // includes ?page=2
```

### `HeaderList` Methods

Used for `pm.request.headers`, `pm.response.headers`, plus
`body.urlencoded` and `body.formdata`. Case-insensitive lookups; ordered
iteration; mutation gated by source (response headers raise on writes).

| Method                       | Description                                                                  |
|------------------------------|------------------------------------------------------------------------------|
| `get(name)`                  | Case-insensitive value lookup.                                                |
| `has(name)`                  | Case-insensitive presence check.                                              |
| `find(name)`                 | Returns `{key, value}` (or `undefined`).                                      |
| `idx(n)`                     | Entry at index `n`.                                                           |
| `each(fn)`                   | Iterate `(entry) => void` in insertion order.                                 |
| `all()`                      | `[{key, value}, …]`.                                                          |
| `toObject()`                 | `{key: value}` (last-write-wins on duplicates).                               |
| `add({key, value})`          | Append (mutable only). Response headers raise.                                |
| `remove(name)`               | Remove all entries with that case-insensitive name (mutable only).            |
| `upsert({key, value})`       | Update existing or append (mutable only).                                     |

```javascript
// Pre-request: add auth header
pm.request.headers.upsert({
    key: "Authorization",
    value: "Bearer " + pm.variables.get("token")
});
```

### `RequestBody` (`pm.request.body`)

| Member        | Description                                                                |
|---------------|----------------------------------------------------------------------------|
| `mode`        | `"raw" \| "urlencoded" \| "formdata" \| "graphql" \| "file" \| ""`.         |
| `raw`         | String body for `mode === "raw"`.                                          |
| `urlencoded`  | Mutable `HeaderList` of form fields.                                       |
| `formdata`    | Mutable `HeaderList` of multipart fields.                                  |
| `graphql`     | `{query, variables, operationName}` object (or `null`).                     |
| `file`        | File spec object (or `null`).                                              |
| `toString()`  | Returns `raw` (so string concatenation still works).                        |

```javascript
if (pm.request.body.mode === "urlencoded") {
    pm.request.body.urlencoded.upsert({ key: "page", value: "2" });
}
```

## `pm.response`

The HTTP response (available in test scripts only; `null` in
pre-request).

| Property              | Type             | Description                                                                  |
|-----------------------|------------------|------------------------------------------------------------------------------|
| `code`                | `number`         | HTTP status code.                                                             |
| `status`              | `string`         | Status text from host (may differ from canonical reason — see `reason()`).    |
| `headers`             | `HeaderList`     | Response headers (read-only).                                                 |
| `responseTime`        | `number`         | Elapsed time in ms.                                                           |
| `responseSize`        | `number`         | Response size in bytes.                                                       |
| `body`                | `string`         | Raw response body.                                                            |
| `cookies`             | `pm.cookies`-shape| Cookies parsed from this response's `Set-Cookie` headers.                    |
| `originalRequest`     | `Request`        | Wrapped (immutable) request that produced this response.                      |

| Method                | Returns          | Description                                                                  |
|-----------------------|------------------|------------------------------------------------------------------------------|
| `json()`              | `object`         | Parse body as JSON. (`reviver` parameter is ignored.)                         |
| `text()`              | `string`         | Body as string.                                                               |
| `reason()`            | `string`         | Canonical HTTP reason phrase for `code` (e.g. `200 → "OK"`).                  |
| `mime()`              | `{type, charset}`| Parse `Content-Type` into a `{type, charset}` object.                         |
| `dataURI()`           | `string`         | Body encoded as `data:<mime>;base64,<...>`.                                  |
| `size()`              | `number`         | `responseSize` if known, otherwise `body.length`.                            |

```javascript
pm.test("Response is JSON", function() {
    const data = pm.response.json();
    pm.expect(data).to.be.an("object");
});

pm.test("Reason phrase", function() {
    pm.expect(pm.response.reason()).to.equal("OK");
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

The callback receives a context object with a `.skip()` method. Calling
`ctx.skip()` short-circuits the body and records the test as skipped.

```javascript
pm.test("Status code is 200", function() {
    pm.expect(pm.response.code).to.equal(200);
});

pm.test("Skip when no token", function(ctx) {
    if (!pm.environment.get("token")) {
        ctx.skip();
    }
    pm.expect(pm.environment.get("token")).to.have.lengthOf.above(0);
});
```

### `pm.test.skip(name, fn)`

Record a named test as skipped without invoking `fn`. Use to keep a WIP
test in the file without it failing.

```javascript
pm.test.skip("Body schema (WIP)", function() {
    // Will not run; recorded as { skipped: true, passed: true }.
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
| `.status(code|reason)` | HTTP status code assertion. Accepts numeric (`201`) or canonical reason phrase (`"Created"`). |
| `.header(name, [val])` | Response header assertion |
| `.body(string|RegExp)` | Response body equals string OR regex matches. |
| `.oneOf([...])` | Value is `===` to one of the items in the array. |
| `.jsonBody(path, [val])` | Lodash-style path assertion. Supports dot + bracket: `a.b[0].c`. |

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

Cookie jar parsed from response `Set-Cookie` headers. `pm.response.cookies`
is an alias to the same object.

| Method | Returns | Description |
|--------|---------|-------------|
| `get(name)` | `string \| undefined` | Get cookie value by name |
| `getAll()` | `[{name, value}]` | All parsed cookies |
| `jar()` | `CookieJar` | See below |

```javascript
pm.test("Session cookie set", function() {
    pm.expect(pm.cookies.get("session_id")).to.exist;
});
```

### `pm.cookies.jar()`

Returns a Postman-style `CookieJar`. **Read-only in v1** — read paths
work; mutation methods raise a documented error pending host-side
cookie storage.

| Method                          | Behaviour                                                                              |
|---------------------------------|----------------------------------------------------------------------------------------|
| `get(url, name[, callback])`    | Returns the cookie value parsed from this response's `Set-Cookie`. Optional callback fires. |
| `getAll(url[, callback])`       | Returns all known cookies for this response.                                            |
| `set(...)`                      | Throws `Error("pm.cookies.jar().set is not yet supported in postmark")`.                |
| `unset(...)`                    | Throws with the analogous error.                                                         |
| `clear(...)`                    | Throws with the analogous error.                                                         |

The `url` argument is currently ignored — there is no host-side cookie
jar to scope by domain/path. Reads return cookies parsed from this
response only.

## `pm.execution`

Runner flow control — available in both pre-request and test scripts.

| Member                                | Description                                                                  |
|---------------------------------------|------------------------------------------------------------------------------|
| `setNextRequest(name)`                | Override the next request in the collection runner.                          |
| `skipRequest()`                       | Skip the current request's HTTP send.                                         |
| `location.current`                    | Folder/collection path of the current request (string).                       |

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

## Built-in Libraries

JavaScript scripts can load the following built-in libraries with
`require()`.  These are bundled with Postmark and loaded lazily — only
when your script references them.

### CryptoJS

Full `crypto-js` 4.2.0 library for hashing, encryption, and encoding.

```javascript
var CryptoJS = require("crypto-js");

// Hashing
var hash = CryptoJS.SHA256("hello world").toString();
var hmac = CryptoJS.HmacSHA256("message", "secret").toString();

// AES encryption / decryption
var encrypted = CryptoJS.AES.encrypt("data", "password").toString();
var decrypted = CryptoJS.AES.decrypt(encrypted, "password")
    .toString(CryptoJS.enc.Utf8);

// MD5, SHA1, SHA512, etc.
var md5 = CryptoJS.MD5("text").toString();
```

> **Tip:** `CryptoJS` is also available as a global — you can use it
> without `require()` if your script references the `CryptoJS` name.

### Lodash

`lodash` 4.17.23 — utility library for arrays, objects, strings.

```javascript
var _ = require("lodash");

var unique = _.uniq([1, 2, 2, 3]);
var grouped = _.groupBy(data, "category");
var picked = _.pick(obj, ["id", "name"]);
```

### Moment

`moment` 2.30.1 — date parsing, formatting, and manipulation.

```javascript
var moment = require("moment");

var now = moment().format("YYYY-MM-DD");
var iso = moment().toISOString();
var diff = moment("2025-01-01").diff(moment(), "days");
```

### Chai

`chai` 4.5.0 — BDD/TDD assertion library.  The built-in
`pm.expect()` already provides Chai-style assertions, but you can use
the full Chai API directly if needed.

```javascript
var chai = require("chai");
var expect = chai.expect;

expect([1, 2, 3]).to.have.lengthOf(3);
expect({ a: 1 }).to.have.property("a", 1);
```

### tv4

`tv4` 1.3.0 — JSON Schema validation (Draft 4).

```javascript
var tv4 = require("tv4");

var schema = {
    type: "object",
    properties: { id: { type: "number" }, name: { type: "string" } },
    required: ["id", "name"]
};

pm.test("Response matches schema", function() {
    var result = tv4.validate(pm.response.json(), schema);
    pm.expect(result).to.be.true;
});
```

### Ajv

`ajv` 8.18.0 — JSON Schema validator (Drafts 4/6/7/2019-09/2020-12).

```javascript
var Ajv = require("ajv");
var ajv = new Ajv();

var schema = {
    type: "object",
    properties: { email: { type: "string", format: "email" } },
    required: ["email"]
};

pm.test("Valid schema", function() {
    var validate = ajv.compile(schema);
    pm.expect(validate(pm.response.json())).to.be.true;
});
```

### xml2js

`xml2js` 0.6.2 — XML to JavaScript object converter.

```javascript
var xml2js = require("xml2js");

var xml = pm.response.text();
xml2js.parseString(xml, function(err, result) {
    if (!err) {
        pm.variables.set("title", result.root.title[0]);
    }
});
```

### csv-parse/sync

`csv-parse` 5.6.0 — synchronous CSV parser.

```javascript
var parse = require("csv-parse/sync").parse;

var records = parse(pm.response.text(), {
    columns: true,
    skip_empty_lines: true
});
pm.variables.set("row_count", records.length.toString());
```

### uuid

UUID v4 generation (built into the bootstrap — no vendor file needed).

```javascript
var uuid = require("uuid");

var id = uuid.v4();
pm.variables.set("request_id", id);
```

## `pm.require(spec)`

Postman-style module loader. Bare specifiers map to bundled vendor
modules (`crypto-js`, `lodash`, `moment`, `chai`, `tv4`, `ajv`,
`xml2js`, `csv-parse/lib/sync`, `cheerio`, `atob`, `btoa`, `uuid`).

```javascript
const _ = pm.require("lodash");
const tv4 = pm.require("tv4");
```

JS scripts running under Deno can additionally use `npm:` and `jsr:`
prefixed specifiers — these are resolved through Deno's import system
during the bundle build.

The companion global `require()` works for the same vendor names if
your script prefers Node-style.

## `pm.visualizer.set(template, data, options)` — not supported

Always throws:

```text
pm.visualizer.set is not supported in postmark —
see data/snippets/README.md (Out of scope) for the rationale.
```

The explicit raise (rather than a no-op) makes it obvious to users that
the call did nothing and prompts them to remove or replace it.

## Legacy v1 globals

These exist as top-level names (no `pm.` prefix) for compatibility with
very old Postman scripts. New code should use the modern `pm.*` API.

| Global             | Type                                  | Maps to                                                |
|--------------------|---------------------------------------|---------------------------------------------------------|
| `responseBody`     | `string`                              | `pm.response.body`.                                     |
| `responseCode`     | `{code, name}` object                 | `{code: pm.response.code, name: pm.response.reason()}`. |
| `responseHeaders`  | `{key: value}` object                 | `pm.response.headers.toObject()`.                       |
| `tests`            | `{}` mutable object                   | Postman v1 — assignments here are picked up by old runners. |
| `xml2Json(xml)`    | `function(string) -> object \| null`  | XML → object via `pm.require("xml2js")` internally.     |
| `postman.*`        | object                                | `setEnvironmentVariable` / `getEnvironmentVariable` / `clearEnvironmentVariable` / `setGlobalVariable` / `getGlobalVariable` / `clearGlobalVariable` / `setNextRequest`. |

```javascript
// Legacy v1 — works, but prefer the pm.* form below.
postman.setEnvironmentVariable("token", responseBody);

// Modern equivalent:
pm.environment.set("token", pm.response.text());
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
