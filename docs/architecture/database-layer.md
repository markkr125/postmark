# Database Layer

The database layer manages persistence using SQLAlchemy 2.0 with a local
SQLite database.

## Engine and Initialisation

The database is managed by module-level state in
`src/database/database.py`:

```text
init_db(db_path=None)
  1. Resolve db_path (default: data/database/main.db)
  2. Create SQLAlchemy Engine with SQLite
  3. Enable WAL journal mode (PRAGMA journal_mode=WAL)
  4. Run Base.metadata.create_all() -- creates tables if missing
  5. Run _migrate_add_missing_columns() -- forward-only migration
  6. Create sessionmaker factory (expire_on_commit=False)
```

**WAL mode** enables concurrent read access from worker threads while
the main thread writes.

**`expire_on_commit=False`** ensures ORM instances remain readable after
the session commits and closes — critical for passing detached objects
back to the service and UI layers.

## Session Management

All database access uses the `get_session()` context manager:

```python
@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

**Rules:**
- Every repository function creates its own session — no long-lived
  sessions.
- Never create `Session()` manually — always use `get_session()`.
- `init_db()` must be called before any database access (app startup and
  test fixtures).

## Forward-Only Migration

When new columns are added to ORM models, `_migrate_add_missing_columns()`
automatically issues `ALTER TABLE ADD COLUMN` for any columns that exist
in the model but are absent on disk.  This avoids the need for a full
migration framework (like Alembic) for simple additive changes.

**Limitations:** Never drops or renames columns.  Schema changes requiring
column removal or rename need manual handling.

## Model Relationships

```text
CollectionModel (collections table)
  |
  +-- parent_id --> CollectionModel (self-referential, nullable)
  |                 .children: list[CollectionModel]
  |
  +-- .requests: list[RequestModel]
        |
        RequestModel (requests table)
          |
          +-- collection_id --> CollectionModel
          |
          +-- .saved_responses: list[SavedResponseModel]
                |
                SavedResponseModel (saved_responses table)
                  +-- request_id --> RequestModel

EnvironmentModel (environments table)
  (standalone -- no foreign keys to other tables)
```

## ORM Models

Four models, all inheriting from `Base` (SQLAlchemy `DeclarativeBase`):

| Model | Table | Purpose |
|-------|-------|---------|
| `CollectionModel` | `collections` | Folders in the collection tree |
| `RequestModel` | `requests` | HTTP requests with method, URL, body, headers, auth |
| `SavedResponseModel` | `saved_responses` | Named response snapshots attached to requests |
| `EnvironmentModel` | `environments` | Named variable sets (key-value pairs) |

See [ORM Models](../api-reference/database/models.md) for complete column
definitions.

## Repository Organisation

Repository functions are split by concern:

| Module | Responsibility |
|--------|---------------|
| `collection_repository.py` | Mutations — create, rename, delete, update, move |
| `collection_query_repository.py` | Queries — fetch all, get by ID, breadcrumbs, auth chains, variables |
| `import_repository.py` | Atomic bulk-import of parsed collection trees |
| `environment_repository.py` | Full CRUD for environments |

See the [API Reference](../api-reference/database/) for function-level
documentation.

## JSON Columns

Several columns store structured data as JSON:

| Model | Column | Schema |
|-------|--------|--------|
| `CollectionModel` | `variables` | `list[{"key": str, "value": str}]` |
| `CollectionModel` | `auth` | `{"type": str, ...type-specific fields}` |
| `CollectionModel` | `events` | `dict[str, Any]` (pre/post-request scripts) |
| `RequestModel` | `request_parameters` | `list[{"key": str, "value": str, "enabled": bool}]` |
| `RequestModel` | `headers` | `list[{"key": str, "value": str, "enabled": bool}]` |
| `RequestModel` | `body_options` | `dict[str, Any]` (body encoding/format settings) |
| `RequestModel` | `auth` | `{"type": str, ...type-specific fields}` |
| `RequestModel` | `scripts` | `{"pre_request": str, "test": str, "language": str}` |
| `RequestModel` | `settings` | `dict[str, Any]` |
| `RequestModel` | `events` | `dict[str, Any]` |
| `SavedResponseModel` | `headers` | `list[{"key": str, "value": str}]` |
| `SavedResponseModel` | `original_request` | `dict[str, Any]` (snapshot of request at save time) |
| `EnvironmentModel` | `values` | `list[{"key": str, "value": str, "enabled": bool}]` |
