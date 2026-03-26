# Query Repository

Read-only query functions for the collection tree.  All functions manage
their own sessions via `get_session()`.

Source: `src/database/models/collections/collection_query_repository.py`

## Tree Queries

### `fetch_all_collections`

```python
def fetch_all_collections() -> dict[str, Any]
```

Fetch the entire collection tree with nested children and requests.
Returns a dict with a `"collections"` key containing the top-level
collection list.  Each collection includes nested `children` and
`requests` lists.

### `get_collection_by_id`

```python
def get_collection_by_id(collection_id: int) -> CollectionModel | None
```

Fetch a single collection by ID.  Returns `None` if not found.

### `get_request_by_id`

```python
def get_request_by_id(request_id: int) -> RequestModel | None
```

Fetch a single request by ID.  Returns `None` if not found.

### `count_collection_requests`

```python
def count_collection_requests(collection_id: int) -> int
```

Count the total number of requests in a collection (direct children
only).

### `get_recent_requests_for_collection`

```python
def get_recent_requests_for_collection(
    collection_id: int,
    limit: int = 10,
) -> list[dict[str, Any]]
```

Fetch the most recently updated requests in a collection.  Returns a
list of dicts with request metadata.

## Breadcrumb Queries

### `get_request_breadcrumb`

```python
def get_request_breadcrumb(request_id: int) -> list[dict[str, Any]]
```

Build the breadcrumb trail for a request: root collection → ... →
parent folder → request name.  Each entry has `type`, `id`, and `name`.

### `get_collection_breadcrumb`

```python
def get_collection_breadcrumb(collection_id: int) -> list[dict[str, Any]]
```

Build the breadcrumb trail for a collection.

## Auth Chain Queries

### `get_request_auth_chain`

```python
def get_request_auth_chain(request_id: int) -> dict[str, Any] | None
```

Get the effective auth config for a request by walking up the collection
ancestry.  Returns the first non-`"inherit"` auth dict found, or `None`.

### `get_request_inherited_auth`

```python
def get_request_inherited_auth(request_id: int) -> dict[str, Any] | None
```

Get inherited auth for a request (skipping the request's own auth).
Walks the parent collection chain only.

### `get_collection_inherited_auth`

```python
def get_collection_inherited_auth(
    collection_id: int,
) -> dict[str, Any] | None
```

Get inherited auth for a collection (from its parent chain only).

## Variable Chain Queries

### `get_request_variable_chain`

```python
def get_request_variable_chain(request_id: int) -> dict[str, str]
```

Build a flat variable map by walking the collection ancestry.  Child
collections override parent values.  Returns `{"key": "value", ...}`.

### `get_request_variable_chain_detailed`

```python
def get_request_variable_chain_detailed(
    request_id: int,
) -> dict[str, tuple[str, int]]
```

Like `get_request_variable_chain` but returns `(value, collection_id)`
tuples so callers know which collection defined each variable.

### `get_collection_variable_chain_detailed`

```python
def get_collection_variable_chain_detailed(
    collection_id: int,
) -> dict[str, tuple[str, int]]
```

Same as `get_request_variable_chain_detailed` but starts from a
collection instead of a request.

## Saved Response Queries

### `get_saved_responses_for_request`

```python
def get_saved_responses_for_request(
    request_id: int,
) -> list[dict[str, Any]]
```

Fetch all saved responses for a request.  Returns a list of dicts.

### `get_saved_response`

```python
def get_saved_response(response_id: int) -> dict[str, Any] | None
```

Fetch a single saved response by ID.  Returns `None` if not found.
