# Javascript `pm` API quick reference

Generated from LSP stubs by ``scripts/build_app_wiki.py``. For narratives and examples see [JavaScript API](../../../docs/scripting/javascript-api.md) or [Python API](../../../docs/scripting/python-api.md).

TypeScript uses the same `pm` surface; types are stripped at run time.

## `pm` members

- `pm.clearEnvironmentVariable`
- `pm.clearGlobalVariable`
- `pm.collectionVariables`
- `pm.collectionVariables.clear`
- `pm.collectionVariables.get`
- `pm.collectionVariables.has`
- `pm.collectionVariables.replaceIn`
- `pm.collectionVariables.set`
- `pm.collectionVariables.toObject`
- `pm.collectionVariables.unset`
- `pm.cookies`
- `pm.cookies.get`
- `pm.cookies.getAll`
- `pm.cookies.jar`
- `pm.environment`
- `pm.environment.clear`
- `pm.environment.get`
- `pm.environment.has`
- `pm.environment.replaceIn`
- `pm.environment.set`
- `pm.environment.toObject`
- `pm.environment.unset`
- `pm.execution`
- `pm.execution.location`
- `pm.execution.setNextRequest`
- `pm.execution.skipRequest`
- `pm.expect`
- `pm.getEnvironmentVariable`
- `pm.getGlobalVariable`
- `pm.globals`
- `pm.globals.clear`
- `pm.globals.get`
- `pm.globals.has`
- `pm.globals.replaceIn`
- `pm.globals.set`
- `pm.globals.toObject`
- `pm.globals.unset`
- `pm.info`
- `pm.iterationData`
- `pm.iterationData.get`
- `pm.iterationData.has`
- `pm.iterationData.toObject`
- `pm.request`
- `pm.require`
- `pm.response`
- `pm.sendRequest`
- `pm.setEnvironmentVariable`
- `pm.setGlobalVariable`
- `pm.test`
- `pm.variables`
- `pm.variables.clear`
- `pm.variables.get`
- `pm.variables.has`
- `pm.variables.replaceIn`
- `pm.variables.set`
- `pm.variables.toObject`
- `pm.variables.unset`
- `pm.visualizer`
- `pm.visualizer.set`

## Global helpers (call WITHOUT a `pm.` prefix)

These are top-level builtins in the script sandbox — e.g. `datetime_now()`, not `pm.datetime_now()`.

- `require(module)` — Import a bundled library (lodash, moment, crypto-js, …)
- `atob(encoded)` — Decode base64 string
- `btoa(data)` — Encode string to base64
- `responseTime` — Legacy global: response elapsed ms (test scripts)
