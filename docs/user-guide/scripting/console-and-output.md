# Console and script output

Script logs and test results appear in several places after **Send**, **Run**, or **Debug**.

## Application console

1. Open **View → Toggle Console** or press **Ctrl+J**.
2. All `console.log()` (JavaScript/TypeScript) and `print()` (Python) output from scripts appears here workspace-wide.

Useful for quick debugging without switching tabs.

## Script output panel

On the **Scripts** tab, below the editors:

| Tab | Contents |
|-----|----------|
| **Output** | Console lines, test summary, errors |
| **Debugger** | Call stack, watches, scopes (during debug) |
| **Problems** | LSP diagnostics and local dependency issues |
| **Iterations** | Data-driven run matrix (when using a data file) |
| **Mock response** | Manual status/headers/body for offline test runs |

After **Send**, check **Test Results** in the response viewer for pass/fail rows per assertion.

## Inline log hints

After a script run, faint annotations may appear beside lines that emitted console output — open **Output** for the full text.

## Common log patterns

```javascript
console.log("URL:", pm.request.url.toString());
console.log("Status:", pm.response.code);
console.log("Body:", pm.response.text());
```

```python
print("URL:", pm.request.url.to_string())
print("Status:", pm.response.code)
```

## Related

- [Debugging](debugging.md)
- [Tests and assertions (JavaScript)](javascript/tests-and-assertions.md)
