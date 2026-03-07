---
name: "Testing Conventions"
description: "Pytest rules — fixtures, test structure, layer boundaries"
applyTo: "tests/**/*.py"
---

# Testing conventions

## Quick rules — read these first

1. **Run `poetry run pytest` after every change** — all tests must pass.
2. **Also run `poetry run ruff check src/ tests/`,
   `poetry run ruff format --check src/ tests/`, and
   `poetry run mypy src/ tests/`** — see `copilot-instructions.md` for the
   full validation checklist.
3. **Each test gets a fresh SQLite database** — the `_fresh_db` autouse
   fixture handles this.  Never share DB state between tests.
4. **UI tests need `qapp` and `qtbot` fixtures.**  Register widgets with
   `qtbot.addWidget(widget)`.
5. **The `_no_fetch` fixture is autouse in `tests/ui/`** — it prevents
   `CollectionWidget` from spawning a background thread.  You do not need
   to apply it manually.
6. **Use bare module imports** (e.g. `from database.database import init_db`)
   — `src/` is on the Python path.
7. **Do not test the session or engine directly** — test through the
   repository or service layer.

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

`CollectionWidget.__init__` spawns a `QThread` that queries the database.
This breaks tests because:

1. **SQLite rejects cross-thread access** — the test DB is on the main
   thread; the worker thread gets `sqlite3.ProgrammingError`.
2. **The async fetch races with assertions** — the test may check the tree
   before loading finishes.

**How `_no_fetch` works:** It patches `CollectionWidget._start_fetch` to a
no-op so no background thread starts.

**How to populate the tree instead:** Call
`widget._tree_widget.set_collections(make_collection_dict(...))` directly.

`_no_fetch` is **autouse** within `tests/ui/` — every UI test gets the patch
automatically.  No decorator is needed:

```python
class TestCollectionWidget:
    ...
```

Only override `_no_fetch` for tests that intentionally verify the threading
behaviour (and configure SQLite for cross-thread access).

## Test layers — what to test and how

| Layer | Import from | Notes |
|-------|-------------|-------|
| Repository | `database.models.collections.collection_repository` | Direct function calls, assert return values and DB side-effects |
| Service | `services.collection_service.CollectionService` | Instantiate the class, call methods, verify delegation works |
| UI widgets | `ui.collections.*` | Use `qapp` + `qtbot` fixtures; `_no_fetch` is autouse |
| MainWindow | `ui.main_window.MainWindow` | Smoke tests only; `_no_fetch` is autouse |

### Do NOT test the database engine or session factory directly

Test through the repository or service layer. The session is an implementation
detail managed by `get_session()`.

## Directory layout

Test directories **mirror the source tree**.  Keep them in sync — when a
source file lives under `src/ui/request/`, its test lives under
`tests/ui/request/`.  Never dump new test files into `tests/ui/` or
`tests/unit/` root — always place them in the matching subfolder.

**Test file line limit:** Test files follow the same **600-line** cap as
source files.  When a source file is split into a sub-package, mirror the
split in the test directory — one test file per submodule.  If a single
test file still exceeds 600 lines, split by test class into separate files.

```
tests/
├── conftest.py                    # Root: _fresh_db (autouse) + qapp (session)
├── unit/                          # Pure logic — no Qt widgets
│   ├── database/                  # Repository layer tests
│   │   ├── test_repository.py
│   │   └── test_environment_repository.py
│   └── services/                  # Service layer tests
│       ├── test_service.py
│       ├── test_environment_service.py
│       ├── test_import_parser.py
│       ├── test_import_service.py
│       └── http/                  # HTTP service tests
│           ├── test_http_service.py
│           ├── test_graphql_schema_service.py
│           └── test_snippet_generator.py
└── ui/                            # PySide6 widget tests (need qapp + qtbot)
    ├── conftest.py                # _no_fetch (autouse) + helper functions
    ├── test_main_window.py        # Top-level MainWindow smoke tests
    ├── styling/                   # Theme and icon tests
    │   ├── test_theme_manager.py
    │   └── test_icons.py
    ├── widgets/                   # Shared component tests
    │   ├── test_code_editor.py
    │   ├── test_code_editor_memory.py
    │   ├── test_info_popup.py
    │   ├── test_key_value_table.py
    │   ├── test_variable_line_edit.py
    │   └── test_variable_popup.py
    ├── collections/               # Collection sidebar tests
    │   ├── test_collection_header.py
    │   ├── test_collection_tree.py
    │   ├── test_collection_tree_delegate.py
    │   └── test_collection_widget.py
    ├── dialogs/                   # Dialog tests
    │   ├── test_import_dialog.py
    │   └── test_settings_dialog.py
    ├── environments/              # Environment widget tests
    │   ├── test_environment_editor.py
    │   └── test_environment_selector.py
    ├── panels/                    # Panel tests
    │   ├── test_console_panel.py
    │   └── test_history_panel.py
    └── request/                   # Request/response editing tests
        ├── test_folder_editor.py
        ├── test_http_worker.py
        ├── test_request_editor.py
        ├── test_response_viewer.py
        ├── navigation/            # Tab and breadcrumb tests
        │   ├── test_breadcrumb_bar.py
        │   ├── test_request_tab_bar.py
        │   └── test_tab_manager.py
        └── popups/                # Response popup tests
            ├── test_status_popup.py
            ├── test_timing_popup.py
            ├── test_size_popup.py
            └── test_network_popup.py
```

- **unit/database/** — repository tests. No Qt dependency.
- **unit/services/** — service layer tests. No Qt dependency.
- **unit/services/http/** — HTTP, GraphQL, and snippet service tests.
- **ui/** — widget integration tests grouped by source subpackage.
- **ui/styling/** — theme and icon tests.
- **ui/widgets/** — shared component tests.

When adding tests for a new widget, create the file in the matching
`tests/ui/<subpackage>/` folder.  When adding tests for a new service or
repository, add to the matching `tests/unit/<subpackage>/` folder.

## Test file and class naming

- One test file per component, placed in the matching subfolder:
  `tests/ui/request/test_request_editor.py`,
  `tests/unit/services/test_service.py`
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
`tests/ui/conftest.py` and can be imported via relative import from any
subfolder:

```python
from ..conftest import make_collection_dict, top_level_items
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
from ui.collections.tree import CollectionTree, ROLE_ITEM_ID
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
