# Script Examples

Side-by-side JavaScript and Python examples for common scripting
patterns.

## Response Validation

### Check status code and body

**JavaScript:**

```javascript
pm.test("Status 200", function() {
    pm.expect(pm.response.code).to.equal(200);
});

pm.test("Has required fields", function() {
    var data = pm.response.json();
    pm.expect(data).to.have.property("id");
    pm.expect(data).to.have.property("name");
    pm.expect(data.name).to.be.a("string");
});

pm.test("Response time under 500ms", function() {
    pm.expect(pm.response.responseTime).to.be.below(500);
});
```

**Python:**

```python
pm.test("Status 200",
    lambda: pm.expect(pm.response.code).to.equal(200))

def check_fields():
    data = pm.response.json()
    pm.expect(data).to.have.property("id")
    pm.expect(data).to.have.property("name")
    pm.expect(data["name"]).to.be.a("string")

pm.test("Has required fields", check_fields)

pm.test("Response time under 500ms",
    lambda: pm.expect(pm.response.response_time).to.be.below(500))
```

## Auth Token Chain

Pre-request script that extracts a token from a prior login response
and injects it as a Bearer header.

**JavaScript:**

```javascript
// Pre-request: use stored token
var token = pm.variables.get("auth_token");
if (token) {
    pm.request.headers.upsert({
        key: "Authorization",
        value: "Bearer " + token
    });
}
```

```javascript
// Test script on login endpoint: save token for later
pm.test("Login successful", function() {
    pm.expect(pm.response.code).to.equal(200);
    var body = pm.response.json();
    pm.expect(body).to.have.property("token");
    pm.variables.set("auth_token", body.token);
});
```

**Python:**

```python
# Pre-request: use stored token
token = pm.variables.get("auth_token")
if token:
    pm.request.headers["Authorization"] = "Bearer " + token
```

```python
# Test script on login endpoint: save token
def save_token():
    pm.expect(pm.response.code).to.equal(200)
    body = pm.response.json()
    pm.expect(body).to.have.property("token")
    pm.variables.set("auth_token", body["token"])

pm.test("Login successful", save_token)
```

## Dynamic Data Generation

Pre-request script that sets dynamic values as variables.

**JavaScript:**

```javascript
pm.variables.set("timestamp", Date.now().toString());
pm.variables.set("random_id", Math.random().toString(36).substring(2, 10));

// Use in URL: {{base_url}}/items?ts={{timestamp}}
// Use in body: {"id": "{{random_id}}"}
```

**Python:**

```python
pm.variables.set("timestamp", datetime_now())
pm.variables.set("hash", hashlib_sha256("seed-" + datetime_now()))
pm.variables.set("request_id", uuid_v4())

# Use {{timestamp}}, {{hash}}, and {{request_id}} in URL or body
```

## JSON Schema Validation

**JavaScript:**

```javascript
pm.test("User list schema", function() {
    var data = pm.response.json();
    pm.expect(data).to.be.an("array");
    pm.expect(data).to.have.lengthOf(10);

    // Check first item shape
    var first = data[0];
    pm.expect(first).to.have.property("id");
    pm.expect(first).to.have.property("email");
    pm.expect(first.email).to.include("@");
    pm.expect(first.id).to.be.a("number");
    pm.expect(first.id).to.be.above(0);
});
```

**Python:**

```python
def check_schema():
    data = pm.response.json()
    pm.expect(data).to.be.a("list")
    pm.expect(data).to.have.length_of(10)

    first = data[0]
    pm.expect(first).to.have.property("id")
    pm.expect(first).to.have.property("email")
    pm.expect(first["email"]).to.include("@")
    pm.expect(first["id"]).to.be.above(0)

pm.test("User list schema", check_schema)
```

## Cookie Validation

**JavaScript:**

```javascript
pm.test("Session cookie set", function() {
    pm.expect(pm.cookies.get("session_id")).to.exist;
});

pm.test("Cookie count", function() {
    var all = pm.cookies.getAll();
    pm.expect(all.length).to.be.above(0);
});
```

**Python:**

```python
pm.test("Session cookie set",
    lambda: pm.expect(pm.cookies.get("session_id")).to.exist)

def check_cookies():
    cookies = pm.cookies.get_all()
    pm.expect(len(cookies)).to.be.above(0)

pm.test("Cookie count", check_cookies)
```

