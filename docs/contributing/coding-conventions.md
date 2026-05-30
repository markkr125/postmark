# Coding Conventions

Rules and patterns enforced across the codebase.

## Python Version

Python 3.12+.  Every module starts with:

```python
from __future__ import annotations
```

## Type Annotations

Use modern union syntax:

```python
# Correct
def get(id: int) -> dict | None: ...

# Wrong
from typing import Optional
def get(id: int) -> Optional[dict]: ...
```

## Imports

Source root is `src/`.  Use bare module names:

```python
from database.database import get_session
from services.collection_service import CollectionService
from ui.styling.theme import current_palette
```

First-party packages for isort: `database`, `ui`, `services`.

## Linting and Formatting

Ruff is both linter and formatter.  Configuration in `pyproject.toml`.

```bash
poetry run ruff check src/ tests/       # lint
poetry run ruff format --check src/ tests/  # format check
poetry run mypy src/ tests/             # type check
```

All three must pass with zero errors before any change is merged.

## Docstrings

Every module, class, and public function must have a docstring.

## Named Constants

Use named constants over magic numbers:

```python
# Correct
MAX_HISTORY_ENTRIES = 50
if len(entries) > MAX_HISTORY_ENTRIES:

# Wrong
if len(entries) > 50:
```

## Colour Values

All hex colour values belong in `src/ui/styling/theme.py`.  Never
inline colours in widget code.

## TypedDicts

Use `TypedDict` for dict schemas that cross module boundaries.
Define them in the owning service module and re-export from the
package `__init__.py`.

## Comments

No emoji in code comments.  Use plain numbered steps:

```python
# 1. Fetch the collection tree
# 2. Filter by search term
# 3. Update the tree widget
```

## File Limits

- **5 `.py` files per directory** (excluding `__init__.py`).  When
  a directory reaches this limit, extract a sub-package.
- **600 lines per file** (including docstrings and comments).
  Extract cohesive method groups into sub-modules.  Re-export public
  symbols from `__init__.py`.

Test directories mirror the source tree.  Test file count may exceed
5 when multiple test files cover a single source module.

## Layer Boundaries

```
UI -> Service -> Repository -> get_session()
```

UI must never import from `database/`.  Services mediate all data
access.

## Database Access

`init_db()` must complete before any DB access (worker thread at startup;
`_fresh_db` in tests).  It is idempotent once the engine exists.  Always use
`get_session()` for session lifecycle.
