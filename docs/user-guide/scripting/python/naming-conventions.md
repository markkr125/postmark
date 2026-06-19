# Python naming conventions

Python scripts can use **snake_case** helpers. Postman-style **camelCase** aliases also work for pasted scripts.

## Dual naming

| camelCase (Postman) | snake_case (Pythonic) |
|---------------------|------------------------|
| `pm.collectionVariables` | `pm.collection_variables` |
| `pm.iterationData` | `pm.iteration_data` |
| `pm.sendRequest` | `pm.send_request` |
| `pm.execution.setNextRequest` | `pm.execution.set_next_request` |
| `pm.execution.skipRequest` | `pm.execution.skip_request` |

Both forms refer to the same objects. Pick one style per file for readability.

## Response helpers

```python
pm.response.json()
pm.response.text()
pm.response.code
pm.response.response_time  # snake_case attribute
```

CamelCase properties such as `responseTime` may also exist for parity — prefer snake_case in new Python scripts.

## Restricted fallback runtime

When the full Pyodide runtime is unavailable, Python runs in a restricted subprocess:

- No `import` statements — use injected helpers (`json_loads`, `re_search`, etc.).
- No `open()`, `eval()`, or `exec()`.
- See [Python API reference](../../../scripting/python-api.md) for allowed builtins.

With Pyodide + Deno, more packages are available via `pm.require`.

## Related

- [Variables](variables.md)
- [Python API reference](../../../scripting/python-api.md)
