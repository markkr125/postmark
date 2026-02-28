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
│   ├── database.py                # init_db(), get_session(), migration
│   └── models/
│       ├── base.py                # DeclarativeBase
│       ├── collections/
│       │   ├── collection_repository.py   # CRUD for collections + requests
│       │   ├── import_repository.py       # Atomic bulk-import of parsed data
│       │   └── model/
│       │       ├── collection_model.py    # CollectionModel (folders)
│       │       ├── request_model.py       # RequestModel (HTTP requests)
│       │       └── saved_response_model.py
│       └── environments/
│           ├── environment_repository.py  # CRUD for environments
│           └── model/
│               └── environment_model.py   # EnvironmentModel (key-value sets)
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
    ├── theme.py                   # Palettes, colours, badge geometry, method_color()
    ├── theme_manager.py           # ThemeManager — QPalette + global QSS + QSettings
    ├── icons.py                   # Phosphor font-glyph icon provider (phi())
    ├── key_value_table.py         # Reusable key-value editor widget
    ├── collections/               # Collection sidebar
    │   ├── collection_header.py
    │   ├── collection_widget.py
    │   └── tree/                  # Tree widget sub-package
    │       ├── constants.py
    │       ├── draggable_tree_widget.py
    │       └── collection_tree.py
    ├── dialogs/                   # Modal dialogs
    │   ├── code_snippet_dialog.py
    │   ├── collection_runner.py
    │   ├── import_dialog.py
    │   └── settings_dialog.py     # Settings (theme, colour scheme)
    ├── environments/              # Environment management widgets
    │   ├── environment_editor.py
    │   └── environment_selector.py
    ├── panels/                    # Bottom / side panels
    │   ├── console_panel.py
    │   └── history_panel.py
    └── request/                   # Request/response editing
        ├── breadcrumb_bar.py
        ├── http_worker.py
        ├── request_editor.py
        ├── request_tab_bar.py
        ├── response_viewer.py
        └── tab_manager.py
tests/
├── conftest.py                    # Autouse fresh-DB fixture + qapp fixture
├── unit/                          # Repository & service layer tests
│   ├── database/                  # Repository tests
│   │   ├── test_repository.py
│   │   └── test_environment_repository.py
│   └── services/                  # Service layer tests
│       ├── test_service.py
│       ├── test_environment_service.py
│       ├── test_http_service.py
│       ├── test_import_parser.py
│       ├── test_import_service.py
│       └── test_snippet_generator.py
└── ui/                            # End-to-end PySide6 widget tests
    ├── conftest.py                # _no_fetch (autouse) + helpers
    ├── test_main_window.py
    ├── test_theme_manager.py
    ├── test_icons.py
    ├── test_key_value_table.py
    ├── collections/               # Collection sidebar tests
    │   ├── test_collection_header.py
    │   ├── test_collection_tree.py
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
        ├── test_breadcrumb_bar.py
        ├── test_http_worker.py
        ├── test_request_editor.py
        ├── test_request_tab_bar.py
        ├── test_response_viewer.py
        └── test_tab_manager.py
```

**Layering:** UI → signals → Service → Repository → `get_session()`.
UI must never import from `database/`.

## CRITICAL — Verify after every change

After **any** code change, run the **full** validation suite and confirm
**zero failures** before considering the task complete:

```bash
poetry run pytest                          # all tests must pass
poetry run ruff check src/ tests/          # linter clean
poetry run ruff format --check src/ tests/ # formatter clean
poetry run mypy src/ tests/                # type checker clean
```

**NEVER use `--fix` or auto-format as a substitute for the checks above.**
Always run the check-only commands first. If they fail, fix the code
manually (or with `--fix`), then **re-run the check-only commands** and
confirm they pass. The goal is to surface every issue visibly — a silent
auto-fix that is never re-verified can leave the working tree clean while
the staged/committed version is still broken.

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
