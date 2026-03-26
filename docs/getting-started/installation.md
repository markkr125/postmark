# Installation

## Prerequisites

- **Python 3.12** or newer (up to 3.13).
- **Poetry** — Python dependency and virtual environment manager.

## Steps

1. **Clone the repository:**

   ```bash
   git clone <repository-url>
   cd postmark
   ```

2. **Install all dependencies** (including dev tools):

   ```bash
   poetry install --with dev
   ```

   This installs the runtime dependencies (PySide6, SQLAlchemy, httpx,
   Pygments, jsonpath-ng, lxml) and the dev dependencies (pytest, ruff,
   mypy, pytest-qt, pytest-xdist, type stubs).

3. **Verify the installation:**

   ```bash
   poetry run python -c "import PySide6; print(PySide6.__version__)"
   ```

## Fonts

The application ships with Phosphor icon fonts in `data/fonts/`.  These
are loaded automatically at startup — no manual font installation is
required.

## Database

The SQLite database is created automatically on first run at
`data/database/main.db`.  No manual setup is needed.

## Poetry Configuration

The project uses `poetry.toml` for local Poetry settings.  Key points:

- `src/` is configured as the Python path for all tools (`pythonpath` in
  pytest, `mypy_path` in mypy, `extraPaths` in Pyright).
- Imports use bare module names: `from database.database import init_db`.

## Next Steps

- [Running the application](running.md)
- [Architecture Overview](../architecture/overview.md)
