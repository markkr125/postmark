---
name: "SQLAlchemy Conventions"
description: "SQLAlchemy 2.0 model and session rules — Mapped columns, session management, relationships"
applyTo: "src/database/**/*.py"
---

# SQLAlchemy coding conventions

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

## DeclarativeBase lives in base.py

All models inherit from `Base` defined in `src/database/models/base.py`.
Do not create a second base class.
