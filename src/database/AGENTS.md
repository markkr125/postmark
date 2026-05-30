# SQLAlchemy coding conventions

## Quick rules — read these first

1. **Use `Mapped` + `mapped_column()`**, never legacy `Column()`.
2. **Use `select()` + `session.execute()`**, never `session.query()`.
3. **Use `session.get(Model, pk)`**, never `session.query(Model).get(pk)`.
4. **Always use `get_session()` context manager** — never create sessions
   manually.
5. **Each repository function is its own transaction.** There is no way to
   batch multiple calls into one commit.
6. **Accessing relationships on a detached ORM object raises
   `DetachedInstanceError`.**  Convert to dicts inside the session for
   anything deeper than one level.
7. **All models inherit from `Base`** in `database/models/base.py`. Do not
   create a second base class.
8. **`init_db()` must complete before any DB access** — in production the
   collection fetch worker calls it before ``CollectionService.fetch_all()``;
   tests call it via the `_fresh_db` fixture. **`init_db()` is idempotent** —
   second and later calls no-op while `_engine` is set; tests reset `_engine` /
   `_SessionLocal` to `None` before each run (see `_fresh_db` in `conftest.py`).

## Use Mapped + mapped_column (2.0 style only)

Never use the legacy `Column()` API. Pylance infers `Column[int]` instead of
`int`, causing type errors everywhere the attribute is read.

```python
# WRONG — causes "Column[int]" is not assignable to "int" everywhere
id = Column(Integer, primary_key=True)
name = Column(String(255), nullable=False)

# CORRECT
id: Mapped[int] = mapped_column(primary_key=True, index=True)
name: Mapped[str] = mapped_column(String(255), index=True)
body: Mapped[str | None] = mapped_column(Text, default=None)
```

## Cross-model relationships need TYPE_CHECKING imports

Models live in separate files. Use `TYPE_CHECKING` to avoid circular imports:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .request_model import RequestModel

class CollectionModel(Base):
    requests: Mapped[list[RequestModel]] = relationship(...)
```

Because `from __future__ import annotations` is active, do **not** add quotes
around the type — `Mapped[list[RequestModel]]` is correct.

## Sessions use the get_session() context manager

Never create sessions manually or use a global session object:

```python
from database.database import get_session

def my_function():
    with get_session() as session:
        obj = session.get(MyModel, some_id)
        ...
```

`get_session()` auto-commits on success, rolls back on exception, and closes.
It uses `expire_on_commit=False` so detached objects stay usable after exit.

## Use session.get() not session.query().get()

The legacy `session.query(Model).get(id)` pattern is deprecated:

```python
# WRONG
obj = session.query(CollectionModel).get(collection_id)

# CORRECT
obj = session.get(CollectionModel, collection_id)
```

## Use select() for multi-row queries

Never use the legacy `session.query(Model).filter(...)` pattern. Use
`select()` + `session.execute()` instead:

```python
# WRONG
results = session.query(CollectionModel).filter(...).all()

# CORRECT
from sqlalchemy import select
stmt = select(CollectionModel).where(CollectionModel.parent_id.is_(None))
results = list(session.execute(stmt).scalars().all())
```

## init_db() — idempotent; must complete before any DB access

`init_db()` returns immediately if `_engine` is already created.

Production startup does not open the SQLite file on the main thread;
``CollectionWidget``'s background worker runs ``init_db()`` (no-op if already
initialised) before fetching collections. Tests use `_fresh_db` in
`conftest.py`, which resets `_engine` / `_SessionLocal` and calls
`init_db(db_path)` per test before widgets run.

## Session-per-function — no cross-function transactions

Every repository function opens and closes **its own session** via
`get_session()`.  There is no way to batch multiple repository calls into a
single transaction.  Each operation auto-commits independently.

If you need atomic multi-step logic, do it inside **one** repository function
with a single `with get_session() as session:` block.

## expire_on_commit=False — detached object rules

`get_session()` uses `expire_on_commit=False`.

**What works:** Scalar attributes (e.g. `obj.name`, `obj.id`) remain
readable after the session closes.

**What breaks:** Accessing relationships (e.g. `collection.children`,
`collection.requests`) on a detached object raises
`DetachedInstanceError`.  Both relationships use `lazy="selectin"` which
eagerly loads **one level** during the query — but deeper nesting fails.

**Fix:** Convert ORM objects to dicts **inside** the open session.  See
`_collections_to_dict` in `collection_repository.py`.

```python
# WRONG — accessing children after session close on a deep tree
with get_session() as session:
    roots = list(session.execute(stmt).scalars().all())
# roots[0].children works (selectin loaded), but
# roots[0].children[0].children may raise DetachedInstanceError

# CORRECT — convert inside the session
with get_session() as session:
    roots = list(session.execute(stmt).scalars().all())
    return _collections_to_dict(roots)   # runs while session is open
