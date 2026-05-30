# Testing conventions

## Quick rules — read these first

1. **Run `poetry run pytest` after every change** — all tests must pass.
   Use the default addopts (`-n auto`, ~2–3 minutes). Avoid `-n0` unless
   debugging a single file; the full suite takes ~11 minutes single-process
   and can look hung. A **120s per-test timeout** (`pytest-timeout`) aborts
   stuck tests instead of blocking the run indefinitely.
2. **Also run `poetry run ruff check src/ tests/`,
   `poetry run ruff format --check src/ tests/`, and
   `poetry run mypy src/ tests/`** — see [AGENTS.md](../AGENTS.md) for the
   full validation checklist.
3. **Each test gets a fresh SQLite database** — the `_fresh_db` autouse
   fixture handles this.  Never share DB state between tests.
4. **Each test starts with cleared tab preferences** — the
   `_reset_tab_settings` autouse fixture removes the `tabs/*` QSettings
   group and the ``ui/kv_col_widths`` key (key-value table column widths)
   so preview/tab-limit settings and persisted table columns never leak
   between cases.
4b. **Settings → Scripting tests** — `test_settings_dialog` uses an
   autouse fixture that removes `scripting` (as well as `theme` and `tabs`)
   **before and after** each test so a fake persisted `scripting/deno_path`
   from the Apply test cannot affect later test modules in the same session
   (which would break Deno-based script tests).  Mypy: that module has a
   scoped ``[[tool.mypy.overrides]]`` entry in ``pyproject.toml`` disabling
   ``union-attr`` for ``QTreeWidgetItem`` / ``QTableWidgetItem`` access patterns
   the stubs mark as optional.
5. **UI tests need `qapp` and `qtbot` fixtures.**  Register widgets with
   `qtbot.addWidget(widget)`.
6. **The `_no_fetch` fixture is autouse in `tests/ui/`** — it prevents
   `CollectionWidget` from spawning a background thread.  You do not need
   to apply it manually.
7. **Use bare module imports** (e.g. `from database.database import init_db`)
   — `src/` and `tests/` are on the Python path (see `pyproject.toml` ``pythonpath``).
8. **JS tests that need Esprima** can use ``from esprima_test_util import deno_and_esprima_available`` — ``deno --version`` alone is not enough when the Esprima subprocess is broken.
9. **Do not test the session or engine directly** — test through the
   repository or service layer.

## Fresh database per test (autouse fixture)

`conftest.py` provides a `_fresh_db` fixture that resets the module-level
engine and creates a new SQLite file in `tmp_path` before every test. Tests
must **never** share database state.

When adding new conftest fixtures that touch the DB, keep the same pattern:

```python
import database.database as db_mod

db_mod._engine = None
db_mod._SessionLocal = None
init_db(tmp_path / "test.db")
```

## QApplication fixture (session-scoped)

`conftest.py` provides a `qapp` fixture (session-scoped) that returns the
single `QApplication` instance. All UI tests must accept `qapp` and use
`qtbot.addWidget(widget)` for cleanup.

At import time, `conftest.py` calls `configure_before_qapplication()` from
`qt_app_init` (same as `main.py`) so Hi-DPI scale-factor rounding applies before
the first `QApplication` is constructed in the test process.

## Fresh QSettings tab preferences per test (autouse fixture)

`conftest.py` also provides `_reset_tab_settings`, which removes the
`tabs` QSettings group and the ``ui/kv_col_widths`` key before every test.
Use this when adding persisted request-tab settings (or key-value column
widths) so one test cannot silently change preview, tab-limit, or table
layout behaviour for the next.

## `_no_fetch` fixture — avoiding background threads in tests

`CollectionWidget.__init__` spawns a `QThread` that queries the database.
This breaks tests because:

1. **SQLite rejects cross-thread access** — the test DB is on the main
   thread; the worker thread gets `sqlite3.ProgrammingError`.
2. **The async fetch races with assertions** — the test may check the tree
   before loading finishes.

**How `_no_fetch` works:** It patches `CollectionWidget._start_fetch` to a
no-op so no background thread starts.

**How to populate the tree instead:** Call
`widget._tree_widget.set_collections(make_collection_dict(...))` directly.

`_no_fetch` is **autouse** within `tests/ui/` — every UI test gets the patch
automatically.  No decorator is needed:

```python
class TestCollectionWidget:
    ...
```

