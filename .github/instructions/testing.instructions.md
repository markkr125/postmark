---
name: "Testing Conventions"
description: "Pytest rules — fixtures, test structure, layer boundaries"
applyTo: "tests/**/*.py"
---

# Testing conventions

## Run tests

```bash
poetry run pytest
```

## Fresh database per test (autouse fixture)

`conftest.py` provides a `_fresh_db` fixture that resets the module-level
engine and creates a new SQLite file in `tmp_path` before every test. Tests
must **never** share database state.

When adding new conftest fixtures that touch the DB, keep the same pattern:

```python
import database.database as db_mod

db_mod._engine = None
db_mod._SessionLocal = None
init_db(tmp_path / "test.db")
```

## Test layers — what to test and how

| Layer | Import from | Notes |
|-------|-------------|-------|
| Repository | `database.models.collections.collections_utils` | Direct function calls, assert return values and DB side-effects |
| Service | `services.collection_service.CollectionService` | Instantiate the class, call methods, verify delegation works |
| UI | *not yet implemented* | Will require a `QApplication` fixture; do not add without one |

### Do NOT test the database engine or session factory directly

Test through the repository or service layer. The session is an implementation
detail managed by `get_session()`.

## Test file and class naming

- One test file per feature area: `tests/test_<feature>.py`
- Group related tests in classes: `TestCollectionCRUD`, `TestRequestCRUD`,
  `TestCollectionService`
- Prefix test methods with `test_`: `test_create_root_collection`

## Assertions and error testing

- Use plain `assert` — pytest rewrites them for rich diffs.
- Use `pytest.raises(ExceptionType, match="substring")` for expected errors.
- Avoid `try/except` in tests; let unexpected exceptions propagate.

## Imports

All imports use bare module names relative to `src/` (configured via
`pythonpath = ["src"]` in `pyproject.toml`):

```python
from database.models.collections.collections_utils import create_new_collection
from services.collection_service import CollectionService
```

## Coding style

- `from __future__ import annotations` in every test module.
- Follow the same ruff / type-checking rules as production code.
- Keep tests focused — one logical assertion per test method when practical.
- Use descriptive names: `test_delete_nonexistent_collection_raises` not
  `test_delete_error`.
