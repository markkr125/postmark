# Testing conventions

## Quick rules — read these first

1. **Run `poetry run pytest` after every change** — all tests must pass.
   Use default addopts (`-n auto`; ~2–3 minutes). **Do not** use `-n0` for
   full-suite validation — see the parallel-run warning in
   [AGENTS.md](../AGENTS.md) (CRITICAL — Verify after every change).
   Reserve `-n0` for single-file debugging only. A **120s per-test timeout**
   (`pytest-timeout`) aborts stuck tests instead of blocking the run indefinitely.
   **``--max-worker-restart=8``** stops the session when xdist workers segfault
   repeatedly instead of replacing them forever.
   **`tests/conftest.py`** sets ``QT_QPA_PLATFORM=offscreen`` by default so UI
   tests do not pop windows on the developer desktop; use ``POSTMARK_TEST_VISIBLE=1``
   or an explicit ``QT_QPA_PLATFORM`` when debugging layout on a real display.
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
4b. **Settings dialog tests** — `test_settings_dialog` uses an autouse fixture
   that removes `scripting` and `history` (as well as `theme` and `tabs`)
   **before and after** each test so a fake persisted `scripting/deno_path`
   from the Apply test cannot affect later test modules in the same session
   (which would break Deno-based script tests).  Mypy: that module has a
   scoped ``[[tool.mypy.overrides]]`` entry in ``pyproject.toml`` disabling
   ``union-attr`` for ``QTreeWidgetItem`` / ``QTableWidgetItem`` access patterns
   the stubs mark as optional.
5. **UI tests need `qapp` and `qtbot` fixtures.**  Register widgets with
   `qtbot.addWidget(widget)`.
5b. **Qt widget destruction in tests** — never ``del`` a visible ``QWidget`` and
   hammer ``gc.collect()`` in a loop; that can segfault Shiboken during parallel
   runs. Use ``tests/qt_widget_lifecycle.py`` (``dispose_qt_widget``,
   ``run_gc_after_qt_flush``, ``wait_for_weakrefs_cleared``). Memory-leak tests
   in ``test_code_editor_memory.py`` use ``pytest.mark.xdist_group("code_editor_memory")``
   (serialized under xdist); all ``tests/ui/sidebar/`` UI tests share
   ``pytest.mark.xdist_group("sidebar_qt")`` via ``tests/ui/sidebar/conftest.py``
   (including transcript memory cases — run ``-n0`` when debugging a single file).
   RestrictedPython subprocess tests use ``pytest.mark.xdist_group("restricted_python_sandbox")``
   and ``tests/unit/services/conftest.py`` holds a cross-worker ``fcntl`` lock so
   ``test_script_sandbox.py`` and ``test_pm_python_parity.py`` do not spawn sandboxes
   in parallel under ``--dist loadfile``. ``tests/conftest.py`` caps xdist workers at 8,
   reaps child zombies after
   each test, and tears down sandbox subprocesses via detached process groups.
6. **The `_no_fetch` fixture is autouse in `tests/ui/`** — it prevents
   `CollectionWidget` from spawning a background thread.  You do not need
   to apply it manually.
7. **Use bare module imports** (e.g. `from database.database import init_db`)
   — `src/` and `tests/` are on the Python path (see `pyproject.toml` ``pythonpath``).
8. **JS tests that need Esprima** can use ``from esprima_test_util import deno_and_esprima_available`` — ``deno --version`` alone is not enough when the Esprima subprocess is broken.
9. **Do not test the session or engine directly** — test through the
   repository or service layer.

## A failing test is a finding, not an obstacle

A previously-passing test that fails after your change is a **regression
until proven otherwise** — fix the production code, not the test.  See the
three-question gate and green-baseline rule in [AGENTS.md](../AGENTS.md)
(CRITICAL — A failing test is a finding, not an obstacle).

### Never do these to make a failing existing test pass

- Change an `assert`'s expected value to match the new (wrong) output.
- Add `@pytest.mark.skip` / `xfail` / `pytest.skip()` to a regressing test.
- Loosen an assertion (`assert x == 5` → `assert x is not None`, exact →
  substring, `==` → `>=`).
- Delete the failing test or its assertions.
- Broaden a `pytest.raises(match=...)` or remove the `match`.
- Wrap the body in `try/except` to swallow the failure.
- Comment out the test or its assertions.

Each of the above is allowed **only** when accompanied by an explicit,
user-requested behaviour change that invalidates the old contract — and you
must say so in your response.

