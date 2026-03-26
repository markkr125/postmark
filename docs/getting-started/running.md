# Running

## Launch the Application

```bash
poetry run python src/main.py
```

Or use the VS Code build task (defined in `.vscode/tasks.json`):
**Run main with Poetry** — press `Ctrl+Shift+B` to execute.

## Development Commands

All commands use `poetry run` to ensure the correct virtual environment.

### Full validation suite

Run after every code change — all four must pass with zero errors:

```bash
poetry run pytest                          # all tests
poetry run ruff check src/ tests/          # linter
poetry run ruff format --check src/ tests/ # formatter
poetry run mypy src/ tests/                # type checker
```

### Individual commands

| Command | Purpose |
|---------|---------|
| `poetry run pytest` | Run all tests (parallelised with pytest-xdist) |
| `poetry run pytest tests/unit/` | Run only repository and service tests |
| `poetry run pytest tests/ui/` | Run only UI widget tests |
| `poetry run pytest -x` | Stop on first failure |
| `poetry run ruff check src/` | Lint source code |
| `poetry run ruff format src/` | Auto-format source code |
| `poetry run mypy src/` | Type-check source code |
| `python scripts/check_md_links.py` | Validate markdown links |

### Documentation link check

After any `.md` file change:

```bash
python scripts/check_md_links.py
```

## Project Structure

```text
postmark/
  src/          Source code (database, services, ui)
  tests/        Test suite (mirrors src/ structure)
  data/         Runtime data (database, fonts, images)
  docs/         Project documentation
  scripts/      Utility scripts
  archive/      Sample collection data for development
```

See [Directory Structure](../architecture/directory-structure.md) for the
full annotated source tree.
