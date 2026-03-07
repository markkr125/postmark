---
name: test-writing
description: Guide for writing tests for Postmark components. Use when creating new test files, writing test classes, or adding test methods for widgets, services, or repository functions.
---

# Test writing guide

Step-by-step guide for writing tests in the Postmark project.  For core
test rules (fixtures, imports), see `testing.instructions.md`.

## Choosing the right test layer

| What you're testing | Test location | Fixtures needed |
|---------------------|---------------|-----------------|
| Repository function | `tests/unit/database/` | `_fresh_db` (autouse) |
| Service method | `tests/unit/services/` | `_fresh_db` (autouse) |
| UI widget | `tests/ui/<subpackage>/` | `qapp`, `qtbot`, `_fresh_db`, `_no_fetch` (all autouse) |
| MainWindow | `tests/ui/test_main_window.py` | `qapp`, `qtbot`, `_fresh_db`, `_no_fetch` (all autouse) |

## Repository test pattern

```python
from __future__ import annotations

from database.database import init_db
from database.models.collections.collection_repository import (
    create_new_collection,
    delete_collection,
    fetch_all_collections,
)


class TestMyFeature:
    def test_create_and_fetch(self) -> None:
        col = create_new_collection("Test Collection")
        result = fetch_all_collections()
        assert str(col.id) in result

    def test_delete_nonexistent_raises(self) -> None:
        # delete_collection silently succeeds for missing IDs
        delete_collection(999999)
```

## Service test pattern

```python
from __future__ import annotations

from services.collection_service import CollectionService


class TestCollectionServiceCreate:
    def test_create_strips_name(self) -> None:
        col = CollectionService.create_collection("  Padded  ")
        assert col.name == "Padded"

    def test_create_empty_name_raises(self) -> None:
        import pytest
        with pytest.raises(ValueError, match="empty"):
            CollectionService.create_collection("")
```

## UI widget test pattern

```python
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.my_widget import MyWidget


class TestMyWidget:
    def test_initial_state(self, qapp: QApplication, qtbot) -> None:
        widget = MyWidget()
        qtbot.addWidget(widget)
        assert widget.some_property == expected_value

    def test_signal_emission(self, qapp: QApplication, qtbot) -> None:
        widget = MyWidget()
        qtbot.addWidget(widget)
        with qtbot.waitSignal(widget.some_signal, timeout=1000):
            widget.trigger_action()
```

## Collection widget test pattern

`_no_fetch` is autouse in `tests/ui/` — no decorator needed.  Populate the
tree manually:

```python
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.collections.collection_widget import CollectionWidget
from ..conftest import make_collection_dict, top_level_items


class TestCollectionWidgetFeature:
    def test_tree_loads_data(self, qapp: QApplication, qtbot) -> None:
        widget = CollectionWidget()
        qtbot.addWidget(widget)

        data = make_collection_dict(
            {"id": 1, "name": "Folder A", "type": "folder", "children": {}},
        )
        widget._tree_widget.set_collections(data)

        items = top_level_items(widget._tree_widget._tree)
        assert len(items) == 1
```

## MainWindow test pattern

MainWindow tests are smoke tests — verify construction and basic wiring:

```python
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme_manager import ThemeManager


class TestMainWindowSmoke:
    def test_construction(self, qapp: QApplication, qtbot) -> None:
        tm = ThemeManager(qapp)
        window = MainWindow(tm)
        qtbot.addWidget(window)
        assert window.windowTitle()
```

## Test file placement rules

Mirror the source tree exactly:

| Source file | Test file |
|-------------|-----------|
| `src/ui/request/request_editor.py` | `tests/ui/request/test_request_editor.py` |
| `src/services/http_service.py` | `tests/unit/services/test_http_service.py` |
| `src/database/models/collections/collection_repository.py` | `tests/unit/database/test_repository.py` |

## Shared test helpers

These helpers are defined in `tests/ui/conftest.py`:

- `make_collection_dict(*items)` — Build a collection dict from item dicts
- `top_level_items(tree)` — Get all top-level `QTreeWidgetItem`s

Import them in subfolder tests via:

```python
from ..conftest import make_collection_dict, top_level_items
```

## After writing tests

Run the full validation suite:

```bash
poetry run pytest                          # all tests must pass
poetry run ruff check src/ tests/          # linter clean
poetry run ruff format --check src/ tests/ # formatter clean
poetry run mypy src/ tests/                # type checker clean
```
