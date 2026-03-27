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

# Use {{timestamp}} and {{hash}} in URL or body
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
