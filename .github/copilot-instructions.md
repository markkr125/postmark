# Postmark — Copilot Instructions

## CRITICAL — Keeping instructions in sync

This file and the scoped instruction files below form a single source of
truth.

- **Check all instruction files for overlap** before editing any of them.
- **Never duplicate rules** across files — reference the canonical location.
- **Place rules in the most specific file** that applies. Only add rules here
  if they are truly project-wide.
- **Prefer creating new scoped instruction files** (under
  `.github/instructions/` with an `applyTo` glob) over adding to this file.

Scoped instruction files (auto-applied by path):

| File | Applies to |
|------|------------|
| [pyside6.instructions.md](./instructions/pyside6.instructions.md) | `src/ui/**/*.py` |
| [sqlalchemy.instructions.md](./instructions/sqlalchemy.instructions.md) | `src/database/**/*.py` |
| [architecture.instructions.md](./instructions/architecture.instructions.md) | `src/**/*.py` |
| [testing.instructions.md](./instructions/testing.instructions.md) | `tests/**/*.py` |

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
│   ├── collection_service.py      # CollectionService (static methods)
│   ├── import_service.py          # ImportService (parse + persist)
│   └── import_parser/             # Parser sub-package
│       ├── models.py              # TypedDict schemas for parsed data
│       ├── postman_parser.py      # Postman collection/environment parser
│       ├── curl_parser.py         # cURL command parser
│       └── url_parser.py          # URL/raw-text auto-detect parser
└── ui/                            # PySide6 widgets
    ├── main_window.py             # Top-level MainWindow
    ├── theme.py                   # Colours, method_color() helper
    ├── import_dialog.py           # Import dialog (files, cURL, paste)
    └── collections/               # Collection sidebar
        ├── collection_header.py
        ├── collection_widget.py
        └── tree/                  # Tree widget sub-package
            ├── constants.py
            ├── draggable_tree_widget.py
            └── collection_tree.py
tests/
├── conftest.py                    # Autouse fresh-DB fixture + qapp fixture
├── unit/                          # Repository & service layer tests
│   ├── test_repository.py
│   ├── test_service.py
│   ├── test_environment_repository.py
│   ├── test_import_parser.py
│   └── test_import_service.py
└── ui/                            # End-to-end PySide6 widget tests
    ├── conftest.py                # _no_fetch (autouse) + helpers
    ├── test_collection_header.py
    ├── test_collection_tree.py
    ├── test_collection_widget.py
    ├── test_import_dialog.py
    └── test_main_window.py
```

**Layering:** UI → signals → Service → Repository → `get_session()`.
UI must never import from `database/`.

## CRITICAL — Verify after every change

After **any** code change, run the **full** validation suite and confirm
**zero failures** before considering the task complete:

```bash
poetry run pytest                # all tests must pass
poetry run ruff check src/ tests/  # linter clean
poetry run mypy src/ tests/      # type checker clean
```

After **any** documentation change (`.md` files, instruction files, README),
run the markdown link checker and confirm **zero broken links**:

```bash
python scripts/check_md_links.py
```

Never skip a layer — repository, service, UI, and MainWindow tests all
must stay green.  See `testing.instructions.md` for detailed conventions.

## Coding conventions

- `from __future__ import annotations` in **every** module.
- `X | None`, not `Optional[X]`.
- Ruff is the linter **and** formatter (config in `pyproject.toml`).
  First-party packages for isort: `database`, `ui`, `services`.
- Named constants over magic numbers.
- `init_db()` must be called before any DB access (app startup and test fixture).
- Every module, class, and public function must have a docstring.
- All hex colour values belong in `src/ui/theme.py` -- never inline.
- Use `TypedDict` for dict schemas that cross module boundaries.
- No emoji in code comments -- use plain numbered steps (e.g. `# 1.`).