## Environment-Aware Scripts

**JavaScript:**

```javascript
var env = pm.environment.get("env_name");
console.log("Running against:", env);

if (env === "production") {
    pm.test("HTTPS only", function() {
        pm.expect(pm.request.url).to.include("https://");
    });
}
```

**Python:**

```python
env = pm.environment.get("env_name")
print("Running against:", env)

if env == "production":
    pm.test("HTTPS only",
        lambda: pm.expect(pm.request.url).to.include("https://"))
```

## Variable Scoping

```javascript
// Variables merge with this precedence (highest wins):
// local (script-set) > environment > collection > globals

// Read from merged scope:
var value = pm.variables.get("api_key");

// Write to specific scopes:
pm.environment.set("env_specific", "value");
pm.collectionVariables.set("collection_wide", "value");
pm.globals.set("global_value", "value");

// Template substitution uses merged variables:
var url = pm.variables.replaceIn("{{base_url}}/{{version}}/users");
```

## Negation Assertions

**JavaScript:**

```javascript
pm.test("Not unauthorized", function() {
    pm.expect(pm.response.code).to.not.equal(401);
    pm.expect(pm.response.code).to.not.equal(403);
});
```

**Python:**

```python
def check_not_auth_error():
    pm.expect(pm.response.code).not_.equal(401)
    pm.expect(pm.response.code).not_.equal(403)

pm.test("Not unauthorized", check_not_auth_error)
```

## Collection-Level Shared Setup

Set a script at the collection level to run before every request:

```javascript
// Collection pre-request script
console.log("Running:", pm.info.requestName);
pm.variables.set("run_timestamp", Date.now().toString());
```

Set a collection-level test script for common assertions:

```javascript
// Collection test script
pm.test("No server errors", function() {
    pm.expect(pm.response.code).to.be.below(500);
});
```

These scripts run automatically for every request in the collection,
thanks to script inheritance.

## Using Vendor Libraries (JavaScript only)

### JSON Schema Validation with tv4

```javascript
var tv4 = require("tv4");

var schema = {
    type: "object",
    properties: {
        id: { type: "number" },
        email: { type: "string" }
    },
    required: ["id", "email"]
};

pm.test("Matches schema", function() {
    pm.expect(tv4.validate(pm.response.json(), schema)).to.be.true;
});
```

### HMAC Request Signing with CryptoJS

```javascript
var CryptoJS = require("crypto-js");

var timestamp = Date.now().toString();
var signature = CryptoJS.HmacSHA256(timestamp + pm.request.body, pm.variables.get("secret_key")).toString();

pm.request.headers.upsert({ key: "X-Timestamp", value: timestamp });
pm.request.headers.upsert({ key: "X-Signature", value: signature });
```

### HMAC Request Signing (Python)

```python
timestamp = datetime_now()
signature = hashlib_hmac_sha256(
    timestamp + pm.request.body,
    pm.variables.get("secret_key")
)

pm.request.headers["X-Timestamp"] = timestamp
pm.request.headers["X-Signature"] = signature
```

### Data Manipulation with Lodash

```javascript
var _ = require("lodash");

pm.test("Group and count", function() {
    var data = pm.response.json();
    var grouped = _.groupBy(data, "status");
    pm.expect(_.size(grouped.active)).to.be.above(0);
});
```

## Achieving JavaScript Parity in Python

