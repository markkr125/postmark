# Postmark — Copilot Instructions

## CRITICAL — Keeping instructions in sync

This file and the three scoped instruction files below form a single source of
truth. **Before editing any instruction file, check the others for overlap or
contradiction.** Never duplicate rules across files — reference the canonical
location instead. When adding a new convention, place it in the most specific
file that applies; only add it here if it is truly project-wide.

**Prefer creating new scoped instruction files** over adding content to this
file. This file should stay thin — project-wide basics only. If a rule applies
to a specific path or technology, create (or extend) a dedicated file under
`.github/instructions/` with an appropriate `applyTo` glob.

Scoped instruction files (auto-applied by path):

| File | Applies to |
|------|------------|
| [pyside6.instructions.md](instructions/pyside6.instructions.md) | `src/ui/**/*.py` |
| [sqlalchemy.instructions.md](instructions/sqlalchemy.instructions.md) | `src/database/**/*.py` |
| [testing.instructions.md](instructions/testing.instructions.md) | `tests/**/*.py` |

## Project overview

**Postmark** — native desktop API client built with **PySide6**, **SQLAlchemy 2.0**, **Python 3.12+**, managed by **Poetry**.

```bash
poetry install --with dev   # pytest, ruff, mypy
poetry run python src/main.py
poetry run ruff check src/ && poetry run ruff format src/
poetry run mypy src/
poetry run pytest
```

`src/` is the source root for all tools (`pythonpath`, `mypy_path`,
`extraPaths` in `pyproject.toml`). Imports use bare module names:
`from database.database import init_db`.

## Architecture

```
src/
├── main.py                        # Entry point — QApplication + init_db()
├── database/                      # Engine, models, repository
├── services/                      # Service layer (UI ↔ DB bridge)
└── ui/                            # PySide6 widgets
tests/
├── conftest.py                    # Autouse fresh-DB fixture
└── test_collections.py
```

**Layering:** UI → signals → Service → Repository → `get_session()`.
UI must never import from `database/`.

## Coding conventions

- `from __future__ import annotations` in **every** module.
- `X | None`, not `Optional[X]`.
- Ruff is the linter **and** formatter (config in `pyproject.toml`).
  First-party packages for isort: `database`, `ui`, `services`.
- Named constants over magic numbers.
- `init_db()` must be called before any DB access (app startup and test fixture).
