# Writing Scripts

Step-by-step guide for adding pre-request and test scripts to your
requests and collections.

## Finding the Scripts Tab

### Request-level scripts

1. Open a request in the editor.
2. Click the **Scripts** tab (next to Auth, Headers, Body).
3. Two editors appear: **Pre-request** and **Test**.
4. Select a language from the dropdown (JavaScript or Python).

### Collection/Folder-level scripts

1. Click a collection or folder in the sidebar.
2. The folder editor shows **Pre-request Script** and **Test Script**
   editors.
3. These scripts run for every request inside the collection/folder.

## Choosing a Language

| Factor | JavaScript | Python |
|--------|-----------|--------|
| Postman compatibility | Full | Partial (different naming) |
| Sandbox | V8 isolate | Subprocess + RestrictedPython |
| Timeout | 5 seconds | 5 seconds CPU |
| Default | Yes | No (opt-in) |

Use JavaScript for Postman-imported collections.  Use Python if you
prefer Python syntax.  Both languages provide the same `pm.*` API.

## Your First Test Script

### Step 1: Write the script

In the Test editor:

```javascript
pm.test("Status is 200", function() {
    pm.expect(pm.response.code).to.equal(200);
});
```

### Step 2: Send the request

Click **Send**.  The script runs after the response arrives.

### Step 3: View results

Switch to the **Test Results** tab in the Response Viewer.  You'll see:

- A summary: `1/1 tests passed`
- A row for each test with a green check or red X.
- Error details for failed tests.

## Your First Pre-request Script

```javascript
// Set a timestamp variable
pm.variables.set("ts", Date.now().toString());

// Use {{ts}} in the URL or body
console.log("Timestamp set:", pm.variables.get("ts"));
```

The variable `{{ts}}` can now be used in the URL, headers, or body
with double-brace syntax.

## Using Inherited Scripts

1. Open a collection or folder.
2. Add a pre-request script (e.g., logging or auth setup).
3. Every request inside that collection/folder will run the script
   before its own pre-request script.

```text
Collection pre-request: console.log("Starting request")
  Folder pre-request:   pm.request.headers.upsert({key: "X-Custom", value: "1"})
    Request pre-request: pm.variables.set("id", "123")
```

## Debugging via Console Panel

All `console.log()` (JavaScript) and `print()` (Python) output appears
in the Console Panel at the bottom of the window.

Common debugging patterns:

```javascript
console.log("Request URL:", pm.request.url);
console.log("Response body:", pm.response.text());
console.log("Variables:", JSON.stringify(pm.variables.toObject()));
```

## Common Pitfalls

### Script timeout

Scripts have a 5-second timeout.  Infinite loops or heavy computation
will be killed with a `Script timed out` error.

### Missing response in pre-request

`pm.response` is `null` in pre-request scripts.  Accessing it will
cause a runtime error.

### Python import statements

Python scripts cannot use `import`.  Use pre-injected functions instead:
`json_loads()`, `re_search()`, `hashlib_sha256()`, etc.  See
[Python API](../scripting/python-api.md) for the full list.

### RestrictedPython compilation errors

Python scripts that use `getattr()` on private attributes, `exec()`,
`eval()`, or `open()` will fail at compilation time with a
`Compilation failed` error.

## Related Pages

- [JavaScript API Reference](../scripting/javascript-api.md)
- [Python API Reference](../scripting/python-api.md)
- [Examples](../scripting/examples.md)
- [Security](../scripting/security.md)
