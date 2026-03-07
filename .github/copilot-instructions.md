# Postmark — Copilot Instructions

## CRITICAL — Keeping instructions in sync

> **MANDATORY — EVERY code change MUST be followed by an instruction audit.**
> After modifying, adding, or deleting ANY source file, test file, signal,
> TypedDict, service method, QSS objectName, or architectural pattern, you
> MUST review ALL instruction files listed below and update them to reflect
> the change.  **Stale or incomplete instructions are treated as bugs.**
>
> Checklist — run through each step after every code change:
>
> 1. **Update the architecture tree** in this file to match `src/` and
>    `tests/`.  Add new files, remove deleted files.
> 2. **Update `architecture.instructions.md`** with any new or changed
>    signals, data flows, TypedDicts, implicit contracts, or service methods.
> 3. **Update `pyside6.instructions.md`** with any new `objectName` values
>    used in global QSS.
> 4. **Update `testing.instructions.md`** with any new test files or
>    directories.
> 5. **Update `sqlalchemy.instructions.md`** with any new models,
>    relationships, or repository functions.
> 6. **Update relevant skills** (under `.github/skills/`) when adding or
>    changing signals, service/repository methods, TypedDicts, widgets, or
>    parsers.  See the Skills table below.
> 7. **Search every instruction file and skill** for stale references to
>    renamed, moved, or deleted code.  Remove or correct them.

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

On-demand skills (loaded when the task matches the description):

| Skill | Description |
|-------|-------------|
| [signal-flow](./skills/signal-flow/SKILL.md) | Complete signal flow diagrams, signal declaration tables, MainWindow wiring summary |
| [service-repository-reference](./skills/service-repository-reference/SKILL.md) | Repository function catalogues, service method tables, TypedDict schemas |
| [widget-patterns](./skills/widget-patterns/SKILL.md) | Tree badge rendering, data roles, InfoPopup, VariablePopup, theme module, new widget checklist |
| [test-writing](./skills/test-writing/SKILL.md) | Test patterns for all layers — repository, service, UI widget, MainWindow |
| [import-parser](./skills/import-parser/SKILL.md) | How to add a new import format parser to the import system |
| [customization-guide](./skills/customization-guide/SKILL.md) | How to create, update, or debug Copilot instruction files, skills, applyTo patterns, and YAML frontmatter |

> **Instructions vs Skills:** Instructions are always loaded when editing
> matching files — keep them lean with core rules.  Skills are loaded
> on-demand when the task description matches — use them for heavyweight
> reference material, step-by-step guides, and catalogues.

### Quick-reference — creating new skills or instructions

If you need to **add a new skill** or **instruction file**, follow these
minimal rules (full guide in the `customization-guide` skill):

**Skill** — `.github/skills/<name>/SKILL.md`:
```yaml
---
name: "<name>"                    # kebab-case, matches folder name
description: "One sentence ..."    # VS Code matches this to user prompts
---
# <Title>
(content)
```

**Instruction** — `.github/instructions/<name>.instructions.md`:
```yaml
---
name: "<Display Name>"
description: "One sentence ..."
applyTo: "src/path/**/*.py"        # glob — auto-loaded for matching files
---
# <Title>
(content)
```

After creating either, **update this file**: add the new entry to the
scoped-instructions or skills table above, and update the sync checklist
if needed.

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

## LLM Navigation Quick-Start

Fastest paths to understand and navigate the codebase:

- **All services at a glance:** Read `src/services/__init__.py` — re-exports
  `CollectionService`, `EnvironmentService`, `ImportService`, and key
  TypedDicts (`RequestLoadDict`, `VariableDetail`, `LocalOverride`).
- **HTTP subsystem:** Read `src/services/http/__init__.py` — re-exports
  `HttpService`, `GraphQLSchemaService`, `SnippetGenerator`,
  `HttpResponseDict`, `parse_header_dict`.
- **All DB models:** Read `src/database/database.py` — re-exports all four
  ORM models (`CollectionModel`, `RequestModel`, `SavedResponseModel`,
  `EnvironmentModel`).
- **Collection CRUD vs queries:** Mutations live in
  `collection_repository.py`; read-only tree/breadcrumb/ancestor queries
  live in `collection_query_repository.py`.
