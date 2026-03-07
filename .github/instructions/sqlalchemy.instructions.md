---
name: "SQLAlchemy Conventions"
description: "SQLAlchemy 2.0 model and session rules — Mapped columns, session management, relationships"
applyTo: "src/database/**/*.py"
---

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
8. **`init_db()` must be called before any DB access** — at app startup and
   in test fixtures.

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

## init_db() must be called before any DB access

`main.py` calls `init_db(db_path)` at startup. Tests use an autouse fixture
in `conftest.py` that resets the engine and calls `init_db()` per test.

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
  columns.
- New columns added to any model are automatically picked up — no manual
  migration script needed.
- `create_all()` handles brand-new tables; the migration only applies to
  tables that already exist on disk but lack newly-added columns.
- The type mapping uses `col.type.compile(dialect=engine.dialect)` to derive
  the correct SQLite type string from the SQLAlchemy column type.

**When adding new columns to a model:**

1. Add the `Mapped` attribute with `mapped_column()` as usual.
2. Give it a sensible default (`default=None` or `server_default`) so
   existing rows with NULL values work correctly.
3. Run the app or tests — `_migrate_add_missing_columns` will add the column
   automatically.

```python
# Example: adding an optional "description" column to CollectionModel
description: Mapped[str | None] = mapped_column(Text, default=None)
```

## Database model catalogue

Four ORM models, all inheriting from `Base`:

| Model | Table | File |
|-------|-------|------|
| `CollectionModel` | `collections` | `database/models/collections/model/collection_model.py` |
| `RequestModel` | `requests` | `database/models/collections/model/request_model.py` |
| `SavedResponseModel` | `saved_responses` | `database/models/collections/model/saved_response_model.py` |
| `EnvironmentModel` | `environments` | `database/models/environments/model/environment_model.py` |

### Re-exports in database.py

`database.py` re-exports all four models using the `import X as X` pattern
(PEP 484 explicit re-export) so that `Base.metadata.create_all()` discovers
every table.  These imports must remain even though `database.py` itself
does not use the models directly.