Only override `_no_fetch` for tests that intentionally verify the threading
behaviour (and configure SQLite for cross-thread access).

## Test layers — what to test and how

| Layer | Import from | Notes |
|-------|-------------|-------|
| Repository | `database.models.collections.collection_repository` | Direct function calls, assert return values and DB side-effects |
| Service | `services.collection_service.CollectionService` | Instantiate the class, call methods, verify delegation works |
| UI widgets | `ui.collections.*` | Use `qapp` + `qtbot` fixtures; `_no_fetch` is autouse |
| MainWindow | `ui.main_window.MainWindow` | Smoke tests only; `_no_fetch` is autouse |

### Do NOT test the database engine or session factory directly

Test through the repository or service layer. The session is an implementation
detail managed by `get_session()`.

## Directory layout

Test directories **mirror the source tree**.  Keep them in sync — when a
source file lives under `src/ui/request/`, its test lives under
`tests/ui/request/`.  Never dump new test files into `tests/ui/` or
`tests/unit/` root — always place them in the matching subfolder.

**Test file line limit:** Test files follow the same **600-line** cap as
source files.  When a source file is split into a sub-package, mirror the
split in the test directory — one test file per submodule.  If a single
test file still exceeds 600 lines, split by test class into separate files.

```
tests/
├── conftest.py                    # Root: configure_before_qapplication + _fresh_db + _reset_tab_settings + _disable_script_lsp_in_tests + _shutdown_lsp_clients + _reset_code_editor_popups_after_test (autouse) + qapp
├── qt_popup_cleanup.py            # reset_code_editor_popups + flush_deferred_widget_deletes (shared by root + ui conftest)
├── esprima_test_util.py           # deno_and_esprima_available() for JS parse-dependent tests
├── unit/                          # Pure logic — no Qt widgets
│   ├── database/                  # Repository layer tests
│   │   ├── test_repository.py
│   │   ├── test_debug_metadata_migration.py
│   │   ├── test_debug_metadata_repository.py
│   │   ├── test_local_script_repository.py
│   │   ├── test_local_script_path_policy.py
│   │   ├── test_local_script_require_refs.py
│   │   ├── test_local_script_import_refs_rewrite.py  # ESM relative import rewrite on rename
│   │   ├── test_snippet_repository.py
│   │   ├── test_request_assertion_repository.py
│   │   ├── test_script_version_local_script.py
│   │   ├── test_environment_repository.py
│   │   └── test_run_history_repository.py
│   ├── local_scripts/             # Script filename display helpers
│   │   └── test_script_filename.py
│   └── services/                  # Service layer tests
│       ├── test_service.py
│       ├── test_environment_service.py
│       ├── test_import_parser.py
│       ├── test_import_service.py
│       ├── test_script_bridge_globals.py
│       ├── test_script_debug.py
│       ├── test_assertion_service.py
│       ├── test_script_debug_cdp.py
│       ├── test_js_debug.py
│       ├── test_py_debug.py
│       ├── test_console_source_line.py
│       ├── test_dynamic_variables.py
│       ├── test_pm_parity_deno_pyodide.py
│       ├── test_script_engine.py
│       ├── test_script_output_tab_prefs.py
│       ├── test_pm_api_schema_drift.py  # pm_api_schema paths resolve in Deno JS
│       ├── test_pyodide_runtime.py
│       ├── test_debug_script_metadata.py
│       ├── test_debug_metadata_persist_host.py
│       ├── test_script_sandbox.py
│       ├── test_script_service.py
│       ├── test_script_vendor.py
│       ├── test_script_vendor_libs.py
│       ├── test_data_loader.py
│       ├── test_script_run_worker_iterations.py
│       ├── test_script_version_service.py
│       ├── test_snippet_service.py
│       ├── test_assertions_compiler.py
│       ├── test_deno_manager.py
│       ├── test_python_format.py
│       ├── test_script_error_format.py
│       ├── test_runtime_settings.py
│       ├── test_secret_store.py     # SecretStore backends: keyring / encrypted-file / noop; default-store self-test fallback
│       ├── test_deno_runtime_registries.py  # _build_npmrc_text + deno_ipc_argv_and_env private-registry plumbing
│       ├── test_cjs_deno_interop.py       # Gate 0 Deno ``import *`` from ``.cjs``
│       ├── test_local_script_pm_require.py  # pm.require("local:…") resolve + bundle + CJS runtime
│       ├── test_local_dependency_diagnostics.py  # Direct local: dependency Problems + require anchors
│       ├── test_local_scripts_project_mirror.py  # Deno local/ mirror sync + orphan prune
│       ├── test_local_scripts_project_import_graph.py  # Regex ESM import closure
│       ├── test_local_scripts_project_runner.py  # Local entry bundle (dynamic import)
│       ├── test_local_scripts_project_navigation.py  # Ctrl+click import resolution
│       ├── test_ambient_pm_deno.py  # Live ``deno check`` for ambient_pm.d.ts + local/ pm usage
│       ├── test_pyodide_private_pypi.py     # _pypi_index_hosts + _resolve_pypi_index_urls auth embedding
│       ├── lsp/                   # LSP transport / offset helpers
│       │   ├── test_transport.py
│       │   ├── test_qt_lsp_offsets.py
│       │   ├── test_js_lsp_preamble.py
│       │   ├── test_npm_types_members.py
│       │   ├── test_deno_npm_completion_e2e.py  # headless completion capture; tmp_path LSP workspace; xdist_group deno_lsp
│       │   ├── test_pm_require_resolve.py
│       │   ├── test_pm_require_types.py
│       │   ├── test_local_script_lsp_prep.py  # prepare_local_script_lsp_attach, worker shutdown, finalize token guard
│       │   └── fake_server.py     # JSON-RPC test double (not collected)
│       └── http/                  # HTTP service tests
│           ├── test_http_service.py
│           ├── test_graphql_schema_service.py
│           ├── test_snippet_generator.py
│           ├── test_snippet_shell.py
│           ├── test_snippet_dynamic.py
│           ├── test_snippet_compiled.py
│           ├── test_auth_handler.py
│           └── test_oauth2_service.py
└── ui/                            # PySide6 widget tests (need qapp + qtbot)
    ├── conftest.py                # _no_fetch (autouse) + helper functions
   ├── test_main_window.py        # Top-level MainWindow smoke tests
   ├── test_main_window_tabs_navigation.py # Wrapped tab deck shortcuts + search tests
   ├── test_main_window_tab_nav_history.py # Go menu tab activation back/forward
    ├── test_main_window_save.py   # SaveButton + RequestSaveEndToEnd tests
    ├── test_main_window_draft.py  # Draft tab open/save lifecycle tests
    ├── test_main_window_session.py # Tab session persistence (save/restore) tests
    ├── local_scripts/
    │   └── test_local_script_editor_widget.py # LocalScriptEditorWidget auto-save + async LSP prep defer tests
    ├── styling/                   # Theme and icon tests
    │   ├── test_theme_manager.py
    │   ├── test_icons.py
    │   └── test_language_icons.py
    ├── widgets/                   # Shared component tests
    │   ├── test_code_editor.py
    │   ├── test_code_editor_folding.py
    │   ├── test_code_editor_painting.py
    │   ├── test_code_editor_memory.py
    │   ├── test_code_editor_minimap.py
    │   ├── test_completion_engine.py
    │   ├── test_completion_engine_top_level.py
    │   ├── test_completion_engine_local_paths.py
    │   ├── test_esm_import_completion_accept.py
    │   ├── test_lsp_diagnostic_debounce.py
    │   └── unit/services/lsp/test_lsp_spawn_registry.py
    │   ├── test_no_debug_on_keystroke.py  # script editor typing must not call DebugProtocol.evaluate
    │   ├── test_debug_session_suspend_lsp.py  # LSP didChange paused during debug session
    │   ├── test_local_dependency_problems.py
    │   ├── test_local_require_ctrl_click.py
    │   ├── test_completion_popup.py
    │   ├── test_info_popup.py
    │   ├── test_key_value_table.py
    │   ├── test_query_string.py   # URL query parse/build helpers (no encoding)
    │   ├── test_variable_line_edit.py
    │   ├── test_variable_popup.py
    │   ├── test_variable_popup_local.py
    │   ├── test_search_replace_bar.py
    │   ├── test_snippets_popup.py   # Snippet JSON + SnippetsPopup (no delete on user rows)
    │   ├── test_snippet_capture_dialog.py  # Create / edit dialog
    │   └── test_runtime_banner.py
   ├── sidebar/                   # Sidebar widget tests
   │   ├── test_sidebar.py
   │   ├── test_left_sidebar.py
   │   ├── test_variables_panel.py
   │   ├── test_snippet_panel.py
   │   ├── test_debug_panel.py
   │   ├── test_debug_call_stack.py
   │   ├── test_debug_inspector_split.py
   │   ├── test_debug_variables_watches.py
   │   ├── test_debug_metadata_persist.py
   │   ├── test_snippets_sidebar_panel.py
   │   └── test_saved_responses_panel.py
    ├── collections/               # Collection sidebar tests
    │   ├── test_collection_header.py
    │   ├── test_collection_tree.py
    │   ├── test_collection_tree_actions.py
    │   ├── test_collection_tree_delegate.py
    │   ├── test_collection_widget.py
    │   ├── test_local_scripts_tree_breadcrumb.py
    │   ├── test_local_scripts_tree_folder_expand.py  # expand must not rewrite folder label to Unnamed
    │   ├── test_local_scripts_tree_icons.py
    │   ├── test_local_scripts_tree_rename.py
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
        ├── test_folder_editor.py
        ├── test_folder_editor_scripts.py
        ├── test_runner_panel.py
        ├── test_script_language.py
        ├── test_http_worker.py
        ├── test_request_editor.py
        ├── test_request_editor_auth.py
        ├── test_request_editor_binary.py
        ├── test_request_editor_graphql.py
        ├── test_request_editor_search.py
        ├── test_assertions_tab.py
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

- **unit/database/** — repository tests. No Qt dependency.
- **unit/services/** — service layer tests. No Qt dependency.
- **unit/services/http/** — HTTP, GraphQL, and snippet service tests.
- **ui/** — widget integration tests grouped by source subpackage.
- **ui/styling/** — theme and icon tests.
- **ui/widgets/** — shared component tests.

When adding tests for a new widget, create the file in the matching
`tests/ui/<subpackage>/` folder.  When adding tests for a new service or
repository, add to the matching `tests/unit/<subpackage>/` folder.

## Test file and class naming

- One test file per component, placed in the matching subfolder:
  `tests/ui/request/test_request_editor.py`,
  `tests/unit/services/test_service.py`
- Group related tests in classes: `TestCollectionCRUD`, `TestRequestCRUD`,
  `TestCollectionService`, `TestCollectionTree`, `TestCollectionWidget`
- Prefix test methods with `test_`: `test_create_root_collection`

## UI test patterns

When testing PySide6 widgets:

1. Accept `qapp` and `qtbot` as fixtures.
2. Create the widget and register it with `qtbot.addWidget(widget)`.
3. ``RequestEditorWidget`` does not build Body / Scripts heavy editors until those
   tabs are shown — call ``_ensure_body_editors()`` / ``_ensure_scripts_editors()``
   (or ``_tabs.setCurrentIndex`` for Body / Scripts) before touching body or script
   widgets (e.g. ``_body_code_editor``, ``_pre_request_edit``).
4. Use `qtbot.waitSignal` to assert that a signal was emitted.
5. Populate tree data via `set_collections(make_collection_dict(...))`.
6. Assert tree state via `top_level_items(tree)`, `item.data(col, ROLE)`, etc.
7. For signal-to-service integration, emit signals directly on the tree widget
   and verify the DB changed via `CollectionService`.

Shared helpers (`make_collection_dict`, `top_level_items`) live in
`tests/ui/conftest.py` and can be imported via relative import from any
subfolder:

```python
from ..conftest import make_collection_dict, top_level_items
```

## Assertions and error testing

- Use plain `assert` — pytest rewrites them for rich diffs.
- Use `pytest.raises(ExceptionType, match="substring")` for expected errors.
- Avoid `try/except` in tests; let unexpected exceptions propagate.

## Imports

All imports use bare module names relative to `src/` (configured via
`pythonpath = ["src"]` in `pyproject.toml`):

```python
from database.models.collections.collection_repository import create_new_collection
from services.collection_service import CollectionService
from ui.collections.tree import CollectionTree, ROLE_ITEM_ID
```

## Coding style

- `from __future__ import annotations` in every test module.
- Follow the same ruff / type-checking rules as production code.
- Keep tests focused -- one logical assertion per test method when practical.
- Use descriptive names: `test_delete_nonexistent_collection_raises` not
  `test_delete_error`.

## Temporary directories

Use pytest's built-in `tmp_path` fixture. Do **not** import
`tempfile.TemporaryDirectory` -- `tmp_path` handles cleanup automatically.
