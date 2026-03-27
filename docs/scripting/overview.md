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
| JavaScript | V8 via PyMiniRacer | Yes | V8 isolate (5 s, 64 MB) |
| Python | Subprocess + RestrictedPython | No | Process isolation (5 s CPU, 128 MB) |

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

## Where Scripts Live

- **Request-level:** Stored in `RequestModel.scripts` JSON column as
  `{"pre_request": "...", "test": "...", "language": "javascript"}`.
- **Collection/Folder-level:** Stored in `CollectionModel.events` JSON
  column.  Supports both Postman array format and internal dict format.

## Related Pages

- [JavaScript API Reference](javascript-api.md)
- [Python API Reference](python-api.md)
- [Examples](examples.md)
- [Security](security.md)
- [Collection Runner Scripting](collection-runner.md)
- [Writing Scripts Guide](../guides/writing-scripts.md)
