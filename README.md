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
- Environment variables with key-value editor and `{{var}}` substitution
- **GraphQL support** — schema introspection, syntax highlighting, and prettify
- **Code editor** — syntax highlighting, code folding, line numbers, bracket matching
- Code snippet generation (cURL, Python, JavaScript)
- Tabbed request editing with breadcrumb navigation
- Response viewer with search, JSONPath/XPath filtering, and beautify
- Response metadata popups (status, timing, size, network/TLS details)
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

## Architecture

`src/` is organized into three layers: `database/` (SQLAlchemy models and repositories), `services/` (business logic bridging UI and DB), and `ui/` (PySide6 widgets). Tests in `tests/` mirror the source tree. See [`.github/copilot-instructions.md`](.github/copilot-instructions.md) for the full architecture tree and coding conventions.