To check whether a test was passing before your change, use **read-only**
git commands (`git diff`, `git show HEAD:<path>`, `git log -p`).  **NEVER run
`git stash`** without the USER's direct approval.

## Isolated user-data and send-history directories (autouse fixtures)

`conftest.py` provides `_isolated_postmark_user_data`, which monkeypatches
`postmark_user_data_dir()` to a per-test folder under `tmp_path`.

`_isolated_request_history` monkeypatches `user_history_root()` to a temp folder.
**Required** so `init_db()` → `reconcile_orphans()` on an empty per-test DB does
not delete the developer's real `~/.local/share/postmark/history/` payloads.

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
├── qt_popup_cleanup.py            # reset_code_editor_popups + reset_session_history_popups + dismiss_all_top_level_test_widgets
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
│   │   ├── test_run_history_repository.py
│   │   ├── test_ai_chat_migration.py
│   │   ├── test_ai_chat_repository.py
│   │   ├── test_data_paths.py
│   │   ├── test_request_history_body_store.py
│   │   └── test_request_history_repository.py
│   ├── local_scripts/             # Script filename display helpers
│   │   └── test_script_filename.py
│   ├── ui/                        # UI helpers (may need qapp for Qt types)
│   │   ├── sidebar/ai/            # Chat markdown renderer unit tests
│   │   │   ├── test_chat_markdown_fence_split.py
│   │   │   ├── test_chat_markdown_highlight.py
│   │   │   ├── test_chat_markdown_highlight_cache.py
│   │   │   ├── test_markdown_code_block_chrome.py
│   │   │   ├── test_chat_markdown_render.py
│   │   │   ├── test_chat_markdown_streaming.py
│   │   │   ├── test_chat_markdown_streaming_render.py
│   │   │   ├── test_streaming_table.py
│   │   │   ├── test_markdown_content_height.py
│   │   │   ├── test_markdown_content_static.py  # MarkdownContent paint, selection, drag autoscroll
│   │   │   ├── test_markdown_content_links.py  # postmark:// deep-links vs https external; malformed postmark:// never opens externally
│   │   │   ├── test_chat_time_format.py
│   │   │   ├── test_thought_collapse_height.py
│   │   │   ├── test_thought_layout_reentrancy.py
│   │   │   ├── test_bubble_stream_row_height.py
│   │   │   ├── test_chat_composer.py
│   │   │   ├── test_composer_attachments.py  # attachment paths + prompt-trailer lift/compose for edit
│   │   │   └── test_user_message_collapse.py
│   │   └── widgets/
│   │       ├── test_text_format_helpers.py
│   │       └── test_text_format_async.py
│   └── services/                  # Service layer tests
│       ├── conftest.py            # cross-worker fcntl lock for restricted_python_sandbox
│       ├── test_service.py
│       ├── test_environment_service.py
│       ├── test_import_parser.py
│       ├── test_openapi_parser.py  # OpenAPI 3 / Swagger 2 / YAML / URL fetch
│       ├── test_openapi_security.py  # securitySchemes → auth/signature; $ref params; Expedia unspecified note
│       ├── test_openapi_examples.py  # named examples → saved responses; request variants; Swagger 2
│       ├── test_wsdl_parser.py     # WSDL 1.1 → SOAP POST collection
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
│       ├── test_pm_python_parity.py  # xdist_group restricted_python_sandbox
│       ├── test_script_engine.py
│       ├── test_script_output_tab_prefs.py
│       ├── test_pm_api_schema_drift.py  # pm_api_schema paths resolve in Deno JS
│       ├── test_pyodide_runtime.py
│       ├── test_debug_script_metadata.py
│       ├── test_debug_metadata_persist_host.py
│       ├── test_script_sandbox.py  # xdist_group restricted_python_sandbox; SAFE_STDLIB ↔ pm_bootstrap key parity
│       ├── test_script_local_py_require.py  # Python pm.require("local:…") RestrictedPython + payloads
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
│       ├── test_request_history_service.py
│       ├── ai/
│       │   ├── test_ai_budget_config.py
│       │   ├── test_budget_period.py
│       │   ├── test_spend_rollup.py
│       │   ├── test_budget_status.py
│       │   ├── test_chat_run_limits.py
│       │   ├── test_chat_run_registry.py
│       │   ├── test_chat_run_registry_streaming.py  # Registry incremental streaming, chronological background reattach + anti-lambda guard
│       │   ├── test_ai_config.py
│       │   ├── test_model_metadata.py
│       │   ├── test_run_context_choices.py
│       │   ├── test_provider_display_name.py
│       │   ├── test_chat_response_text.py
│       │   ├── test_chat_session_service.py
│       │   ├── test_context_usage.py
│       │   ├── test_message_usage.py
│       │   ├── test_session_transcript_window.py  # Tail/older turn slicing
│       │   ├── test_llm_service.py
│       │   ├── test_postmark_agent_registry.py  # workspace prompt/desc: history routing + within_ids
│       │   ├── test_subagent_registry.py
│       │   ├── test_subagent_events.py
│       │   ├── test_tool_activity_events.py
│       │   ├── test_execute_events.py  # Agent execute observation → clickable card records
│       │   ├── test_thinking_sections.py
│       │   ├── test_subagent_disk_registry.py
│       │   ├── test_subagent_transcript.py
│       │   ├── test_subagent_limits.py
│       │   ├── test_delegate_tool.py
│       │   ├── test_build_app_wiki.py
│       │   ├── test_wiki_query_tool.py
│       │   ├── test_datetime_query_tool.py  # postmark_datetime now + timezone convert
│       │   ├── test_workspace_snapshot.py  # session snapshot + last search hits
│       │   ├── test_workspace_query_tool.py
│       │   ├── test_workspace_query_audit.py  # redaction, within_ids/[-1], params search, dirty merge, tokenized search
│       │   ├── test_workspace_query_variable.py  # scope=variable definitions/resolution/usages
│       │   ├── test_workspace_query_insights.py  # workspace health, fielded ops, multi-goal, env diff
│       │   ├── test_workspace_query_explorer.py  # env_reach, dependencies, walkthrough, dead/token/response_drift
│       │   ├── test_send_core_parity.py  # SharedSendCore: pre-request errors, overrides, globals, redact
│       │   ├── test_confirmation_spike.py  # ConfirmRisky pause/resume/reject + whitelist skip
│       │   ├── test_confirmation_payload.py  # human_preview + Approve title/detail + max-iterations Continue payload
│       │   ├── test_agent_tools_for_turn.py  # Ask/Plan/Agent tools_for_turn; Agent MUTATING_MAX_ITERATIONS=50
│       │   ├── test_agent_import_tool.py  # postmark_import Action schema + ImportService executor
│       │   ├── test_document_import_tool.py  # chunk paging, coverage, URI resolution, turn-name card labels, on-demand upload
│       │   ├── test_chat_attachment_chunks.py # chunk size/order/coverage; fences never split
│       │   ├── test_chat_attachment_screenshots.py # vision gate: images vs lazy cached OCR fallback
│       │   ├── test_chat_attachment_store.py # copy-in, Markdown conversion, URIs, session-delete cleanup
│       │   ├── test_provider_errors.py       # malformed tool call + unreachable provider summaries
│       │   ├── test_collection_draft_tool.py # incremental draft ops, empty-batch soft no-op, body/query-input matrix, table-only replay, finish persistence, risk mapping
│       │   ├── test_collection_draft_enrichment.py # params/scripts/vars/auth/responses/default headers
│       │   ├── test_collection_draft_signatures.py # recipe scripts, unknown kind, finish pre_request
│       │   ├── test_fabricated_link_guard.py # strip collection links no tool produced this turn
│   ├── document_import/               # PDF/DOCX extraction service tests
│   │   ├── fixtures/sample.pdf
│   │   ├── test_extract_pdf.py
│   │   ├── test_extract_docx.py
│   │   ├── test_ocr.py
│   │   ├── test_path_policy.py
│   │   └── test_to_markdown.py
│       │   ├── test_workspace_security.py  # PostmarkWorkspaceSecurityAnalyzer + policy
│       │   ├── test_mutation_bridge.py  # enqueue/drain mutation GUI events
│       │   ├── test_mutation_auto_approve.py  # whitelist add/remove/clear + Phase 2 kinds
│       │   ├── test_workspace_mutate_collections.py  # mutate CRUD + assertion_set + field filter
│       │   ├── test_workspace_mutate_local.py  # local scripts + secrets/auth/env/snippet mutate
│       │   ├── test_workspace_mutate_session.py  # active env, history delete, version restore, folder events
│       │   ├── test_workspace_mutate_debug_metadata.py  # breakpoints/watches merge mutate
│       │   ├── test_workspace_mutate_settings.py  # allowlisted settings mutate
│       │   ├── test_binary_body.py  # binary path policy + HttpService byte send
│       │   ├── test_agent_graphql_fetch.py  # execute fetch_graphql_schema
│       │   ├── test_agent_codegen_export.py  # generate_snippet + export artifact
│       │   ├── test_agent_oauth_get_token.py  # oauth_get_token v1 credential-blind
│       │   ├── test_agent_runner_execute.py  # execute:run_collection + run_iterations
│       │   ├── test_agent_send_execute.py  # record_history, run_agent_scripts, execute dispatch
│       │   ├── test_agent_local_script_execute.py  # run_agent_local_script + local kinds + secrets rejection
│       │   ├── test_pm_api_quickref.py
│       │   ├── test_provider_ops.py
│       │   ├── test_model_filters.py
│       │   ├── test_model_metadata.py
│       │   ├── test_ai_logging.py
│       │   ├── test_capability_display.py
│       │   ├── test_cost_display.py
│       │   ├── test_ai_page_splice.py
│       │   ├── test_ai_models_tree_header.py
│       │   └── test_sdk_env.py
│       ├── test_request_history_replay.py
│       ├── test_request_history_snapshot_headers.py
│       ├── test_secret_store.py     # SecretStore backends: keyring / encrypted-file / noop; default-store self-test fallback; platform keyring pin (no foreign backends)
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
   ├── main_window/
   │   └── test_ai_chat_controller.py  # AI chat controller + concurrent run registry paths
   │   └── test_ai_chat_deeplink.py  # postmark:// deep-link navigation (request/collection/script/tab/history/environment/saved_response) + focus_section; unknown/stale/missing/unsupported-focus/history-busy show status tip
   │   └── test_ai_chat_attachments.py # attached document copied in and delivered to the model
   │   └── test_main_window_ai_session_restore.py  # Persist + reopen last chat session on startup
   │   └── test_ai_chat_registry_streaming.py  # E2E registry→controller→panel incremental streaming
   │   └── test_ai_concurrent_runs.py  # E2E New chat / session switch + parallel send flows
   │   └── test_session_history_switch.py  # MainWindow session history switch during transcript load
   ├── test_main_window.py        # Top-level MainWindow smoke tests
   ├── test_main_window_tabs_navigation.py # Wrapped tab deck shortcuts + search tests
   ├── test_main_window_tab_nav_history.py # Go menu tab activation back/forward
    ├── test_main_window_save.py   # SaveButton + RequestSaveEndToEnd tests
    ├── test_main_window_draft.py  # Draft tab open/save lifecycle tests
    ├── test_main_window_session.py # Tab session persistence (save/restore) tests
    ├── local_scripts/
    │   ├── conftest.py                # local_script_editor fixture (WA_DontShowOnScreen) + autouse teardown
    │   └── test_local_script_editor_widget.py # LocalScriptEditorWidget auto-save + async LSP prep defer tests
    ├── styling/                   # Theme and icon tests
    │   ├── test_theme_manager.py
    │   ├── test_icons.py
    │   └── test_language_icons.py
    ├── widgets/                   # Shared component tests
    │   ├── test_code_editor.py
    │   ├── test_code_editor_folding.py
    │   ├── test_code_editor_painting.py
    │   ├── test_code_editor_memory.py  # xdist_group code_editor_memory; qt_widget_lifecycle teardown
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
    │   ├── test_busy_spinner.py
    │   └── test_runtime_banner.py
   ├── sidebar/                   # Sidebar widget tests
   │   ├── conftest.py  # pytestmark xdist_group sidebar_qt (all sidebar UI tests)
   │   ├── test_ai_chat_panel.py
   │   ├── test_chat_panel_streaming.py
   │   ├── test_chat_panel_smooth_scroll.py
   │   ├── test_chat_panel_resize.py
   │   ├── test_ai_chat_worker.py
