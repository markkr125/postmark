# Environment Repository

CRUD functions for environment variable sets.  All functions manage
their own sessions via `get_session()`.

Source: `src/database/models/environments/environment_repository.py`

## `fetch_all_environments`

```python
def fetch_all_environments() -> list[dict[str, Any]]
```

Fetch all environments as a list of dicts.  Each dict contains `id`,
`name`, `values`, and timestamps.

## `create_environment`

```python
def create_environment(
    name: str,
    values: list[dict[str, Any]] | None = None,
) -> EnvironmentModel
```

Create a new environment.  Returns the detached model instance.

**Parameters:**
- `name` — display name for the environment.
- `values` — optional initial variable list.  Each entry:
  `{"key": str, "value": str, "enabled": bool}`.

## `get_environment_by_id`

```python
def get_environment_by_id(
    environment_id: int,
) -> EnvironmentModel | None
```

Fetch a single environment by ID.  Returns `None` if not found.

## `rename_environment`

```python
def rename_environment(
    environment_id: int,
    new_name: str,
) -> None
```

Rename an environment by ID.

## `delete_environment`

```python
def delete_environment(environment_id: int) -> None
```

Delete an environment by ID.

## `update_environment_values`

```python
def update_environment_values(
    environment_id: int,
    values: list[dict[str, Any]],
) -> None
```

Replace the variable list for an environment.  The entire `values` JSON
column is overwritten.
