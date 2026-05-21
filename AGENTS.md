# Postmark — Agent Instructions

## CRITICAL — Keeping instructions in sync

> **MANDATORY — EVERY code change MUST be followed by an instruction audit.**
> After modifying, adding, or deleting ANY source file, test file, signal,
> TypedDict, service method, QSS objectName, or architectural pattern, you
> MUST review ALL relevant `AGENTS.md` files and skills listed below and update them to reflect
> the change.  **Stale or incomplete instructions are treated as bugs.**
>
> Checklist — run through each step after every code change:
>
> 1. **Update the architecture tree** in this file to match `src/` and
>    `tests/`.  Add new files, remove deleted files.
> 2. **Update [`src/AGENTS.md`](src/AGENTS.md)** with any new or changed
>    signals, data flows, TypedDicts, implicit contracts, or service methods.
> 3. **Update [`src/ui/AGENTS.md`](src/ui/AGENTS.md)** with any new `objectName` values
>    used in global QSS.
> 4. **Update [`tests/AGENTS.md`](tests/AGENTS.md)** with any new test files or
>    directories.
> 5. **Update [`src/database/AGENTS.md`](src/database/AGENTS.md)** with any new models,
>    relationships, or repository functions.
> 6. **Update relevant skills** (under `.agents/skills/`) when adding or
>    changing signals, service/repository methods, TypedDicts, widgets, or
>    parsers.  See the Skills table below.
> 7. **Search every `AGENTS.md` file and skill** for stale references to
>    renamed, moved, or deleted code.  Remove or correct them.
> 8. **Update `docs/` pages** when adding, changing, or removing public API,
>    signals, TypedDicts, widgets, parsers, or architectural patterns.
>    Update [`docs/AGENTS.md`](docs/AGENTS.md) when documentation authoring rules change.
>    See `docs/contributing/updating-docs.md` for the full checklist.

This file and the nested `AGENTS.md` files below form a single source of
truth.

- **Check all agent instruction files for overlap** before editing any of them.
- **Never duplicate rules** across files — reference the canonical location.
- **Place rules in the most specific file** that applies. Only add rules here
  if they are truly project-wide.
- **Prefer adding a nested `AGENTS.md`** in the appropriate directory
  (`src/`, `src/ui/`, `src/database/`, `tests/`, `docs/`) over growing this file.

Nested `AGENTS.md` files (merged with this file based on which paths you edit — see each file for layer-specific rules):

| File | Scope |
|------|-------|
| [src/ui/AGENTS.md](src/ui/AGENTS.md) | PySide6 / UI code under `src/ui/` |
| [src/database/AGENTS.md](src/database/AGENTS.md) | SQLAlchemy / DB under `src/database/` |
| [src/AGENTS.md](src/AGENTS.md) | Architecture & data flow for all of `src/` |
| [tests/AGENTS.md](tests/AGENTS.md) | Testing conventions under `tests/` |
| [docs/AGENTS.md](docs/AGENTS.md) | Documentation authoring under `docs/` |

On-demand skills — read the relevant `SKILL.md` when the task matches (see `description` in each file’s frontmatter):

| Skill | Description |
|-------|-------------|
| [signal-flow](.agents/skills/signal-flow/SKILL.md) | Complete signal flow diagrams, signal declaration tables, MainWindow wiring summary |
| [service-repository-reference](.agents/skills/service-repository-reference/SKILL.md) | Repository function catalogues, service method tables, TypedDict schemas |
| [widget-patterns](.agents/skills/widget-patterns/SKILL.md) | Tree badge rendering, data roles, InfoPopup, VariablePopup, theme module, new widget checklist |
| [test-writing](.agents/skills/test-writing/SKILL.md) | Test patterns for all layers — repository, service, UI widget, MainWindow |
| [import-parser](.agents/skills/import-parser/SKILL.md) | How to add a new import format parser to the import system |
| [customization-guide](.agents/skills/customization-guide/SKILL.md) | How to create, update, or debug agent instructions, nested `AGENTS.md`, skills, and project conventions |

> **Nested AGENTS.md vs Skills:** Nested files apply when you work under their directories — keep them lean with core rules. Skills are optional deep reference — load when the task matches the skill description.

### Quick-reference — creating new skills or nested instructions

If you need to **add a new skill** or **nested `AGENTS.md`**, follow these
minimal rules (full guide in the `customization-guide` skill):