- **Signal flow:** Load the `signal-flow` skill for complete wiring diagrams.
- **TypedDicts:** Cross-module dict schemas live in the service that owns
  them (e.g. `RequestLoadDict` in `collection_service.py`,
  `HttpResponseDict` in `http_service.py`).
- **Test fixtures:** `make_collection_with_request` (root `conftest.py`) and
  `make_request_dict` (`tests/ui/request/conftest.py`) reduce setup
  boilerplate.

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
│       │   ├── collection_query_repository.py   # Read-only tree/breadcrumb/ancestor queries
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
│   ├── environment_service.py     # EnvironmentService (variable substitution + TypedDicts)
│   ├── import_service.py          # ImportService (parse + persist)
│   ├── http/                      # HTTP request/response handling
│   │   ├── http_service.py        # HttpService (httpx) + response TypedDicts
│   │   ├── graphql_schema_service.py  # GraphQL introspection + schema parsing
│   │   ├── snippet_generator.py   # Code snippet generation (cURL/Python/JS)
│   │   └── header_utils.py        # Shared header parsing utility
│   └── import_parser/             # Parser sub-package
│       ├── models.py              # TypedDict schemas for parsed data
│       ├── postman_parser.py      # Postman collection/environment parser
│       ├── curl_parser.py         # cURL command parser
│       └── url_parser.py          # URL/raw-text auto-detect parser
└── ui/                            # PySide6 widgets
    ├── main_window/               # Top-level MainWindow sub-package
    │   ├── window.py              # MainWindow widget + signal wiring
    │   ├── send_pipeline.py       # _SendPipelineMixin — HTTP send/response flow
    │   ├── tab_controller.py      # _TabControllerMixin — tab open/close/switch
    │   └── variable_controller.py # _VariableControllerMixin — env variable management
    ├── loading_screen.py          # Loading screen overlay widget
    ├── styling/                   # Visual theming and icons
    │   ├── theme.py               # Palettes, colours, badge geometry, method_color()
    │   ├── theme_manager.py       # ThemeManager — QPalette + QSettings
    │   ├── global_qss.py          # build_global_qss() — global stylesheet builder
    │   └── icons.py               # Phosphor font-glyph icon provider (phi())
    ├── widgets/                   # Reusable shared components
    │   ├── code_editor/           # CodeEditorWidget sub-package
    │   │   ├── editor_widget.py   # CodeEditorWidget — main editor class
    │   │   ├── highlighter.py     # Syntax highlighting engine
    │   │   ├── folding.py         # Code folding logic
    │   │   ├── gutter.py          # Line-number gutter
    │   │   └── painting.py        # Custom painting helpers
    │   ├── info_popup.py          # InfoPopup (QFrame) base + ClickableLabel
    │   ├── key_value_table.py     # Reusable key-value editor widget
    │   ├── variable_line_edit.py  # VariableLineEdit — QLineEdit with {{var}} highlighting + hover popup
    │   └── variable_popup.py      # VariablePopup — singleton hover popup for variable details
    ├── collections/               # Collection sidebar
    │   ├── collection_header.py
    │   ├── collection_widget.py
    │   └── tree/                  # Tree widget sub-package
    │       ├── constants.py
    │       ├── draggable_tree_widget.py
    │       ├── collection_tree.py # CollectionTree widget
    │       ├── tree_actions.py    # _TreeActionsMixin — context menus, rename, delete
    │       └── collection_tree_delegate.py  # Custom delegate for method badges
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
        ├── folder_editor.py         # Folder/collection detail editor
        ├── http_worker.py           # HttpSendWorker + SchemaFetchWorker (QThread)
        ├── request_editor/          # RequestEditor sub-package
        │   ├── editor_widget.py     # RequestEditor — main request editing widget
        │   ├── auth.py              # _AuthMixin — authentication UI
        │   ├── body_search.py       # _BodySearchMixin — search/replace in body
        │   └── graphql.py           # _GraphQLMixin — GraphQL mode + schema
        ├── response_viewer/         # ResponseViewer sub-package
        │   ├── viewer_widget.py     # ResponseViewer — response display widget
        │   └── search_filter.py     # _SearchFilterMixin — response search/filter
        ├── navigation/              # Tab switching and path navigation
        │   ├── breadcrumb_bar.py
        │   ├── request_tab_bar.py
        │   └── tab_manager.py       # TabManager + TabContext (with local_overrides)
        └── popups/                  # Response metadata popups
            ├── status_popup.py      # HTTP status code explanation
            ├── timing_popup.py      # Request timing breakdown
            ├── size_popup.py        # Response/request size breakdown
            └── network_popup.py     # Network/TLS connection details
