<p align="center">
  <img src="data/images/logo.png" alt="Postmark logo" width="200" />
</p>

# Postmark

A native desktop API client for testing and managing HTTP requests, built with **PySide6** and **SQLAlchemy**.

## Features

- Organise requests into nested collections (folders)
- Drag-and-drop to rearrange collections and requests
- In-place rename with rollback on failure
- Background data loading (non-blocking UI)
- SQLite persistence via SQLAlchemy
- **Theme support** — automatic OS dark/light mode detection, with manual override
- **Settings dialog** — choose between Fusion (default) and native OS widget style
- Import from Postman collections, cURL commands, or raw URLs
- Environment variables with key-value editor
- Code snippet generation
- Console and history panels

## Prerequisites

- Python 3.12+
- [Poetry](https://python-poetry.org/) for dependency management

## Setup

```bash
# Clone the repository
git clone <repo-url> && cd postmark

# Install dependencies (creates a virtualenv in .venv/)
poetry install

# Install dev tools (linter, type checker, test runner)
poetry install --with dev
```

## Running

```bash
poetry run python src/main.py
```

Or use the VS Code task **Run main with Poetry** (`Ctrl+Shift+B`).

## Development

```bash
# Lint
poetry run ruff check src/

# Format
poetry run ruff format src/

# Type check
poetry run mypy src/

# Run tests
poetry run pytest
```

## Project Structure

```
src/
├── main.py                        # Application entry point
├── database/
│   ├── database.py                # Engine, session, init_db()
│   └── models/
│       ├── base.py                # SQLAlchemy DeclarativeBase
│       ├── collections/
│       │   ├── collection_repository.py   # CRUD for collections + requests
│       │   ├── import_repository.py       # Atomic bulk-import
│       │   └── model/
│       │       ├── collection_model.py
│       │       ├── request_model.py
│       │       └── saved_response_model.py
│       └── environments/
│           ├── environment_repository.py
│           └── model/
│               └── environment_model.py
├── services/
│   ├── collection_service.py      # Service layer (UI ↔ DB bridge)
│   ├── environment_service.py
│   ├── http_service.py
│   ├── import_service.py          # Parse + persist imports
│   ├── snippet_generator.py
│   └── import_parser/             # Parser sub-package
│       ├── models.py
│       ├── postman_parser.py
│       ├── curl_parser.py
│       └── url_parser.py
└── ui/
    ├── main_window.py             # Top-level MainWindow
    ├── theme.py                   # Palettes, colours, badge geometry
    ├── theme_manager.py           # ThemeManager — QPalette + global QSS + QSettings
    ├── key_value_table.py         # Reusable key-value editor widget
    ├── collections/
    │   ├── collection_header.py
    │   ├── collection_widget.py
    │   └── tree/
    │       ├── constants.py
    │       ├── draggable_tree_widget.py
    │       └── collection_tree.py
    ├── dialogs/
    │   ├── code_snippet_dialog.py
    │   ├── collection_runner.py
    │   ├── import_dialog.py
    │   └── settings_dialog.py     # Settings (theme, colour scheme)
    ├── environments/
    │   ├── environment_editor.py
    │   └── environment_selector.py
    ├── panels/
    │   ├── console_panel.py
    │   └── history_panel.py
    └── request/
        ├── breadcrumb_bar.py
        ├── http_worker.py
        ├── request_editor.py
        ├── request_tab_bar.py
        ├── response_viewer.py
        └── tab_manager.py
tests/
├── conftest.py                    # Autouse fresh-DB fixture + qapp
├── unit/                          # Repository & service layer tests
│   ├── database/
│   └── services/
└── ui/                            # PySide6 widget integration tests
    ├── conftest.py                # _no_fetch (autouse) + helpers
    ├── test_main_window.py
    ├── test_theme_manager.py
    ├── test_key_value_table.py
    ├── collections/
    ├── dialogs/
    ├── environments/
    ├── panels/
    └── request/
```
