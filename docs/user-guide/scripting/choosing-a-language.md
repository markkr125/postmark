# Choosing a script language

Each script editor (pre-request and test) can use **JavaScript**, **TypeScript**, **Python**, or **Auto** (detect from content).

## Set the language

1. Open the **Scripts** tab on a request, folder, or collection.
2. Click the language label in the **status bar** under the editor (e.g. **JavaScript**).
3. Pick **JavaScript**, **TypeScript**, **Python**, or **Auto**.

Pre-request and test editors can use different languages on the same request.

## Which language to pick

| Language | Best for |
|----------|----------|
| **JavaScript** | Default; full Postman-style `pm.*` API; imported Postman collections |
| **TypeScript** | Same runtime as JavaScript; optional type annotations for readability |
| **Python** | Python syntax; snake_case helpers; same `pm.*` concepts with aliases |

All three share the same scripting concepts: variables, tests, `pm.sendRequest`, and external packages via `pm.require` (with language-specific rules).

## Runtime requirements

| Language | Needs |
|----------|--------|
| JavaScript / TypeScript | **Deno** — download or configure under **File → Settings… → Scripting** |
| Python | **Deno** + vendored Pyodide when available; otherwise a restricted Python subprocess |

If Deno is missing, a banner in the script editor links to **Scripting** settings.

## Timeouts

Scripts are limited to a few seconds of execution. Avoid infinite loops and heavy CPU work in pre-request or test scripts.

## Related

- [Scripts tab](scripts-tab.md)
- [JavaScript guide](javascript/README.md)
- [TypeScript guide](typescript/README.md)
- [Python guide](python/README.md)
- [Scripting runtimes](../settings/scripting-runtimes.md)
