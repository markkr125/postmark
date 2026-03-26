# Testing Guide

How to run tests and what is expected to pass.

## Running Tests

```bash
# All tests
poetry run pytest

# Specific test file
poetry run pytest tests/unit/services/test_service.py

# Specific test class
poetry run pytest tests/ui/test_main_window.py::TestMainWindowOpen

# With verbose output
poetry run pytest -v

# Stop on first failure
poetry run pytest -x
```

## Full Validation Suite

All four commands must pass with zero errors after every change:

```bash
poetry run pytest                          # all tests
poetry run ruff check src/ tests/          # linter
poetry run ruff format --check src/ tests/ # formatter
poetry run mypy src/ tests/                # type checker
```

Pre-existing errors are not acceptable — fix them immediately.

## Test Layers

| Layer | Directory | Tests |
|-------|-----------|-------|
| Repository | `tests/unit/database/` | Direct DB CRUD |
| Service | `tests/unit/services/` | Service method logic |
| Widget | `tests/ui/` | PySide6 widget behaviour |
| MainWindow | `tests/ui/test_main_window*.py` | End-to-end flows |

## Key Fixtures

| Fixture | Scope | Location | Description |
|---------|-------|----------|-------------|
| `fresh_db` | session | root conftest | In-memory SQLite, autouse |
| `qapp` | session | root conftest | QApplication instance |
| `tab_settings_reset` | function | root conftest | Reset TabSettingsManager |
| `_no_fetch` | function | ui conftest | Patch collection loading |
| `make_collection_with_request` | function | root conftest | Factory for test data |
| `make_request_dict` | function | request conftest | Factory for RequestLoadDict |

## Widget Test Pattern

```python
from __future__ import annotations

from ui.widgets.my_widget import MyWidget


class TestMyWidget:
    """Tests for MyWidget."""

    def test_initial_state(self, qtbot) -> None:
        widget = MyWidget()
        qtbot.addWidget(widget)
        assert widget.isVisible() is False

    def test_signal_emission(self, qtbot) -> None:
        widget = MyWidget()
        qtbot.addWidget(widget)
        with qtbot.waitSignal(widget.my_signal, timeout=1000):
            widget._trigger_action()
```

## Conventions

1. `from __future__ import annotations` in every test file
2. Every test class has a docstring
3. Method names: `test_<behaviour>` or `test_<method>_<scenario>`
4. Use `qtbot.addWidget(w)` for widget cleanup
5. Mock network calls — never make real HTTP requests
6. Use `monkeypatch` for patching
7. UI tests must never import from `database/`
