# Variables (JavaScript)

Scripts read and write variables through the `pm.*` scopes. Resolution matches Postman's order.

## Scopes

| API | Scope |
|-----|--------|
| `pm.variables` | Resolved value (read); writes go to **local** for this run |
| `pm.environment` | Active environment |
| `pm.collectionVariables` | Current collection |
| `pm.globals` | Workspace globals (persisted between runs) |
| `pm.iterationData` | Current row in a data-driven or collection run |

## Read and write

```javascript
pm.variables.set("token", "abc123");
const token = pm.variables.get("token");

pm.environment.set("baseUrl", "https://api.example.com");
pm.collectionVariables.set("version", "v1");
pm.globals.set("lastRun", Date.now().toString());
```

## Substitution in strings

```javascript
const url = pm.variables.replaceIn("{{baseUrl}}/users/{{userId}}");
pm.request.url = url;
```

## Inspect all resolved values

```javascript
console.log(pm.variables.toObject());
```

## Dynamic variables

Use Postman-style names in scripts or request text:

```javascript
const id = pm.variables.replaceIn("{{$guid}}");
```

Examples: `{{$timestamp}}`, `{{$randomInt}}`, `{{$isoTimestamp}}`.

## Related

- [Environment variables](../../environments/variables.md)
- [Pre-request scripts](pre-request-scripts.md)
- [JavaScript API reference](../../../scripting/javascript-api.md)
