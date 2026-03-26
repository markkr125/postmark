# CollectionService

Service layer for collection and request management.  All methods are
`@staticmethod` — no instance state.

Source: `src/services/collection_service.py`

## Queries

### `fetch_all`

```python
@staticmethod
def fetch_all() -> dict[str, Any]
```

Fetch the entire collection tree.  Delegates to
`fetch_all_collections()`.

### `get_collection`

```python
@staticmethod
def get_collection(collection_id: int) -> CollectionModel | None
```

Get a single collection by ID.

### `get_request`

```python
@staticmethod
def get_request(request_id: int) -> RequestModel | None
```

Get a single request by ID.

### `get_request_breadcrumb`

```python
@staticmethod
def get_request_breadcrumb(request_id: int) -> list[dict[str, Any]]
```

Build breadcrumb trail for a request.

### `get_collection_breadcrumb`

```python
@staticmethod
def get_collection_breadcrumb(collection_id: int) -> list[dict[str, Any]]
```

Build breadcrumb trail for a collection.

### `get_folder_request_count`

```python
@staticmethod
def get_folder_request_count(collection_id: int) -> int
```

Count requests in a collection.

### `get_recent_requests`

```python
@staticmethod
def get_recent_requests(
    collection_id: int,
    limit: int = 10,
) -> list[dict[str, Any]]
```

Fetch recently updated requests in a collection.

## Auth Chain

### `get_request_auth_chain`

```python
@staticmethod
def get_request_auth_chain(request_id: int) -> dict[str, Any] | None
```

Get effective auth config for a request (walks ancestry).

### `get_request_inherited_auth`

```python
@staticmethod
def get_request_inherited_auth(request_id: int) -> dict[str, Any] | None
```

Get inherited auth (skipping request's own auth).

### `get_collection_inherited_auth`

```python
@staticmethod
def get_collection_inherited_auth(collection_id: int) -> dict[str, Any] | None
```

Get inherited auth for a collection.

### `get_request_variable_chain`

```python
@staticmethod
def get_request_variable_chain(request_id: int) -> dict[str, str]
```

Build flat variable map from collection ancestry.

## Mutations — Collections

### `create_collection`

```python
@staticmethod
def create_collection(
    name: str,
    parent_id: int | None = None,
) -> CollectionModel
```

### `rename_collection`

```python
@staticmethod
def rename_collection(collection_id: int, new_name: str) -> None
```

### `delete_collection`

```python
@staticmethod
def delete_collection(collection_id: int) -> None
```

### `move_collection`

```python
@staticmethod
def move_collection(
    collection_id: int,
    new_parent_id: int | None,
) -> None
```

### `update_collection`

```python
@staticmethod
def update_collection(collection_id: int, **fields: Any) -> None
```

## Mutations — Requests

### `create_request`

```python
@staticmethod
def create_request(
    collection_id: int,
    method: str,
    url: str,
    name: str,
    body: str | None = None,
    request_parameters: str | None = None,
    headers: str | None = None,
    scripts: dict | None = None,
    settings: dict | None = None,
) -> RequestModel
```

### `rename_request`

```python
@staticmethod
def rename_request(request_id: int, new_name: str) -> None
```

### `delete_request`

```python
@staticmethod
def delete_request(request_id: int) -> None
```

### `move_request`

```python
@staticmethod
def move_request(request_id: int, new_collection_id: int) -> None
```

### `update_request`

```python
@staticmethod
def update_request(request_id: int, **fields: Any) -> None
```

## Saved Responses

### `get_saved_responses`

```python
@staticmethod
def get_saved_responses(request_id: int) -> list[SavedResponseDict]
```

### `get_saved_response`

```python
@staticmethod
def get_saved_response(response_id: int) -> SavedResponseDict | None
```

### `save_response`

```python
@staticmethod
def save_response(
    request_id: int,
    name: str,
    status: str | None,
    code: int | None,
    headers: Any,
    body: str | None,
    preview_language: str | None = None,
    original_request: dict[str, Any] | None = None,
) -> int
```

Returns the new saved response ID.

### `rename_saved_response`

```python
@staticmethod
def rename_saved_response(response_id: int, new_name: str) -> None
```

### `delete_saved_response`

```python
@staticmethod
def delete_saved_response(response_id: int) -> None
```

### `duplicate_saved_response`

```python
@staticmethod
def duplicate_saved_response(response_id: int) -> int
```

Returns the new copy's ID.

## TypedDicts

See [TypedDict Catalogue](../typedicts.md) for `RequestLoadDict` and
`SavedResponseDict` field definitions.