JavaScript scripts can `require()` bundled vendor libraries (lodash,
moment, crypto-js, etc.).  Python scripts cannot import external
packages, but every common task has a built-in equivalent using the
[stdlib functions](python-api.md#available-standard-library) and plain
Python syntax.

### Hashing and Signing (replaces crypto-js)

JavaScript uses `crypto-js` for HMAC, AES, and hashing.  Python
covers HMAC and hashing natively — AES encryption is not available.

```python
# SHA-256 hash
digest = hashlib_sha256("my data")

# HMAC-SHA256 signing (equivalent to CryptoJS.HmacSHA256)
sig = hashlib_hmac_sha256("message", "secret-key")

# MD5 hash (equivalent to CryptoJS.MD5)
md5 = hashlib_md5("my data")
```

### UUID Generation (replaces uuid)

```python
request_id = uuid_v4()  # "a1b2c3d4-e5f6-..."
pm.variables.set("request_id", request_id)
```

### Data Grouping and Filtering (replaces lodash)

Python's built-in comprehensions and `sorted()` cover the most common
lodash operations without any external library.

```python
def check_grouped():
    data = pm.response.json()

    # _.groupBy(data, "status")
    grouped = {}
    for item in data:
        grouped.setdefault(item["status"], []).append(item)
    pm.expect(len(grouped.get("active", []))).to.be.above(0)

    # _.filter / _.find
    active = [x for x in data if x["status"] == "active"]
    first = next((x for x in data if x["id"] == 42), None)

    # _.map / _.pick
    names = [x["name"] for x in data]
    picked = [{k: x[k] for k in ("id", "name")} for x in data]

    # _.uniq / _.sortBy
    unique = list(dict.fromkeys(names))
    by_name = sorted(data, key=lambda x: x["name"])

pm.test("Group and count", check_grouped)
```

### Date Formatting (replaces moment)

Python provides `datetime_now()` for UTC timestamps.  String slicing
handles common formatting needs.

```python
# Full ISO timestamp: "2025-01-15T12:30:45.123456"
ts = datetime_now()
pm.variables.set("timestamp", ts)

# Date only: "2025-01-15"
date_only = ts[:10]

# Seconds since epoch (string math on the timestamp)
pm.variables.set("date", date_only)
```

### JSON Schema Validation (replaces tv4 / ajv)

Use `pm.expect` assertion chains to validate structure.  This covers
the most common schema-check patterns without a formal validator.

```python
def validate_user(user):
    """Check a single user object shape."""
    pm.expect(user).to.have.property("id")
    pm.expect(user).to.have.property("email")
    pm.expect(user["id"]).to.be.a("int")
    pm.expect(user["email"]).to.be.a("str")
    pm.expect(user["email"]).to.include("@")

def check_response():
    data = pm.response.json()
    pm.expect(data).to.be.a("list")
    pm.expect(data).to.have.length_of(10)
    for user in data:
        validate_user(user)

pm.test("User list matches schema", check_response)
```

### XML Parsing (replaces xml2js)

XML parsing is not available in the Python sandbox.  If your API
returns XML, parse it with `pm.expect` string assertions or use
regex extraction:

```python
def check_xml():
    body = pm.response.text()
    pm.expect(body).to.include("<status>ok</status>")
    match = re_search(r"<id>(\d+)</id>", body)
    pm.expect(match).to.exist

pm.test("XML contains status", check_xml)
```

### CSV Parsing (replaces csv-parse)

CSV parsing is not available in the Python sandbox.  For simple CSV
responses, split on delimiters:

```python
def check_csv():
    lines = pm.response.text().strip().split("\n")
    headers = lines[0].split(",")
    pm.expect(headers).to.include("email")
    pm.expect(len(lines)).to.be.above(1)

    # Parse a row
    row = dict(zip(headers, lines[1].split(",")))
    pm.expect(row).to.have.property("email")

pm.test("CSV has expected columns", check_csv)
```

### Quick Reference

| JS library | Python equivalent |
|------------|-------------------|
| `CryptoJS.HmacSHA256(msg, key)` | `hashlib_hmac_sha256(msg, key)` |
| `CryptoJS.SHA256(msg)` | `hashlib_sha256(msg)` |
| `CryptoJS.MD5(msg)` | `hashlib_md5(msg)` |
| `CryptoJS.AES.encrypt(...)` | *Not available* |
| `require("uuid").v4()` | `uuid_v4()` |
| `_.groupBy(arr, key)` | `setdefault` loop (see above) |
| `_.filter(arr, pred)` | List comprehension |
| `_.map(arr, fn)` | List comprehension |
| `_.uniq(arr)` | `list(dict.fromkeys(arr))` |
| `_.sortBy(arr, key)` | `sorted(arr, key=...)` |
| `moment().format(...)` | `datetime_now()` + string slicing |
| `tv4.validate(obj, schema)` | `pm.expect` assertion chains |
| `xml2js.parseString(...)` | `re_search()` on raw text |
| `csvParse(text)` | `str.split()` on lines/commas |

## Postman parity recipes

Recipes that exercise the parity surface added in the latest round —
see [Postman API parity](postman-parity.md) for the full matrix.

### Reason phrase + MIME inspection

```javascript
pm.test("Reason and MIME", function () {
    pm.expect(pm.response.reason()).to.equal("OK");
    pm.expect(pm.response.mime().type).to.equal("application/json");
});
```

```python
def reason_mime():
    pm.expect(pm.response.reason()).to.equal("OK")
    pm.expect(pm.response.mime()["type"]).to.equal("application/json")
pm.test("Reason and MIME", reason_mime)
```

### Resolved variables (read-through scopes)

```javascript
pm.environment.set("base", "https://api.example.com");
console.log(pm.variables.get("base"));   // resolves through env
```

```python
pm.environment.set("base", "https://api.example.com")
print(pm.variables.get("base"))           # same
```

### Skipping tests

```javascript
pm.test("Conditional", function (ctx) {
    if (!pm.environment.get("token")) ctx.skip();
    pm.expect(pm.environment.get("token")).to.have.lengthOf.above(0);
});
pm.test.skip("WIP — coming next sprint", function () { /* ... */ });
```

```python
def conditional(ctx):
    if not pm.environment.get("token"):
        ctx.skip()
    pm.expect(pm.environment.get("token")).to.have.length_of.above(0)
pm.test("Conditional", conditional)

pm.test.skip("WIP — coming next sprint", lambda: None)
```

### URL surgery in pre-request

```javascript
pm.request.url.query.upsert({ key: "page", value: "2" });
pm.request.url.query.add({ key: "limit", value: "50" });
console.log(pm.request.url.toString());
```

```python
pm.request.url.query.upsert({"key": "page", "value": "2"})
pm.request.url.query.add({"key": "limit", "value": "50"})
print(pm.request.url.toString())
```

### Inspecting `originalRequest`

```javascript
pm.test("Original host", function () {
    pm.expect(pm.response.originalRequest.url.getHost())
      .to.equal("api.example.com");
});
```

### Status assertion by canonical name

```javascript
pm.test("Created", function () {
    pm.response.to.have.status("Created");   // accepts 201 OR "Created"
});
```

### Body assertion by RegExp / oneOf

```javascript
pm.test("Body shape", function () {
    pm.expect(pm.response).to.have.body(/"id"\s*:\s*\d+/);
    pm.expect(pm.response.code).to.be.oneOf([200, 201, 202]);
});
```

### Lodash-style JSON path

```javascript
pm.test("Deep path", function () {
    pm.expect(pm.response).to.have.jsonBody("items[0].user.name", "alice");
});
```

## Private package registries

See [external-packages.md → Private package registries](external-packages.md#private-package-registries)
for the configuration walkthrough. Once a private mirror is configured
from **Settings → Scripting → Private package registries**, the `pm.require`
calls below resolve through it transparently.

### Importing from a private @scope (npm)

```javascript
// Settings:
//   Private package registries → Add row
//     scope = "@mycompany"
//     URL   = "https://npm.mycorp.io/"
//     Auth  = Token (your CI read-only token)
//
// Public packages still come from registry.npmjs.org.
const lodash = pm.require("npm:lodash@4.17.21");
const internal = pm.require("npm:@mycompany/auth-helpers@2.4.0");

pm.test("internal helpers wired", function () {
    pm.expect(typeof internal.signRequest).to.equal("function");
});
```

### Routing JSR through a private upstream

```javascript
// Cloudsmith / Artifactory / Verdaccio expose JSR packages over
// npm-compatible HTTP. Add the proxy as a scope row with Type = JSR.
const stdAssert = pm.require("jsr:@std/assert@0.220.1");

pm.test("std/assert resolved through proxy", function () {
    pm.expect(typeof stdAssert.assertEquals).to.equal("function");
});
```

### Importing from a private PyPI (Python / Pyodide)

```python
# Settings:
#   Private package registries → Python (PyPI) index — Pyodide runtime
#     Primary index URL = "https://pypi.mycorp.io/simple/"
#     Auth = Token  (embedded into the URL micropip uses)
#
internal_sdk = pm.require("internal-sdk==1.2.0")

def check_handshake():
    client = internal_sdk.Client(base_url=pm.environment.get("api"))
    pm.expect(client.ping()).to.equal("pong")

pm.test("internal handshake", check_handshake)
```

> Private-PyPI applies to the **Pyodide** Python runtime only — the
> RestrictedPython subprocess fallback has no install step.
