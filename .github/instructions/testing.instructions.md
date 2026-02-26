---
name: "Testing Conventions"
description: "Pytest rules — fixtures, test structure, layer boundaries"
applyTo: "tests/**/*.py"
---

# Testing conventions

## CRITICAL — Run the full suite after every change

After **any** code change (bug fix, refactor, new feature) run the complete
test suite and verify **zero failures** before considering the task done:

```bash
poetry run pytest
```

Also run the linter and type checker:

```bash
poetry run ruff check src/ tests/
poetry run mypy src/ tests/
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

## QApplication fixture (session-scoped)

`conftest.py` provides a `qapp` fixture (session-scoped) that returns the
single `QApplication` instance. All UI tests must accept `qapp` and use
`qtbot.addWidget(widget)` for cleanup.

## `_no_fetch` fixture — avoiding background threads in tests

`CollectionWidget.__init__` spawns a `QThread` to fetch collections from
the database.  SQLite rejects cross-thread access by default, so tests that
construct a `CollectionWidget` (or `MainWindow`) must apply the `_no_fetch`
fixture (defined in `tests/ui/conftest.py`), which patches `_start_fetch`
to a no-op:

```python
@pytest.mark.usefixtures("_no_fetch")
class TestCollectionWidget:
    ...
```

Only omit `_no_fetch` for tests that intentionally verify the threading
behaviour (and configure SQLite for cross-thread access).

## Test layers — what to test and how

| Layer | Import from | Notes |
|-------|-------------|-------|
| Repository | `database.models.collections.collection_repository` | Direct function calls, assert return values and DB side-effects |
| Service | `services.collection_service.CollectionService` | Instantiate the class, call methods, verify delegation works |
| UI widgets | `ui.collections.*` | Use `qapp` + `qtbot` fixtures; apply `_no_fetch` for widgets that spawn threads |
| MainWindow | `main.MainWindow` | Smoke tests only; apply `_no_fetch` |

### Do NOT test the database engine or session factory directly

Test through the repository or service layer. The session is an implementation
detail managed by `get_session()`.

## Directory layout

```
tests/
├── conftest.py                    # Root: _fresh_db (autouse) + qapp (session)
├── unit/                          # Pure logic — no Qt widgets
│   ├── test_repository.py         # TestCollectionCRUD, TestRequestCRUD
│   └── test_service.py            # TestCollectionService
└── ui/                            # PySide6 widget tests (need qapp + qtbot)
    ├── conftest.py                # _no_fetch fixture + helper functions
    ├── test_collection_header.py
    ├── test_collection_tree.py
    ├── test_collection_widget.py
    └── test_main_window.py
```

- **unit/** — repository and service layer tests. No Qt dependency.
- **ui/** — widget integration tests. Each widget gets its own file.

When adding tests for a new widget, create `tests/ui/test_<widget>.py`.
When adding tests for a new service or repository, add to or create a
file under `tests/unit/`.

## Test file and class naming

- One test file per component: `tests/ui/test_<widget>.py`,
  `tests/unit/test_<layer>.py`
- Group related tests in classes: `TestCollectionCRUD`, `TestRequestCRUD`,
  `TestCollectionService`, `TestCollectionTree`, `TestCollectionWidget`
- Prefix test methods with `test_`: `test_create_root_collection`

## UI test patterns

When testing PySide6 widgets:

1. Accept `qapp` and `qtbot` as fixtures.
2. Create the widget and register it with `qtbot.addWidget(widget)`.
3. Use `qtbot.waitSignal` to assert that a signal was emitted.
4. Populate tree data via `set_collections(make_collection_dict(...))`.
5. Assert tree state via `top_level_items(tree)`, `item.data(col, ROLE)`, etc.
6. For signal-to-service integration, emit signals directly on the tree widget
   and verify the DB changed via `CollectionService`.

Shared helpers (`make_collection_dict`, `top_level_items`) live in
`tests/ui/conftest.py` and can be imported via relative import:

```python
from .conftest import make_collection_dict, top_level_items
```

## Assertions and error testing

- Use plain `assert` — pytest rewrites them for rich diffs.
- Use `pytest.raises(ExceptionType, match="substring")` for expected errors.
- Avoid `try/except` in tests; let unexpected exceptions propagate.

## Imports

All imports use bare module names relative to `src/` (configured via
`pythonpath = ["src"]` in `pyproject.toml`):

```python
from database.models.collections.collection_repository import create_new_collection
from services.collection_service import CollectionService
from ui.collections.collection_tree import CollectionTree, ROLE_ITEM_ID
```

## Coding style

- `from __future__ import annotations` in every test module.
- Follow the same ruff / type-checking rules as production code.
- Keep tests focused -- one logical assertion per test method when practical.
- Use descriptive names: `test_delete_nonexistent_collection_raises` not
  `test_delete_error`.

## Temporary directories

Use pytest's built-in `tmp_path` fixture. Do **not** import
`tempfile.TemporaryDirectory` -- `tmp_path` handles cleanup automatically.