```

## DeclarativeBase lives in base.py

All models inherit from `Base` defined in `src/database/models/base.py`.
Do not create a second base class.

## Detached-object decision checklist

After the `get_session()` block exits, the ORM object is *detached*.
Use this quick checklist to decide whether to return the object or a dict:

| What you need after session close | Safe? | Action |
|---|---|---|
| Scalar attributes only (`id`, `name`, `body`, ...) | Yes | Return the ORM object directly |
| One-level eager relation (`collection.requests`) | Yes | `selectin` loads it during the query |
| Two+ levels deep (`coll.children[0].children`) | **No** | Convert to dict inside session |
| Relationship on an object from a different query | **No** | Re-query or join-load explicitly |

When in doubt, convert to a dict inside the open session.

## Lightweight schema migration — forward-only column additions

`database.py` contains `_migrate_add_missing_columns(engine)`, called by
`init_db()` after `create_all()`.  It handles existing databases that were
created before new columns were added to the ORM models.

**How it works:**

1. Inspects every mapped table with `sqlalchemy.inspect()`.
2. Compares existing on-disk columns against the ORM model.
3. Issues `ALTER TABLE <table> ADD COLUMN <col> <type>` for any missing
   columns.

**Rules:**

- This is **forward-only** — it never drops, renames, or alters existing
  columns (except the one-time ``snippets`` rebuild below).
- New columns added to any model are automatically picked up — no manual
  migration script needed.
- ``_migrate_drop_snippet_scope_columns`` (also in ``init_db()``) rebuilds
  ``snippets`` when legacy ``scope_collection_id`` / ``scope_local_script_id``
  columns exist on disk — SQLite cannot drop indexed FK columns in place.
- `create_all()` handles brand-new tables; the migration only applies to
  tables that already exist on disk but lack newly-added columns.
- The type mapping uses `col.type.compile(dialect=engine.dialect)` to derive
  the correct SQLite type string from the SQLAlchemy column type.

**When adding new columns to a model:**

1. Add the `Mapped` attribute with `mapped_column()` as usual.
2. Give it a sensible default (`default=None` or `server_default`) so
   existing rows with NULL values work correctly.
3. Run the app or tests — `_migrate_add_missing_columns` will add the column
   automatically. String ``server_default`` values are emitted as SQLite
   ``DEFAULT '…'`` plus ``NOT NULL`` when the column is non-nullable (see
   ``_migration_default_clause`` in ``database.py``).

```python
# Example: adding an optional "description" column to CollectionModel
description: Mapped[str | None] = mapped_column(Text, default=None)
```

## Database model catalogue

Core ORM models, all inheriting from `Base`:

| Model | Table | File |
|-------|-------|------|
| `CollectionModel` | `collections` | `database/models/collections/model/collection_model.py` |
| `RequestModel` | `requests` | `database/models/collections/model/request_model.py` |
| `SavedResponseModel` | `saved_responses` | `database/models/collections/model/saved_response_model.py` |
| `EnvironmentModel` | `environments` | `database/models/environments/model/environment_model.py` |
| `RunHistoryModel` | `run_history` | `database/models/runs/model/run_history_model.py` |
| `RunResultModel` | `run_results` | `database/models/runs/model/run_result_model.py` |
| `LocalScriptFolderModel` | `local_script_folders` | `database/models/local_scripts/model/local_script_folder_model.py` |
| `LocalScriptModel` | `local_scripts` | `database/models/local_scripts/model/local_script_model.py` |
| `SnippetModel` | `snippets` | `database/models/snippets/model/snippet_model.py` |
| `RequestAssertionModel` | `request_assertions` | `database/models/request_assertions/model/request_assertion_model.py` |

### Local scripts — `module_format`

``LocalScriptModel.module_format`` is ``"esm"`` (default) or ``"commonjs"``.
``LocalScriptModel.debug_metadata`` stores flat persisted breakpoints/watches
(JSON: ``breakpoints``, ``watches``; not nested under ``pre_request``/``test``).
Only JavaScript rows may use ``commonjs``; TypeScript/Python are coerced to
``esm`` in ``_normalize_module_format`` (repository). CommonJS scripts use
``.cjs`` virtual paths via ``script_virtual_extension()`` in
``virtual_paths.py``. Validation runs in ``create_script``,
``rename_script_and_rewrite_refs``, and ``update_script_content`` — not only
in the service layer.

### Re-exports in database.py

`database.py` re-exports collection, environment, run-history, local-script,
snippet, and request-assertion models using the `import X as X` pattern
(PEP 484 explicit re-export) so that `Base.metadata.create_all()` discovers
every table.  These imports must remain even though `database.py` itself
does not use the models directly.  Include ``LocalScriptFolderModel`` and
``LocalScriptModel`` when adding new tables under ``local_scripts/``.