│   ├── test_ai_chat_worker_confirmation.py  # Approve/Reject/Stop-while-waiting slots
│   ├── test_ai_chat_worker_confirm_loop.py  # P0-W: real run() WAITING→Approve/Reject/Stop; preview_url env-sub + draft/replay
│   ├── test_ai_execute_cards.py  # Execute result cards → history?focus=response / request deeplink
│   ├── test_ai_pending_tool_cards.py  # Inline Allow/Reject/Always allow + Continue/Stop max-iterations cards
│   ├── test_ai_tool_activity_cards.py # Tool activity cards, scroll fit, empty-batch prose, execute handoff, multi-cycle chronological phases
│   ├── test_ai_user_message_attachments.py  # User-bubble attachment chips: trailer → chips above prompt, sizes, legacy paths
│   ├── test_ai_session_history_popup.py  # Virtualized list; RUNNING_ROLE; ⋯ menu click routing; rename/delete dialogs
│   ├── test_ai_active_run_badge.py  # Header aiChatActiveRunsBadge count pill
│   ├── test_session_transcript_load.py  # Async session switch + lazy markdown; post-load settle skips work while pinned
   │   └── ai/
   │       ├── conftest.py  # load_transcript_sync helper
   │       ├── test_transcript_window.py  # Virtual tail/prepend paging + spacers
   │       ├── test_transcript_integration.py  # Real SQLite tail load + prefetch guards
   │       ├── test_sticky_prompt_virtual_transcript.py  # Sticky overlay with virtual tail + evicted user rows
   │       ├── test_transcript_memory.py  # sidebar_qt group; tail vs full RAM
   │       ├── test_chat_context_popup.py
   │       ├── test_chat_budget_banner.py
   │       ├── test_context_ring_button.py
   │       ├── test_assistant_message_footer.py
   │       ├── test_assistant_message_actions.py
   │       ├── test_subagent_cards.py  # SubagentTaskCard summary row, click opens dialog
   │       ├── test_subagent_detail_dialog.py  # SubagentDetailDialog task + markdown reply
   │       ├── test_thought_streaming_bounce.py  # E2E: thinking block grows monotonically, no bounce/oscillation
   │       ├── test_user_message_actions.py
   │       ├── test_inline_edit_message.py  # Inline edit + attachment trailer → chips (not mangled text)
   │       ├── test_inline_edit_sticky_host.py  # Inline edit composer reparented into sticky overlay
   │       ├── test_context_usage_integration.py
   │       ├── test_context_thread_safety.py
   │       └── test_context_usage_worker.py
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
   │   ├── test_saved_responses_panel.py
   │   ├── test_request_history_panel.py
   │   ├── test_global_history_panel.py
   │   ├── test_left_sidebar_global_history.py
   │   ├── test_global_history_open_navigation.py  # left-rail opens History; AI execute keeps AI flyout
   │   └── test_right_sidebar_request_history.py
    ├── collections/               # Collection sidebar tests
    │   ├── test_collection_header.py
    │   ├── test_collection_tree.py
    │   ├── test_collection_tree_actions.py
    │   ├── test_collection_tree_delegate.py
    │   ├── test_collection_widget.py
    │   ├── test_collection_refresh.py  # refresh_collections + folder highlight + open-tab reload
    │   ├── test_local_scripts_tree_breadcrumb.py
    │   ├── test_local_scripts_tree_folder_expand.py  # expand must not rewrite folder label to Unnamed
    │   ├── test_local_scripts_tree_icons.py
    │   ├── test_local_scripts_tree_rename.py
    │   ├── test_new_item_popup.py
    │   └── test_new_local_script_popup.py
    ├── dialogs/                   # Dialog tests
    │   ├── test_ai_agents_page.py
    │   ├── test_ai_budget_page.py
    │   ├── test_ai_page.py
    │   ├── test_ai_provider_dialog.py
    │   ├── test_collection_runner.py
    │   ├── test_import_dialog.py
    │   ├── test_save_request_dialog.py
    │   └── test_settings_dialog.py
    ├── environments/              # Environment widget tests
    │   ├── test_environment_editor.py
    │   ├── test_environment_selector.py
    │   └── test_environment_sidebar_panel.py
    ├── panels/                    # Panel tests
    │   └── test_console_panel.py
    └── request/                   # Request/response editing tests
        ├── test_folder_editor.py
        ├── test_folder_editor_scripts.py
        ├── test_runner_panel.py
        ├── test_script_language.py
        ├── test_http_worker.py
        ├── test_request_editor.py
        ├── test_focus_section.py
        ├── test_get_request_data_persist.py
        ├── test_request_editor_auth.py
        ├── test_request_editor_binary.py
        ├── test_request_editor_graphql.py
        ├── test_request_editor_search.py
        ├── test_assertions_tab.py
        ├── test_response_viewer.py
        ├── test_response_replay_indicator.py
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

Shared helpers (`make_collection_dict`, `top_level_items`,
`finish_main_window_startup`) live in `tests/ui/conftest.py` and can be
imported via relative import from any subfolder:

```python
from ..conftest import finish_main_window_startup, make_collection_dict, top_level_items
```

Call ``finish_main_window_startup(window)`` after ``MainWindow`` construction
when a test depends on session tab restore (replaces ``load_finished.emit()``
alone).

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
