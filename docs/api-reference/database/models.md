# ORM Models

Four SQLAlchemy 2.0 models define the database schema.  All use
`Mapped[]` type annotations with `mapped_column()`.

Source: `src/database/models/`

## CollectionModel

**Table:** `collections`
**Module:** `database.models.collections.model.collection_model`

Represents folders in the collection tree.  Self-referential via
`parent_id` for nested folder hierarchies.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `int` | Primary key | Auto-increment ID |
| `name` | `str` | String(255), indexed | Display name |
| `parent_id` | `int \| None` | ForeignKey(`collections.id`) | Parent folder (None = root) |
| `description` | `str \| None` | Text | Folder description |
| `variables` | `list[dict] \| None` | JSON | Collection-level variables |
| `auth` | `dict \| None` | JSON | Auth config inherited by children |
| `events` | `dict \| None` | JSON | Pre/post-request scripts |
| `created_at` | `datetime \| None` | Server default: `now()` | Creation timestamp |
| `updated_at` | `datetime \| None` | Server default: `now()`, onupdate | Last update timestamp |

**Relationships:**
- `children: list[CollectionModel]` — child folders (self-referential)
- `requests: list[RequestModel]` — direct child requests

## RequestModel

**Table:** `requests`
**Module:** `database.models.collections.model.request_model`

Represents an HTTP request stored in a collection.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `int` | Primary key | Auto-increment ID |
| `collection_id` | `int` | ForeignKey(`collections.id`) | Parent collection |
| `name` | `str` | String(255), indexed | Display name |
| `method` | `str` | String(10) | HTTP method (GET, POST, etc.) |
| `url` | `str` | Text, indexed | Request URL (may contain `{{vars}}`) |
| `body` | `str \| None` | Text | Request body content |
| `request_parameters` | `list[dict] \| None` | JSON | Query parameters |
| `headers` | `list[dict] \| None` | JSON | Request headers |
| `description` | `str \| None` | Text | Request description |
| `body_mode` | `str \| None` | String(20) | Body type: raw, formdata, urlencoded, binary, graphql |
| `body_options` | `dict \| None` | JSON | Body encoding/format settings |
| `auth` | `dict \| None` | JSON | Request-level auth config |
| `scripts` | `dict \| None` | JSON | Pre/post-request scripts |
| `settings` | `dict \| None` | JSON | Request-specific settings |
| `events` | `dict \| None` | JSON | Event hooks |
| `protocol_profile_behavior` | `dict \| None` | JSON | Postman compatibility |
| `created_at` | `datetime \| None` | Server default: `now()` | Creation timestamp |
| `updated_at` | `datetime \| None` | Server default: `now()`, onupdate | Last update timestamp |

**Relationships:**
- `collection: CollectionModel` — parent collection (`back_populates="requests"`)
- `saved_responses: list[SavedResponseModel]` — attached saved responses

## SavedResponseModel

**Table:** `saved_responses`
**Module:** `database.models.collections.model.saved_response_model`

Named HTTP response snapshots attached to a request.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `int` | Primary key | Auto-increment ID |
| `request_id` | `int` | ForeignKey(`requests.id`) | Parent request |
| `name` | `str` | String(255) | Display name |
| `status` | `str \| None` | String(50) | Status text (e.g. "OK") |
| `code` | `int \| None` | Integer | HTTP status code |
| `headers` | `list[dict] \| None` | JSON | Response headers |
| `body` | `str \| None` | Text | Response body |
| `preview_language` | `str \| None` | String(20) | Syntax highlighting language |
| `original_request` | `dict \| None` | JSON | Snapshot of request at save time |
| `created_at` | `datetime \| None` | Server default: `now()` | Creation timestamp |

**Relationships:**
- `request: RequestModel` — parent request (`back_populates="saved_responses"`)

## EnvironmentModel

**Table:** `environments`
**Module:** `database.models.environments.model.environment_model`

Named variable sets for `{{variable}}` substitution.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `int` | Primary key | Auto-increment ID |
| `name` | `str` | String(255), indexed | Display name |
| `values` | `list[dict] \| None` | JSON | Variable key-value pairs |
| `created_at` | `datetime \| None` | Server default: `now()` | Creation timestamp |
| `updated_at` | `datetime \| None` | Server default: `now()`, onupdate | Last update timestamp |

**Relationships:** None (standalone model).

## JSON Column Schemas

### Variable entries (`CollectionModel.variables`, `EnvironmentModel.values`)

```python
{"key": "base_url", "value": "https://api.example.com", "enabled": True}
```

### Header/parameter entries (`RequestModel.headers`, `RequestModel.request_parameters`)

```python
{"key": "Content-Type", "value": "application/json", "enabled": True}
```

### Auth config (`CollectionModel.auth`, `RequestModel.auth`)

```python
{"type": "bearer", "bearer": {"token": "abc123"}}
{"type": "basic", "basic": {"username": "user", "password": "pass"}}
{"type": "inherit"}  # inherit from parent collection
```
