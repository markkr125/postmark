# Variables (Python)

Python exposes the same variable scopes as JavaScript through `pm.*`.

## Scopes

```python
pm.variables.set("key", "value")
value = pm.variables.get("key")

pm.environment.set("base_url", "https://api.example.com")
pm.collection_variables.set("version", "v1")
pm.globals.set("last_run", str(pm.variables.replace_in("{{$timestamp}}")))
```

CamelCase aliases work too: `pm.collectionVariables.set(...)`.

## Substitution

```python
url = pm.variables.replace_in("{{base_url}}/users/{{user_id}}")
```

## Iteration data

During collection or data-driven runs:

```python
row = pm.iteration_data.to_object()
user_id = pm.iteration_data.get("userId")
```

## Related

- [Environment variables](../../environments/variables.md)
- [Naming conventions](naming-conventions.md)
- [Python API reference](../../../scripting/python-api.md)
