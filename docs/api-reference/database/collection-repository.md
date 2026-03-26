# Collection Repository

CRUD functions for collections (folders) and requests.  All functions
manage their own database sessions via `get_session()`.

Source: `src/database/models/collections/collection_repository.py`

## Collection Functions

### `create_new_collection`

```python
def create_new_collection(
    name: str,
    parent_id: int | None = None,
) -> CollectionModel
```

Create a new collection (folder).  Returns the detached model instance.

### `rename_collection`

```python
def rename_collection(collection_id: int, new_name: str) -> None
```

Rename a collection by ID.

### `delete_collection`

```python
def delete_collection(collection_id: int) -> None
```

Delete a collection and all its children (cascading).

### `update_collection`

```python
def update_collection(collection_id: int, **fields: Any) -> None
```

Update arbitrary fields on a collection.  Accepts any column name as a
keyword argument (e.g. `description="new desc"`, `auth={...}`).

### `update_collection_parent`

```python
def update_collection_parent(
    collection_id: int,
    new_parent_id: int | None,
) -> None
```

Move a collection to a new parent (or to root if `new_parent_id=None`).

## Request Functions

### `create_new_request`

```python
def create_new_request(
    collection_id: int,
    method: str,
    url: str,
    name: str,
    body: str | None = None,
    request_parameters: str | None = None,
    headers: str | None = None,
    scripts: dict | None = None,
    settings: dict | None = None,
    description: str | None = None,
    auth: dict | None = None,
    body_mode: str | None = None,
    body_options: dict | None = None,
    events: dict | None = None,
    protocol_profile_behavior: dict | None = None,
) -> RequestModel
```

Create a new request in the given collection.  Returns the detached
model instance.

### `rename_request`

```python
def rename_request(request_id: int, new_name: str) -> None
```

Rename a request by ID.

### `delete_request`

```python
def delete_request(request_id: int) -> None
```

Delete a request by ID.

### `update_request`

```python
def update_request(request_id: int, **fields: Any) -> None
```

Update arbitrary fields on a request.  Accepts any column name as a
keyword argument.

### `update_request_collection`

```python
def update_request_collection(
    request_id: int,
    new_collection_id: int | None,
) -> None
```

Move a request to a different collection.

## Saved Response Functions

### `save_response`

```python
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

Save a response snapshot.  Returns the new saved response ID.

### `rename_saved_response`

```python
def rename_saved_response(response_id: int, new_name: str) -> None
```

Rename a saved response by ID.

### `delete_saved_response`

```python
def delete_saved_response(response_id: int) -> None
```

Delete a saved response by ID.

### `duplicate_saved_response`

```python
def duplicate_saved_response(response_id: int) -> int
```

Duplicate a saved response.  Returns the new copy's ID.