**Skill** — `.agents/skills/<name>/SKILL.md`:
```yaml
---
name: "<name>"                    # kebab-case, matches folder name
description: "One sentence ... when to load this skill"
---
# <Title>
(content)
```

**Nested agent instructions** — add `AGENTS.md` in the directory that owns the rules (e.g. `src/ui/AGENTS.md`). No glob metadata required — location defines scope.

After creating either, **update this file**: add the new entry to the
nested-files or skills table above, and update the sync checklist
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
  `CollectionService`, `EnvironmentService`, `ImportService`,
  `RunHistoryService`, and key TypedDicts (`RequestLoadDict`,
  `VariableDetail`, `LocalOverride`).
- **HTTP subsystem:** Read `src/services/http/__init__.py` — re-exports
  `HttpService`, `GraphQLSchemaService`, `SnippetGenerator`,
  `SnippetOptions`, `HttpResponseDict`, `parse_header_dict`.
  Auth header injection lives in `src/services/http/auth_handler.py`.
  OAuth 2.0 token exchange lives in `src/services/http/oauth2_service.py`.
- **All DB models:** Read `src/database/database.py` — re-exports collection,
  environment, run-history, and local-script ORM models (`CollectionModel`,
  `RequestModel`, `SavedResponseModel`, `EnvironmentModel`, `RunHistoryModel`,
  `RunResultModel`, `LocalScriptFolderModel`, `LocalScriptModel`,
  `SnippetModel`).
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
docs/                              # Project documentation (see docs/README.md)
├── README.md                      # Landing page + full table of contents
├── getting-started/               # Installation, running, overview
├── architecture/                  # Layered design, data flow, directory tree
├── api-reference/                 # Function signatures, TypedDicts, signals
│   ├── database/                  # ORM models, repository functions
│   └── services/                  # Service methods, HTTP, auth, parsers
├── ui-reference/                  # Widget classes, styling, navigation
├── guides/                        # How-to guides (import parser, auth, widget, tests, signals)
└── contributing/                  # Coding conventions, testing, updating docs
data/
└── snippets/                      # Script editor snippet JSON (javascript, python; see README.md)
src/
├── main.py                        # Entry point — configure_before_qapplication + QApplication + init_db()
├── qt_app_init.py                 # Hi-DPI bootstrap (before first QApplication; tests + app)
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
│       ├── runs/
│       │   ├── run_history_repository.py  # CRUD for run history + results
│       │   └── model/
│       │       ├── run_history_model.py   # RunHistoryModel (collection runs)
│       │       └── run_result_model.py    # RunResultModel (per-request results)
│       ├── environments/
│       │   ├── environment_repository.py  # CRUD for environments
│       │   └── model/
│       │       └── environment_model.py   # EnvironmentModel (key-value sets)
│       └── local_scripts/
│           ├── local_script_repository.py       # CRUD + atomic rename/move + ref rewrite
│           ├── local_script_query_repository.py   # Read-only script tree query
│           ├── path_policy.py                   # Path-safe folder/script segment validation
│           ├── virtual_paths.py                 # script_virtual_extension; .js vs .cjs paths
│           ├── path_index.py                    # Virtual path list for pm.require local: autocomplete
│           ├── require_refs_rewrite.py          # pm.require("local:…") reference rewriter
│           └── model/
│               ├── local_script_folder_model.py
│               └── local_script_model.py  # ``module_format`` (``esm`` | ``commonjs``)
│       └── snippets/
│           ├── snippet_repository.py      # CRUD for user-authored script snippets
│           └── model/
│               └── snippet_model.py       # SnippetModel (scope + context)
│       └── request_assertions/
│           ├── request_assertion_repository.py  # CRUD for declarative assertion rows
│           └── model/
│               └── request_assertion_model.py   # RequestAssertionModel (subject/operator/expected)
├── services/                      # Service layer (UI ↔ DB bridge)
│   ├── collection_service.py      # CollectionService (static methods)
│   ├── assertion_service.py       # AssertionService + AssertionDict — declarative tests CRUD + compile
│   ├── local_script_service.py    # LocalScriptService + LocalScriptLoadDict
│   ├── snippet_service.py         # SnippetService — user snippet CRUD + loader cache invalidation
│   ├── environment_service.py     # EnvironmentService (variable substitution + TypedDicts)
│   ├── import_service.py          # ImportService (parse + persist)
│   ├── run_history_service.py     # RunHistoryService (run history CRUD bridge)
│   ├── script_service.py          # ScriptService (script chain resolution)
│   ├── scripting/                 # Script execution sub-package
│   │   ├── local_path_policy.py   # Re-export path_policy (UI/service)
│   │   ├── local_virtual_paths.py # Re-export virtual_paths
│   │   ├── local_script_modules.py # pm.require("local:…") resolve + bundle
│   │   ├── local_script_require_refs.py  # Re-export require_refs_rewrite
│   │   ├── __init__.py            # TypedDicts (ScriptInput/Output, TestResult, etc.)
│   │   ├── engine.py              # ScriptEngine + run_debug_chain (re-exports find_pm_tests, find_top_level_statement_lines)
│   │   ├── pm_test_finder.py      # find_pm_tests — pm.test discovery for gutter
│   │   ├── pm_api_linter.py       # Diagnostic + pm/postman static walk helpers
│   │   ├── script_breakpoint_analyzer.py  # find_top_level_statement_lines — debugger gutter
│   │   ├── assertions_compiler.py # compile_to_js/py — declarative rows → pm.test blocks (source_name declarative)
│   │   ├── data_loader.py         # parse_data_file — CSV/JSON rows for data-driven runs
│   │   ├── context.py             # Context builders + normalize_events() + execute_sub_request() + globals persistence
│   │   ├── deno_manager.py        # DenoManager — managed Deno download/cache; managed_deno_path() = cache only
│   │   ├── python_format.py       # format_python_source() — Ruff format for script editors (jedi has no formatter)
│   │   ├── runtime_settings.py   # RuntimeSettings + RuntimePathStatus + RegistryEntry + PyPIConfig — QSettings Deno/Python paths, LSP toggle, validation, private package registries (npm/JSR scope-mapped, default-npm with auth_kind, PyPI index URLs)
│   │   ├── secret_store.py        # SecretStore (Protocol) + KeyringSecretStore / EncryptedFileSecretStore / NoopSecretStore + get_default_store() (keyring self-test fallback) + backend_status() — token storage for private package registries
│   │   ├── deno_runtime.py        # DenoRuntime — default JS run via deno run + data/scripts/deno_drain.mjs (sendRequest IPC); _build_npmrc_text() resolves private-registry tokens into a chmod-0600 .npmrc when ``pm.require("npm:…")``/``("jsr:…")`` literals trigger network mode
│   │   ├── esprima_deno.py        # Esprima parse via deno run data/scripts/esprima_parse.mjs (linter, gutter)
│   │   ├── js_runtime.py          # JSRuntime (DenoRuntime) + bootstrap/vendor + pm.require literal detection / ESM import block for npm:/jsr:
│   │   ├── py_runtime.py          # PyRuntime — Pyodide (Deno) when vendor present, else RestrictedPython subprocess
│   │   ├── pyodide_runtime.py     # PyodideRuntime — data/scripts/pyodide_run.mjs + vendor_pyodide + micropip / pm.require; _resolve_pypi_index_urls() embeds auth into private PyPI index URLs (micropip.set_index_urls)
│   │   ├── _py_sandbox.py         # RestrictedPython subprocess entry (main + _execute_restricted; re-exports for tests)
│   │   ├── _sandbox_safe_globals.py # _SAFE_BUILTINS / _SAFE_STDLIB for RestrictedPython
│   │   ├── _sandbox_runtime.py    # Resource limits, console capture, _write_done
│   │   ├── _sandbox_pm_assertions.py # _Expectation chains
│   │   ├── _sandbox_pm_models.py  # _PmRequest/_PmResponse/_HeaderList, …
│   │   ├── _sandbox_pm_tests.py   # pm.test / pm.test.skip
│   │   ├── _sandbox_pm.py         # _Pm root object + variable scopes
│   │   ├── _sandbox_debug.py      # settrace debug execution (_execute_debug)
│   │   └── debug/                 # Debug sub-package (step-through debugging)
│   │       ├── protocol.py        # DebugProtocol state machine + DebugPauseInfo
│   │       ├── js_debug.py        # JS: inject_checkpoints, locals readers; debug_execute → deno_debug
│   │       ├── deno_scope.py      # CDP scope materialisation; deep expand pm/console; ``__pm_className__`` for CDP descriptions
│   │       ├── deno_debug.py      # Deno --inspect-brk + CDP (Chrome DevTools Protocol) step-through
│   │       └── py_debug.py        # Python settrace subprocess debug execution
│   ├── lsp/                       # Language Server Protocol (Deno LSP, jedi-language-server)
│   │   ├── transport.py           # LspTransport — JSON-RPC Content-Length + QThread reader
│   │   ├── client.py              # LspClient — initialize, didOpen/Change/Close, requests
│   │   ├── qt_lsp_offsets.py      # QTextDocument position ↔ LSP line/UTF-16 column
│   │   ├── pm_require_types.py      # pm_require_index.ts generation + deno cache for npm/jsr specs
│   │   ├── stubs_generator.py     # pm.d.ts / pm.pyi from pm_api_schema
│   │   ├── server_registry.py     # LspRegistry — shared clients; shutdown on app quit
│   │   └── servers/               # make_deno_client, make_jedi_client, workspace seed
│   │       ├── _workspace.py
│   │       ├── deno_client.py
│   │       └── jedi_client.py
│   ├── http/                      # HTTP request/response handling
│   │   ├── http_service.py        # HttpService (httpx) + response TypedDicts
│   │   ├── graphql_schema_service.py  # GraphQL introspection + schema parsing
│   │   ├── auth_handler.py        # Shared auth header injection (all 12 auth types)
│   │   ├── oauth2_service.py      # OAuth 2.0 token exchange (4 grant types)
│   │   ├── snippet_generator/     # Code snippet generation sub-package (23 languages)
│   │   │   ├── generator.py       # SnippetGenerator, SnippetOptions, LanguageEntry, registry
│   │   │   ├── shell_snippets.py  # cURL, HTTP raw, wget, HTTPie, PowerShell
│   │   │   ├── dynamic_snippets.py  # Python, JS, Node, Ruby, PHP, Dart
│   │   │   └── compiled_snippets.py # Go, Rust, C, Swift, Java, Kotlin, C#
│   │   └── header_utils.py        # Shared header parsing utility
│   └── import_parser/             # Parser sub-package
│       ├── models.py              # TypedDict schemas for parsed data
│       ├── postman_parser.py      # Postman collection/environment parser
│       ├── curl_parser.py         # cURL command parser
│       └── url_parser.py          # URL/raw-text auto-detect parser
└── ui/                            # PySide6 widgets
    ├── main_window/               # Top-level MainWindow sub-package
    │   ├── window.py              # MainWindow widget + signal wiring
    │   ├── send_pipeline.py       # _SendPipelineMixin — HTTP send (re-exports debug-hover helpers)
    │   ├── send_pipeline_debug.py # _merge_debug_hover_values, _debug_hover_root_objects, …
    │   ├── send_pipeline_postresponse.py  # on_send_finished, run_post_response_script_with_live_response
    │   ├── send_pipeline_debug_session.py # on_debug_paused/step/finished, end_debug_ui
    │   ├── draft_controller.py    # _DraftControllerMixin — draft tab open/save
    │   ├── tab_controller.py      # _TabControllerMixin — tab open/close/switch
    │   └── variable_controller.py # _VariableControllerMixin — env variable + sidebar management
    ├── local_scripts/             # Centre-pane local script editor
    │   ├── local_script_editor_widget.py  # LocalScriptEditorWidget — CodeEditorWidget + DB save
    │   └── script_filename.py     # Basename/extension display helpers for script tree + tabs
    ├── loading_screen.py          # Loading screen overlay widget
    ├── sidebar/                   # Sidebar rails + flyout panels
    │   ├── sidebar_widget.py      # RightSidebar (icon rail) + _FlyoutPanel
    │   ├── left_sidebar.py        # LeftSidebar — activity rail + stacked nav flyout pages
    │   ├── local_scripts_sidebar_panel.py  # Legacy empty shell (unused; MainWindow uses CollectionWidget)
    │   ├── variables_panel.py     # VariablesPanel — read-only variable display
    │   ├── snippet_panel.py       # SnippetPanel — inline code snippet generator
    │   ├── debug_panel.py         # DebugPanel facade — DebugControls + CallStackPanel + DebugVariablesPanel + WatchPanel
    │   ├── debug_call_stack_panel.py  # CallStackPanel — frame list + frame_selected
    │   ├── debug_watch_panel.py   # WatchPanel — watch expressions via DebugProtocol.evaluate
    │   └── saved_responses/           # Saved responses sub-package
    │       ├── panel.py               # SavedResponsesPanel — saved example list/detail flyout
    │       ├── search_filter.py       # _PanelSearchFilterMixin — body search/filter
    │       ├── helpers.py             # Formatting helpers (body size, language detect, etc.)
    │       └── delegate.py            # Custom delegate for saved response list items
    ├── styling/                   # Visual theming and icons
    │   ├── theme.py               # Palettes, colours, status bar / left-rail chrome, badge/tree geometry, left-nav panel margins, method_color(), status_color()
    │   ├── language_icons.py      # Brand SVG pixmaps for JS / TS / Python tiles
    │   ├── theme_manager.py       # ThemeManager — QPalette + QSettings
    │   ├── tab_settings_manager.py # TabSettingsManager — request-tab QSettings bridge (preview, limits, activate-on-close, wrap mode)
    │   ├── global_qss.py          # build_global_qss() — global stylesheet builder
    │   └── icons.py               # Phosphor font-glyph icon provider (phi())
    ├── widgets/                   # Reusable shared components
    │   ├── code_editor/           # CodeEditorWidget sub-package
    │   │   ├── editor_widget.py   # CodeEditorWidget — core + __init__ (mixins below)
    │   │   ├── editor_formatting.py  # _FormattingMixin — prettify, format-on-idle
    │   │   ├── editor_snippets.py    # _SnippetMixin — save-as-snippet context menu
    │   │   ├── editor_test_gutter.py # _TestGutterMixin — pm.test gutter
    │   │   ├── editor_variables.py   # _VariableMixin — {{var}} + debug hover
    │   │   ├── editor_language.py    # _LanguageMixin — set_language
    │   │   ├── editor_keyboard.py    # _KeyboardMixin — keyPressEvent, line comment
    │   │   ├── editor_ident.py       # _IdentMixin — identifier at position
    │   │   ├── editor_breakpoints.py # _BreakpointMixin — breakpoint gutter
    │   │   ├── editor_lsp_glue.py    # attach_lsp, detach_lsp, signature/hover glue
    │   │   ├── lsp_integration.py # EditorLspAdapter — LSP sync + diagnostics; optional LSP for script modes
    │   │   ├── popup_registry.py  # Shared singleton Completion/ParameterHint/SymbolDoc/DebugValue popups
    │   │   ├── debug_hover_popup.py # DebugValuePopup — expandable hover for paused script locals
    │   │   ├── highlighter.py     # Syntax highlighting engine
    │   │   ├── folding.py         # Code folding logic
    │   │   ├── gutter.py          # Gutter QWidget delegates + minimap (_MinimapArea); column order in painting.resizeEvent
    │   │   ├── painting.py        # _PaintingMixin shims → paint_* modules
    │   │   ├── paint_breakpoints.py
    │   │   ├── paint_diagnostics.py
    │   │   ├── paint_inline_logs.py
    │   │   ├── paint_test_gutter.py
    │   │   └── completion/        # Autocomplete sub-package
    │   │       ├── schema/        # Schema sub-package
    │   │       │   ├── core.py    # SchemaNode TypedDict, expectation chain, shared helpers
    │   │       │   ├── js.py      # JS_SCHEMA (pm, console, CryptoJS, postman) + JS_GLOBALS
    │   │       │   └── py.py      # PY_SCHEMA + PY_GLOBALS (Python variant)
    │   │       ├── engine.py      # CompletionEngine — dot-path, variables, resolve_symbol(), find_definition_pos(), resolve_call_signature(), resolve_nearest_call_signature()
    │   │       ├── mixin.py       # _CompletionMixin — triggers, filtering, parameter hint + Ctrl+hover symbol doc wiring
    │   │       ├── parameter_hint.py # ParameterHintPopup — floating call-signature hint
    │   │       ├── popup.py       # CompletionPopup — floating autocomplete widget
    │   │       └── symbol_doc_popup.py # SymbolDocPopup — Ctrl+hover / Ctrl+Q quick-doc tooltip
    │   ├── info_popup.py          # InfoPopup (QFrame) base + ClickableLabel
    │   ├── sidebar_section_info.py # SidebarSectionInfoPopup — (i) help for sidebar sections
    │   ├── lazy_editor_placeholder.py # LazyEditorPlaceholder — progress + caption until Body/Scripts editors mount
    │   ├── key_value_column_widths.py # QSettings JSON persistence for Key/Value widths
    │   ├── key_value_table.py     # Reusable key-value editor widget
    │   ├── key_value_bulk.py      # Bulk text serialize/parse for key-value tables
    │   ├── key_value_table_delegate.py # Variable {{…}} highlight delegate for key-value cells
    │   ├── search_replace_bar.py  # SearchReplaceBar — find/replace + go-to-line for CodeEditorWidget
    │   ├── deno_download_worker.py # DenoDownloadWorker — QThread background Deno download (banner + settings)
    │   ├── debug_value_tree.py    # Debug tree helpers (CLASSNAME_KEY, attach_selectable_cell_widgets, debug_tree_cell_text, fill_tree_item, populate_debug_tree, source_dot_icon, make_debug_value_tree)
    │   ├── runtime_banner.py      # RuntimeBanner — Deno install/configure prompt for JS editors
    │   ├── snippets/              # Script snippet palette (loader + SnippetsPopup)
    │   │   ├── loader.py          # load_snippets — merges data/snippets/*.json + DB user snippets
    │   │   ├── popup.py           # SnippetsPopup — search + grouped list; delete user rows
    │   │   └── snippet_capture_dialog.py  # Save as snippet… dialog
    │   ├── variable_line_edit.py  # VariableLineEdit — QLineEdit with {{var}} highlighting + hover popup
    │   └── variable_popup.py      # VariablePopup — singleton hover popup for variable details
    ├── collections/               # Collection sidebar
    │   ├── collection_header.py
    │   ├── collection_widget.py
    │   ├── new_item_popup.py      # NewItemPopup — Postman-style icon grid popup
    │   ├── new_local_script_popup.py  # NewLocalScriptItemPopup — Script / Folder tiles
    │   └── tree/                  # Tree widget sub-package
    │       ├── constants.py
    │       ├── draggable_tree_widget.py
    │       ├── collection_tree.py # CollectionTree widget
    │       ├── tree_actions.py    # _TreeActionsMixin — context menus, rename, delete
    │       └── collection_tree_delegate.py  # Custom delegate for method badges
    ├── dialogs/                   # Modal dialogs
    │   ├── collection_runner/
    │   │   ├── __init__.py        # Re-exports RunnerConfigView, RunnerResultsView, RunnerWorker
    │   │   ├── config.py          # RunnerConfigView (env selector, request checklist, data file, iterations, delay)
    │   │   ├── results.py         # RunnerResultsView (summary + results table + detail panel + export)
    │   │   └── worker.py          # RunnerWorker (QThread), env var substitution, scripts_enabled (imports parse_data_file from services)
    │   ├── import_dialog.py
    │   ├── save_request_dialog.py  # Save draft request to collection
    │   └── settings_dialog.py     # Settings (theme + request-tab + Scripting: LSP toggle, Deno/Python paths)
    ├── environments/              # Environment management widgets
    │   ├── environment_editor.py  # EnvironmentEditorWidget + EnvironmentEditorDialog
    │   ├── environment_selector.py
    │   └── environment_sidebar_panel.py
    ├── panels/                    # Bottom / side panels
    │   ├── console_panel.py
    │   └── history_panel.py
    └── request/                   # Request/response editing
        ├── folder_editor/           # Folder/collection detail editor sub-package
        │   ├── editor_widget.py     # FolderEditorWidget — main editor class
        │   ├── runner_panel.py      # _RunnerPanel — inline collection runner (Runs -> New run)
        │   └── runs.py              # _RunsMixin + _build_runs_table (run history table)
        ├── http_worker.py           # HttpSendWorker + SchemaFetchWorker (QThread)
        ├── auth/                    # Shared auth sub-package (14 auth types)
        │   ├── auth_field_specs.py  # Per-type FieldSpec definitions (AUTH_FIELD_SPECS)
        │   ├── auth_mixin.py        # _AuthMixin — shared by both editors
        │   ├── auth_pages.py        # FieldSpec dataclass, page builders, auth constants
        │   ├── auth_serializer.py   # Generic load/save for all auth types
        │   └── oauth2_page.py       # OAuth 2.0 custom page (grant-type switching)
        ├── request_editor/          # RequestEditor sub-package
        │   ├── editor_widget.py     # RequestEditor — main request editing widget
        │   ├── auth.py              # Re-export of _AuthMixin from auth sub-package
        │   ├── body_search.py       # _BodySearchMixin — search/replace in body
        │   ├── graphql.py           # _GraphQLMixin — GraphQL mode + schema
        │   ├── assertions/          # Declarative assertions sub-package
        │   │   ├── assertions_tab.py    # AssertionsTab — subject/operator/expected rows
        │   │   └── assertions_mixin.py  # _AssertionsMixin — lazy tab + AssertionService persistence
        │   ├── data_runner/         # Inline data-driven script runner (D3)
        │   │   └── panel.py         # DataRunnerPanel — CSV/JSON picker + Run iterations
        │   └── scripts/             # Scripts sub-package
        │       ├── script_language.py # codes: javascript | typescript | python; detect/heuristics, display, normalise
        │       ├── script_editor_pane/ # ScriptEditorPane — reusable toolbar + editor + output stack
        │       ├── scripts_mixin.py # _ScriptsMixin — dual pre-request/test script editors (delegates to panes)
        │       ├── mock_response_tab.py # ScriptMockResponseTab — mock status + headers table + JSON CodeEditorWidget body (post-response)
        │       ├── output_panel.py  # ScriptOutputPanel — orchestration + worker slot shims
        │       ├── output_panel_build.py  # Tab/layout construction
        │       ├── output_console_tab.py  # Console rows + inline_log_annotations_from_console_logs
        │       ├── output_variable_section.py
        │       ├── output_test_results_tab.py
        │       ├── output_debug_bar.py
        │       ├── output_script_runner.py  # run_script / debug worker wiring
        │       ├── output_iterations_tab.py # ScriptOutputIterationsTab — iteration×test matrix + re-run failed
        │       ├── lsp_problems_tab.py # ScriptLspProblemsTab — LSP diagnostics list; ``problem_count_changed`` → tab title ``Problems (n)``
        │       ├── script_run_worker.py # ScriptRunWorker — inline runs; ``iteration_finished`` for data-driven matrix
        │       ├── version_history.py # _show_version_history entry point
        │       └── version_history/ # Version history dialog sub-package
        │           ├── delegate.py  # _VersionItemDelegate — two-line list item rendering
        │           ├── dialog.py    # VersionHistoryDialog — timeline + side-by-side diff
        │           ├── diff_viewer.py # _DiffViewer — dual-editor diff with folding
        │           ├── helpers.py   # Diff formatting, fold ranges, timestamp helpers
        │           └── toolbar.py   # _DiffToolbar — search, nav, whitespace, copy
        ├── response_viewer/         # ResponseViewer sub-package
        │   ├── viewer_widget.py     # ResponseViewer — response display widget
        │   ├── search_filter.py     # _SearchFilterMixin — response search/filter
        │   ├── test_results_mixin.py # _TestResultsMixin — test results tab
        │   └── pre_request_mixin.py # _PreRequestMixin — pre-request script output tab
        ├── navigation/              # Tab switching and path navigation
        │   ├── breadcrumb_bar.py
        │   ├── request_tab_bar.py   # Compatibility wrapper re-exporting the wrapped deck
        │   ├── request_tabs/        # Wrapped multi-row request tab deck sub-package
        │   │   ├── __init__.py
        │   │   ├── bar.py           # RequestTabBar custom wrapped-row deck
        │   │   ├── labels.py        # TabLabel / FolderTabLabel chip content widgets
        │   │   └── tab_button.py    # TabButton chip with close + reorder interactions
        │   └── tab_manager.py       # TabManager + TabContext (with local_overrides, draft_name)
        └── popups/                  # Response metadata popups
            ├── status_popup.py      # HTTP status code explanation
            ├── timing_popup.py      # Request timing breakdown
            ├── size_popup.py        # Response/request size breakdown
            └── network_popup.py     # Network/TLS connection details
