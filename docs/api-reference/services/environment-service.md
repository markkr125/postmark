# EnvironmentService

Service layer for environment management and `{{variable}}` substitution.
All methods are `@staticmethod`.

Source: `src/services/environment_service.py`

## CRUD Methods

### `fetch_all`

```python
@staticmethod
def fetch_all() -> list[dict[str, Any]]
```

Fetch all environments.

### `get_environment`

```python
@staticmethod
def get_environment(environment_id: int) -> EnvironmentModel | None
```

### `create_environment`

```python
@staticmethod
def create_environment(
    name: str,
    values: list[dict[str, Any]] | None = None,
) -> EnvironmentModel
```

### `rename_environment`

```python
@staticmethod
def rename_environment(environment_id: int, new_name: str) -> None
```

### `delete_environment`

```python
@staticmethod
def delete_environment(environment_id: int) -> None
```

### `update_environment_values`

```python
@staticmethod
def update_environment_values(
    environment_id: int,
    values: list[dict[str, Any]],
) -> None
```

## Variable Map Builders

### `build_variable_map`

```python
@staticmethod
def build_variable_map(environment_id: int | None) -> dict[str, str]
```

Build a flat `{key: value}` map from an environment's variables.
Returns empty dict if `environment_id` is `None` or not found.

### `build_combined_variable_map`

```python
@staticmethod
def build_combined_variable_map(
    environment_id: int | None,
    request_id: int | None,
) -> dict[str, str]
```

Build a combined variable map by merging environment variables with
collection ancestor chain variables.  Collection variables override
environment variables.

### `build_combined_variable_detail_map`

```python
@staticmethod
def build_combined_variable_detail_map(
    environment_id: int | None,
    request_id: int | None,
) -> dict[str, VariableDetail]
```

Like `build_combined_variable_map` but returns `VariableDetail` dicts
with source metadata (value, source type, source ID).  Used by the
variable popup to show where each variable comes from.

## Variable Mutation

### `update_variable_value`

```python
@staticmethod
def update_variable_value(
    source: str,
    source_id: int,
    key: str,
    new_value: str,
) -> None
```

Update a single variable's value in its source (environment or
collection).  `source` is `"environment"` or `"collection"`.

### `add_variable`

```python
@staticmethod
def add_variable(
    source: str,
    source_id: int,
    key: str,
    value: str,
) -> None
```

Add a new variable to an environment or collection.

## Substitution

### `substitute`

```python
@staticmethod
def substitute(text: str, variables: dict[str, str]) -> str
```

Replace all `{{key}}` placeholders in `text` with values from the
`variables` dict.  Unmatched placeholders are left unchanged.

Uses the regex pattern `r"\{\{(.+?)\}\}"`.

## TypedDicts

See [TypedDict Catalogue](../typedicts.md) for `VariableDetail` and
`LocalOverride` field definitions.
