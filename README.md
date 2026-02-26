# Postmark

A native desktop API client for testing and managing HTTP requests, built with **PySide6** and **SQLAlchemy**.

## Features

- Organise requests into nested collections (folders)
- Drag-and-drop to rearrange collections and requests
- In-place rename with rollback on failure
- Background data loading (non-blocking UI)
- SQLite persistence via SQLAlchemy

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
├── main.py                          # Application entry point
├── database/
│   ├── database.py                  # Engine, session, init_db()
│   └── models/
│       ├── base.py                  # SQLAlchemy DeclarativeBase
│       └── collections/
│           ├── collection_repository.py # Repository (CRUD operations)
│           └── model/
│               ├── collection_model.py
│               └── request_model.py
├── services/
│   └── collection_service.py        # Service layer between UI ↔ DB
└── ui/
    └── collections/
        ├── collection_header.py     # Import / add / search bar
        ├── collection_tree.py       # Tree widget with drag-and-drop
        └── collection_widget.py     # Composite widget (header + tree)
tests/
└── ...
```
