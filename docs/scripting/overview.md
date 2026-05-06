# Scripting Overview

Postmark supports pre-request and test scripts in both JavaScript and
Python.  Scripts automate request setup, validate responses, and chain
API calls — turning Postmark from an HTTP client into a full API testing
tool.

## Script Types

### Pre-request Scripts

Run **before** the HTTP request is sent.  Use cases:

- Mutate the request: URL, method, headers, body.
- Set variables for dynamic values (timestamps, tokens, UUIDs).
- Chain requests (fetch a token, then use it in the main request).

### Test Scripts (Post-response)

Run **after** the response is received.  Use cases:

- Assert status codes, headers, body content.
- Parse JSON response and validate structure.
- Set variables for downstream requests.

## Execution Order (Inheritance)

Scripts are inherited from parent collections and folders.  Execution
follows a deterministic order:

```text
Pre-request:  Collection --> Folder(s) --> Request   (top-down)
HTTP request:            ---- send ----
Test:         Request --> Folder(s) --> Collection   (bottom-up)
```

A request inside `Collection > Folder A > Folder B` runs:

```text
1. Collection pre-request script
2. Folder A pre-request script
3. Folder B pre-request script
4. Request pre-request script
5. --- HTTP request sent ---
6. Request test script
7. Folder B test script
8. Folder A test script
9. Collection test script
```

Variable changes from earlier scripts propagate to later ones in the
chain.  A collection-level pre-request script that sets `{{token}}`
makes it available in every downstream script.

## Language Support

| Language | Runtime | Default | Sandbox |
|----------|---------|---------|---------|
| JavaScript | Deno subprocess (`deno run`, bundled bootstrap + user script) | Yes | `deno run` with scoped `--allow-read` to the temp workdir; 10 s process timeout |
| Python | Pyodide (Deno + WASM) when vendored assets and Deno are available; otherwise RestrictedPython subprocess | No | Deno permissions + WASM, or process isolation (5 s CPU, 128 MB) |

JavaScript is the default because most existing Postman collections use
it.  Python is opt-in via the language selector in the Scripts tab.

Both languages provide the same `pm.*` API surface (with Pythonic naming
in the Python variant — `pm.collection_variables` instead of
`pm.collectionVariables`).

## Quick Start

### JavaScript test script

```javascript
pm.test("Status is 200", function() {
    pm.expect(pm.response.code).to.equal(200);
});

pm.test("Body contains user", function() {
    var body = pm.response.json();
    pm.expect(body).to.have.property("name");
    pm.expect(body.name).to.be.a("string");
});
```

### Python test script

```python
pm.test("Status is 200",
    lambda: pm.expect(pm.response.code).to.equal(200))

def check_body():
    body = pm.response.json()
    pm.expect(body).to.have.property("name")
    pm.expect(body["name"]).to.be.a("string")

pm.test("Body contains user", check_body)
```

## Security Model

Scripts run in sandboxed environments with no filesystem, network, or
OS access.  See [Security](security.md) for the full threat model,
resource limits, and sandbox architecture.

## Feature Parity: JavaScript vs Python

Both languages provide the same `pm.*` API surface.  However,
JavaScript has access to bundled third-party libraries via `require()`,
while Python provides built-in stdlib functions.

### Shared capabilities (both languages)

- Full `pm.*` API: variables, test/expect assertions, cookies,
  sendRequest, execution flow control, iteration data.
- JSON parsing, regex, base64 encoding/decoding.
- MD5, SHA-256 hashing and UUID v4 generation.
- HMAC-SHA256 signing.
- URL encoding.
- Console / print output.

### JavaScript-only (via `require()`)

These bundled libraries are available only in JavaScript scripts:

| Library | Use case |
|---------|----------|
| `lodash` | Array/object/string utilities |
| `moment` | Date parsing, formatting, manipulation |
| `chai` | Full BDD/TDD assertion library (beyond `pm.expect`) |
| `tv4` | JSON Schema validation (Draft 4) |
| `ajv` | JSON Schema validation (Drafts 4–2020-12) |
| `xml2js` | XML-to-object parsing |
| `csv-parse/sync` | CSV parsing |
| `crypto-js` | AES encryption, HMAC, advanced hashing |

See the [JavaScript API Reference](javascript-api.md#built-in-libraries)
for usage examples.

### Python-only (built-in stdlib)

| Function | Use case |
|----------|----------|
| `re_match` / `re_search` / `re_findall` / `re_sub` | Regular expressions |
| `math_ceil` / `math_floor` / `math_sqrt` / `math_pow` / `math_log` | Math operations |
| `datetime_now()` / `datetime_utcnow()` | UTC timestamps |
| `url_quote()` / `url_urlencode()` | URL encoding |

See the [Python API Reference](python-api.md#available-standard-library)
for the full list.

### Choosing a language

- Use **JavaScript** for Postman-compatible collections, JSON Schema
  validation, XML/CSV parsing, or advanced date manipulation.
- Use **Python** when you prefer Pythonic syntax and only need the
  `pm.*` API with basic stdlib utilities.
- See [Achieving JavaScript Parity in Python](examples.md#achieving-javascript-parity-in-python)
  for side-by-side translations of every vendor library pattern.

## Where Scripts Live

- **Request-level:** Stored in `RequestModel.scripts` JSON column as
  `{"pre_request": "...", "test": "...", "language": "javascript"}`.
- **Collection/Folder-level:** Stored in `CollectionModel.events` JSON
  column.  Supports both Postman array format and internal dict format.

## Related Pages

- [External packages](external-packages.md) — `pm.require`, npm/jsr/PyPI, vendored allowlist
- [JavaScript API Reference](javascript-api.md)
- [Python API Reference](python-api.md)
- [Examples](examples.md)
- [Security](security.md)
- [Collection Runner Scripting](collection-runner.md)
- [Writing Scripts Guide](../guides/writing-scripts.md)
