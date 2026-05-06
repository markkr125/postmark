# Writing Scripts

Step-by-step guide for adding pre-request and test scripts to your
requests and collections.

## Finding the Scripts Tab

### Request-level scripts

1. Open a request in the editor.
2. Click the **Scripts** tab (next to Auth, Headers, Body).
3. Two editors appear: **Pre-request** and **Test**.
4. Set the script language from the **status bar** under each editor: click the
   language name (e.g. **JavaScript**) to open JavaScript, TypeScript, Python, or **Auto**
   (content-based detection). The top toolbar no longer has a separate language
   dropdown.

### Collection/Folder-level scripts

1. Click a collection or folder in the sidebar.
2. The folder editor shows **Pre-request Script** and **Test Script**
   editors.
3. These scripts run for every request inside the collection/folder.

## Choosing a Language

| Factor | JavaScript | TypeScript | Python |
|--------|-----------|------------|--------|
| Postman compatibility | Full | Full (same `pm.*` as JS) | Partial (different naming) |
| Sandbox | Deno subprocess | Deno subprocess (type-stripped) | Pyodide (Deno + WASM) when the vendored runtime is installed; otherwise RestrictedPython subprocess |
| Timeout | 5 seconds | 5 seconds | 5 seconds CPU |
| Default | Yes | No (opt-in) | No (opt-in) |

Use JavaScript for Postman-imported collections.  **TypeScript** uses the same
Deno run as JavaScript; the editor writes a `.ts` temp bundle so you can add
types for readability.  Use Python if you prefer Python syntax.  All three
provide the same `pm.*` API.

### TypeScript

You can write test scripts with optional type annotations; Deno strips types at
run time (no separate transpiler). Example:

```ts
const data: { id: number } = pm.response.json();
pm.test("has id", () => pm.expect(data.id).to.be.a("number"));
```

## npm and JSR packages (JavaScript)

Use **`pm.require`** with a **string literal** whose value starts with **`npm:`**
or **`jsr:`** and pins an **exact** semantic version (for example
``pm.require('npm:lodash@4.17.21')``).  The host scans your script before launch,
emits static `import` lines for Deno, and registers the module on
`pm.require` at runtime.  Calls that use variables, concatenation, or
version ranges (such as ``^1.0.0``) are not supported for bundling.

## PyPI packages (Python)

When the **Pyodide** runtime is installed (see ``data/scripts/vendor_pyodide/``),
Python scripts run under Deno with **`pm.require("package")`** or
**`pm.require("package==1.2.3")`** using **string literals** only (same
scanning rules as the host — exact versions after ``==``).  ``micropip``
downloads wheels into the per-user cache; first use may require network
access to PyPI and the Pyodide CDN.  Without the vendored runtime, Postmark
falls back to the RestrictedPython subprocess.

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

## Editor shortcuts

- **Ctrl+/** — toggle line comment on the selection or current line.
- **Ctrl+Space** — manually open the autocomplete popup.
- **Ctrl+P** — show the parameter signature for the current call.
- **Ctrl+Q** — show a quick-doc popup for the symbol at the text cursor.
- **Ctrl+click** — jump to the definition of a user-declared variable;
  for `pm.*` API entries the quick-doc popup opens instead.
- **Ctrl+hover** — underlines the identifier segment under the cursor and,
  after ~400 ms, shows the same quick-doc popup. Language keywords
  (`const`, `let`, `import`, ...) and unresolved local names are skipped.

## Related Pages

- [External packages](../scripting/external-packages.md) — `pm.require` and the legacy vendored allowlist
- [JavaScript API Reference](../scripting/javascript-api.md)
- [Python API Reference](../scripting/python-api.md)
- [Examples](../scripting/examples.md)
- [Security](../scripting/security.md)