tests/
├── conftest.py                    # Autouse fresh-DB fixture + qapp fixture + tab-settings reset
├── unit/                          # Repository & service layer tests
│   ├── database/                  # Repository tests
│   │   ├── test_repository.py
│   │   ├── test_local_script_repository.py
│   │   ├── test_local_script_path_policy.py
│   │   ├── test_local_script_require_refs.py
│   │   ├── test_request_assertion_repository.py
│   │   ├── test_script_version_local_script.py
│   │   ├── test_environment_repository.py
│   │   └── test_run_history_repository.py
│   └── services/                  # Service layer tests
│       ├── test_service.py
│       ├── test_environment_service.py
│       ├── test_import_parser.py
│       ├── test_import_service.py
│       ├── test_script_bridge_globals.py
│       ├── test_script_debug.py
│       ├── test_script_debug_cdp.py
│       ├── test_script_engine.py
│       ├── test_pm_api_schema_drift.py
│       ├── test_script_linter.py
│       ├── test_script_sandbox.py
│       ├── test_script_service.py
│       ├── test_script_vendor.py
│       ├── test_script_vendor_libs.py
│       ├── test_data_loader.py
│       ├── test_script_run_worker_iterations.py
│       ├── test_script_version_service.py
│       ├── test_assertions_compiler.py
│       ├── test_deno_manager.py
│       ├── test_runtime_settings.py
│       └── http/                  # HTTP service tests
│           ├── test_http_service.py
│           ├── test_graphql_schema_service.py
│           ├── test_snippet_generator.py
│           ├── test_snippet_shell.py
│           ├── test_snippet_dynamic.py
│           ├── test_snippet_compiled.py
│           ├── test_auth_handler.py
│           └── test_oauth2_service.py
└── ui/                            # End-to-end PySide6 widget tests
    ├── conftest.py                # _no_fetch (autouse) + helpers
    ├── test_main_window.py
    ├── test_main_window_tabs_navigation.py # Wrapped tab deck shortcuts + search tests
    ├── test_main_window_save.py   # SaveButton + RequestSaveEndToEnd tests
    ├── test_main_window_draft.py  # Draft tab open/save lifecycle tests
    ├── test_main_window_session.py # Tab session persistence (save/restore) tests
    ├── styling/                   # Theme and icon tests
    │   ├── test_theme_manager.py
    │   └── test_icons.py
    ├── sidebar/                   # Sidebar widget tests
    │   ├── test_sidebar.py
    │   ├── test_left_sidebar.py
    │   ├── test_variables_panel.py
    │   ├── test_snippet_panel.py
    │   ├── test_debug_panel.py
    │   └── test_saved_responses_panel.py
    ├── widgets/                   # Shared component tests
    │   ├── test_code_editor.py
    │   ├── test_code_editor_folding.py
    │   ├── test_code_editor_painting.py
    │   ├── test_code_editor_memory.py
    │   ├── test_code_editor_minimap.py
    │   ├── test_code_editor_variables.py
    │   ├── test_completion_engine.py
    │   ├── test_completion_popup.py
    │   ├── test_info_popup.py
    │   ├── test_key_value_table.py
    │   ├── test_variable_line_edit.py
    │   ├── test_variable_popup.py
    │   ├── test_variable_popup_local.py
    │   ├── test_search_replace_bar.py
    │   └── test_runtime_banner.py
    ├── collections/               # Collection sidebar tests
    │   ├── test_collection_header.py
    │   ├── test_collection_tree.py
    │   ├── test_collection_tree_actions.py
    │   ├── test_collection_tree_delegate.py
    │   ├── test_collection_widget.py
    │   ├── test_new_item_popup.py
    │   └── test_new_local_script_popup.py
    ├── dialogs/                   # Dialog tests
    │   ├── test_collection_runner.py
    │   ├── test_import_dialog.py
    │   ├── test_save_request_dialog.py
    │   └── test_settings_dialog.py
    ├── environments/              # Environment widget tests
    │   ├── test_environment_editor.py
    │   ├── test_environment_selector.py
    │   └── test_environment_sidebar_panel.py
    ├── panels/                    # Panel tests
    │   ├── test_console_panel.py
    │   └── test_history_panel.py
    └── request/                   # Request/response editing tests
        ├── conftest.py              # make_request_dict fixture factory
        ├── test_folder_editor.py
        ├── test_folder_editor_scripts.py
        ├── test_runner_panel.py
        ├── test_http_worker.py
        ├── test_request_editor.py
        ├── test_request_editor_auth.py
        ├── test_request_editor_binary.py
        ├── test_request_editor_graphql.py
        ├── test_request_editor_search.py
        ├── test_response_viewer.py
        ├── test_response_viewer_search.py
        ├── test_response_viewer_tests.py
        ├── test_version_history.py
        ├── test_script_output_panel.py
        ├── test_script_lsp_problems_tab.py
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
must stay green.  See [`tests/AGENTS.md`](tests/AGENTS.md) for detailed conventions.

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