tests/
├── conftest.py                    # Autouse fresh-DB fixture + qapp fixture
├── unit/                          # Repository & service layer tests
│   ├── database/                  # Repository tests
│   │   ├── test_repository.py
│   │   └── test_environment_repository.py
│   └── services/                  # Service layer tests
│       ├── test_service.py
│       ├── test_environment_service.py
│       ├── test_import_parser.py
│       ├── test_import_service.py
│       └── http/                  # HTTP service tests
│           ├── test_http_service.py
│           ├── test_graphql_schema_service.py
│           └── test_snippet_generator.py
└── ui/                            # End-to-end PySide6 widget tests
    ├── conftest.py                # _no_fetch (autouse) + helpers
    ├── test_main_window.py
    ├── test_main_window_save.py   # SaveButton + RequestSaveEndToEnd tests
    ├── styling/                   # Theme and icon tests
    │   ├── test_theme_manager.py
    │   └── test_icons.py
    ├── widgets/                   # Shared component tests
    │   ├── test_code_editor.py
    │   ├── test_code_editor_folding.py
    │   ├── test_code_editor_painting.py
    │   ├── test_code_editor_memory.py
    │   ├── test_info_popup.py
    │   ├── test_key_value_table.py
    │   ├── test_variable_line_edit.py
    │   ├── test_variable_popup.py
    │   └── test_variable_popup_local.py
    ├── collections/               # Collection sidebar tests
    │   ├── test_collection_header.py
    │   ├── test_collection_tree.py
    │   ├── test_collection_tree_actions.py
    │   ├── test_collection_tree_delegate.py
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
        ├── conftest.py              # make_request_dict fixture factory
        ├── test_folder_editor.py
        ├── test_http_worker.py
        ├── test_request_editor.py
        ├── test_request_editor_auth.py
        ├── test_request_editor_binary.py
        ├── test_request_editor_graphql.py
        ├── test_request_editor_search.py
        ├── test_response_viewer.py
        ├── test_response_viewer_search.py
        ├── navigation/            # Tab and breadcrumb tests
        │   ├── test_breadcrumb_bar.py
        │   ├── test_request_tab_bar.py
        │   └── test_tab_manager.py
        └── popups/                # Response popup tests
            ├── test_status_popup.py
            ├── test_timing_popup.py
            ├── test_size_popup.py
            └── test_network_popup.py
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

> **ZERO tolerance for errors — including pre-existing ones.**
> Every command above must exit with **zero** errors, warnings, or
> suggestions.  If you find a pre-existing error (lint, type, format,
> test failure) while working on an unrelated task, **fix it immediately**
> in the same change.  "It was already broken" is never an acceptable
> excuse — fix it anyway.  All four commands passing clean is a hard gate
> on every change.  No exceptions.

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
- All hex colour values belong in `src/ui/styling/theme.py` -- never inline.
- Use `TypedDict` for dict schemas that cross module boundaries.
- No emoji in code comments -- use plain numbered steps (e.g. `# 1.`).
- **Directory file limit:** No directory may contain more than 5 `.py` files
  (excluding `__init__.py`).  When a directory reaches this limit, group
  related files into a sub-package before adding more.  Test directories
  mirror the source tree; test file count may exceed 5 when multiple test
  files cover a single source module.
- **File line limit:** No single `.py` file may exceed **600 lines**
  (including docstrings and comments).  When a file approaches this limit,
  extract cohesive groups of methods, helper classes, or setup logic into
  a sub-package.  Re-export public symbols from the package's `__init__.py`
  so external imports remain stable.  Test files follow the same limit —
  split by test class into separate files mirroring the sub-package.
