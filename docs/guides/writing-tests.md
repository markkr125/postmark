# Writing Tests

How to write tests for application components across all layers.

## Test Structure

```
tests/
  conftest.py          # fresh-DB fixture, qapp, tab-settings reset
  unit/
    database/          # Repository tests
    services/          # Service layer tests
  ui/
    conftest.py        # _no_fetch autouse, helpers
    collections/       # Collection widget tests
    dialogs/           # Dialog tests
    environments/      # Environment widget tests
    panels/            # Panel tests
    request/           # Request/response tests
    sidebar/           # Sidebar tests
    styling/           # Theme tests
    widgets/           # Shared widget tests
```

## Fixtures

### Root conftest.py

- `fresh_db` (autouse, session) — calls `init_db()` with in-memory
  SQLite, resets between test sessions
- `qapp` — `QApplication` instance for Qt tests
- `tab_settings_reset` (autouse) — resets `TabSettingsManager` state
- `make_collection_with_request` — factory for creating a collection
  with one request in the database

### UI conftest.py

- `_no_fetch` (autouse) — patches `CollectionWidget._start_fetch` to
  prevent background collection loading during tests
- Helper functions for widget creation

### Request conftest.py

- `make_request_dict` — factory for creating `RequestLoadDict` test
  data

## Repository Tests

Test database CRUD functions directly with `get_session()`.

```python
from __future__ import annotations

from database.models.collections.collection_repository import (
    create_collection,
    get_collection,
)


class TestCreateCollection:
    """Tests for create_collection."""

    def test_create_basic(self) -> None:
        coll = create_collection("Test")
        assert coll.name == "Test"
        assert coll.id is not None

    def test_create_with_parent(self) -> None:
        parent = create_collection("Parent")
        child = create_collection("Child", parent_id=parent.id)
        assert child.parent_id == parent.id
```

## Service Tests

Test service methods, mocking the repository layer when needed.

```python
from __future__ import annotations

from services.collection_service import CollectionService


class TestCollectionService:
    """Tests for CollectionService."""

    def test_get_request_data(self) -> None:
        coll = CollectionService.create_collection("C")
        req = CollectionService.create_request("R", coll["id"])
        data = CollectionService.get_request(req["id"])
        assert data["name"] == "R"
```

## Widget Tests

Use `pytest-qt` and the `qtbot` fixture.

```python
from __future__ import annotations

from PySide6.QtCore import Qt

from ui.widgets.key_value_table import KeyValueTableWidget


class TestKeyValueTable:
    """Tests for KeyValueTableWidget."""

    def test_add_row(self, qtbot) -> None:
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        widget.show()

        # Interact and verify
        assert widget.rowCount() >= 1

    def test_data_changed_signal(self, qtbot) -> None:
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)

        with qtbot.waitSignal(widget.data_changed, timeout=1000):
            # Trigger a change
            widget._add_row()
```

## MainWindow Tests

Use `make_collection_with_request` for setup, then test signal
flows end-to-end.

```python
from __future__ import annotations

from ui.main_window.window import MainWindow


class TestMainWindowOpen:
    """Tests for opening requests in MainWindow."""

    def test_open_request(self, qtbot, make_collection_with_request) -> None:
        coll, req = make_collection_with_request("C", "R")
        win = MainWindow()
        qtbot.addWidget(win)

        win._open_request(req.id)
        assert win._tab_bar.count() == 1
```

## Conventions

1. Every test class has a docstring
2. Test method names: `test_<behaviour>` or `test_<method>_<scenario>`
3. Use `qtbot.addWidget(w)` for cleanup
4. Use `qtbot.waitSignal(sig)` to verify signal emission
5. Use `qtbot.keyClick(widget, key)` for keyboard interaction
6. Mock network calls — never make real HTTP requests in tests
7. Use `monkeypatch` for patching, not `unittest.mock.patch`
   (unless `monkeypatch` is insufficient)
8. All test files must have `from __future__ import annotations`

## Layer Boundaries

- Repository tests: access database directly via `get_session()`
- Service tests: call service methods (may use real DB)
- Widget tests: create widgets with `qtbot`, verify visual state
- MainWindow tests: end-to-end signal flow verification
- UI tests must never import from `database/` directly
