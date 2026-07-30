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
> 9. **App wiki** — when user-visible workflows or allowlisted scripting docs change,
>    update [`docs/user-guide/`](docs/user-guide/) per [`docs/user-guide/AGENTS.md`](docs/user-guide/AGENTS.md),
>    run `poetry run python scripts/build_app_wiki.py`, commit `data/app-wiki/`,
>    and run `python scripts/check_md_links.py`.

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
| [openhands-tools](.agents/skills/openhands-tools/SKILL.md) | Add/change Postmark AI tools on the OpenHands SDK — dedicated tools, not mutate+prompt hacks |
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
  `RunHistoryService`, `RequestHistoryService`, `AiConfig`, `AiLlmService`,
  `AiChatSessionService`, and key TypedDicts (`RequestLoadDict`, `VariableDetail`,
  `LocalOverride`, `RequestHistoryEntryDict`, `SendIdentityDict`, `AiModelEntry`,
  `AiChatSessionDict`, `AiChatMessageDict`).
- **HTTP subsystem:** Read `src/services/http/__init__.py` — re-exports
  `HttpService`, `GraphQLSchemaService`, `SnippetGenerator`,
  `SnippetOptions`, `HttpResponseDict`, `parse_header_dict`.
  Auth header injection lives in `src/services/http/auth_handler.py`.
  OAuth 2.0 token exchange lives in `src/services/http/oauth2_service.py`.
- **All DB models:** Read `src/database/database.py` — re-exports collection,
  environment, run-history, and local-script ORM models (`CollectionModel`,
  `RequestModel`, `SavedResponseModel`, `EnvironmentModel`, `RunHistoryModel`,
  `RunResultModel`, `RequestHistoryEntryModel`, `AiChatSessionModel`,
  `AiChatMessageModel`, `LocalScriptFolderModel`, `LocalScriptModel`, `SnippetModel`).
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
├── guides/                        # How-to guides (import parser, auth, widget, tests, signals, app-wiki)
├── user-guide/                    # End-user how-to (in-app AI knowledge base source)
└── contributing/                  # Coding conventions, testing, updating docs
data/
├── app-wiki/                      # Generated index + WIKI.md + scripting-api quickref (build_app_wiki.py)
└── snippets/                      # Script editor snippet JSON (javascript, python; see README.md)
scripts/
└── build_app_wiki.py              # Regenerate data/app-wiki/ from docs/user-guide + allowlisted scripting
src/
├── main.py                        # Entry point — configure_before_qapplication + QApplication + init_db()
├── qt_app_init.py                 # Hi-DPI bootstrap (before first QApplication; tests + app)
├── database/                      # Engine, models, repository
│   ├── data_paths.py              # project_root(), postmark_user_data_dir(), user_history_root(), session_attachments_dir()
│   ├── database.py                # init_db(), get_session(), migration; reconcile_orphans on startup
│   └── models/
│       ├── base.py                # DeclarativeBase
│       ├── collections/
│       │   ├── collection_repository.py   # CRUD for collections + requests
│       │   ├── collection_query_repository.py   # Read-only tree/breadcrumb/bulk projection queries
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
│           ├── import_refs_rewrite.py           # static relative import/export-from rewriter
│           └── model/
│               ├── local_script_folder_model.py
│               └── local_script_model.py  # ``module_format`` (``esm`` | ``commonjs``)
│       └── snippets/
│           ├── snippet_repository.py      # CRUD for user-authored script snippets
│           └── model/
│               └── snippet_model.py       # SnippetModel (context)
│       └── request_assertions/
│           ├── request_assertion_repository.py  # CRUD for declarative assertion rows
│           └── model/
│               └── request_assertion_model.py   # RequestAssertionModel (subject/operator/expected)
│       └── request_history/
│           ├── body_store.py                    # Atomic body/snapshot files under user_history_root()
│           ├── request_history_repository.py      # insert, get, list, prune, nullify_request_id
│           └── model/
│               └── request_history_entry_model.py  # RequestHistoryEntryModel (metadata in SQLite)
│       └── ai_chat/
│           ├── ai_chat_repository.py            # Session/message CRUD + disk delete (uuid.hex dir)
│           ├── ai_chat_query_repository.py      # list_sessions, search_messages (read-only)
│           └── model/
│               ├── ai_chat_session_model.py     # AiChatSessionModel (searchable index)
│               └── ai_chat_message_model.py     # AiChatMessageModel (transcript index)
├── services/                      # Service layer (UI ↔ DB bridge)
│   ├── collection_service.py      # CollectionService (static methods)
│   ├── document_import/           # PDF/DOCX extraction for AI document uploads
│   │   ├── models.py              # ExtractedDocument TypedDicts + warnings + DocumentImportError
│   │   ├── pdf_extract.py         # pypdf text + embedded images
│   │   ├── docx_extract.py        # python-docx body-order walk (table cells) + zip media reconcile
│   │   ├── ocr.py                 # normalize_png + optional rapidocr (extra `ocr`) + ImageCollector
│   │   ├── to_markdown.py         # ExtractedDocument -> Markdown (page markers, tables, [image N] markers)
│   │   └── extract.py             # path policy + dispatch
│   ├── ai/                        # AI / LLM provider configuration (OpenHands SDK)
│   │   ├── provider_catalog.py    # Static provider/model catalog (display defaults)
│   │   ├── reasoning_effort.py    # Reasoning-effort vocabulary + Ollama/LiteLLM helpers
│   │   ├── ai_budget_config.py    # ProviderBudgetEntry + AiBudgetConfig (QSettings ai/provider_budgets)
│   │   ├── budget_period.py       # period_window + anchor parsing for budget resets
│   │   ├── ai_config.py           # AiConfig + AiModelEntry — QSettings ai/models, ai/chat_model_id, ai/chat_session_id
│   │   ├── sdk_env.py             # ensure_openhands_env + connection timeouts
│   │   ├── ai_logging.py          # [postmark.ai] stderr log during provider setup
│   │   ├── ops/                   # setup_provider, fetch_provider_models, model_metadata
│   │   ├── llm_service.py         # AiLlmService — build/test openhands.sdk.LLM
│   │   └── chat/                  # Multi-session AI chat (OpenHands Conversation)
│   │       ├── agent_registry.py  # PostmarkAgentDef + DEFAULT_AGENT_ID + delegation tools
│   │       ├── subagent_registry.py # register_postmark_subagents (wiki/workspace-researcher, general-purpose)
│   │       ├── subagent_events.py # SubagentEventTracker + SubagentRunRecord parsing
│   │       ├── tool_activity_events.py # ToolActivityTracker + main-agent tool cards
│   │       ├── execute_events.py  # ExecuteRunRecord parsing + EventLog rebuild for send cards
│   │       ├── subagent_disk_registry.py # spawn id → disk path registry + session-scoped resolve
│   │       ├── workspace_snapshot.py # session-keyed GUI snapshot + parent session id resolve for subagents
│   │       ├── subagent_transcript.py # load_subagent_transcript_view + activity steps
│   │       ├── subagent_limits.py # max_parallel_subagents() — QSettings ai/max_parallel_subagents
│   │       ├── tool_registry.py   # register_postmark_tool / resolve_tools
│   │       ├── app_wiki/          # User KB paths, index build, query executor
│   │       │   ├── config.py      # Allowlisted doc roots + SCRIPTING_ALLOWLIST
│   │       │   ├── build_index.py # Generate data/app-wiki/index.md
│   │       │   ├── quickref.py    # scripting-api quickref from pm.d.ts/pm.pyi
│   │       │   ├── query.py       # execute_wiki_query (read-only)
│   │       │   └── schema.py      # WIKI.md body for tool workflow
│   │       ├── tools/             # OpenHands custom tools
│   │       │   ├── wiki_query.py  # postmark_wiki_query Action/Observation/Executor
│   │       │   ├── datetime_query/ # postmark_datetime — now + timezone/Unix convert
│   │       │   │   ├── ops.py     # resolve_zone, parse_when, execute_datetime_query
│   │       │   │   └── tool.py    # Action/Observation/Executor registration
│   │       │   ├── workspace_query/ # postmark_workspace_query (read-only workspace slices)
│   │       │   │   ├── constants.py
│   │       │   │   ├── helpers.py
│   │       │   │   ├── query_parse.py # fielded search operators (in:/method:/has:/…)
│   │       │   │   ├── goals.py       # multi-goal batching (max 4)
│   │       │   │   ├── render/      # live, scripts, settings + collections/ + search/ + insights/scans/ + variables/ + env_reach/ + dependencies/ + walkthrough/
│   │       │   │   └── executor.py
│   │       │   ├── workspace_mutate/ # postmark_workspace_mutate (Agent write ops)
│   │       │   │   ├── common.py      # WorkspaceMutateObservation + secrets policy helpers
│   │       │   │   ├── collection_ops.py # collection/request/assertion_set filter + apply
│   │       │   │   ├── local_ops.py   # local_script / local_script_folder
│   │       │   │   ├── debug_ops.py   # breakpoints/watches via merge_*_debug APIs
│   │       │   │   ├── settings_ops/  # allowlisted settings mutate
│   │       │   │   ├── data_ops/      # environment/globals/snippet/saved_response + session (active env, history, version restore)
│   │       │   │   └── tool.py        # Action/Observation/Executor + dispatch
│   │       │   ├── workspace_import/  # postmark_import (OpenAPI/WSDL/Postman/cURL)
│   │       │   │   ├── apply.py       # ImportService apply + optional root-name suffix + bridge events
│   │       │   │   ├── turn_guard.py  # suppress duplicate source imports within one chat turn
│   │       │   │   └── tool.py        # Action url|path|text|curl + optional collection_name_suffix
│   │       │   ├── document_import/   # postmark_document_import (read one uploaded chunk)
│   │       │   │   └── tool.py        # Action uri + chunk (+ path to upload on demand); chunk X of Y + next_step + vision ImageContent
│   │       │   ├── collection_draft/  # postmark_collection_draft (one chunk-sized request batch per call)
│   │       │   │   ├── state.py       # per-session CollectionDraft store
│   │       │   │   ├── config.py      # draft_script_language QSettings (default python)
│   │       │   │   ├── build.py       # draft -> ParsedCollection; URL {{var}} rewrite + auto variables
│   │       │   │   ├── ops.py         # start/add_requests/status/finish/discard
│   │       │   │   └── tool.py        # Action/Observation/Executor; only finish writes
│   │       │   ├── workspace_execute/ # postmark_workspace_execute (Agent send/run)
│   │       │   │   ├── tool.py        # Action/Observation + thin executor
│   │       │   │   └── dispatch.py    # operation dispatch → execution/* helpers
│   │       │   ├── delegate_tool.py # PostmarkDelegateTool (parallel subagent fan-out)
│   │       │   └── delegate_executor.py # PostmarkDelegateExecutor — registers disk paths at spawn
│   │       ├── mutation/          # Agent write confirm (auto-approve + ConfirmRisky), bridge, audit
│   │       │   ├── auto_approve.py # CATALOG + whitelist rules for ConfirmRisky skip
│   │       │   ├── bridge.py      # enqueue/drain GUI side-effect events
│   │       │   ├── security.py    # PostmarkWorkspaceSecurityAnalyzer + apply_confirmation_policy
│   │       │   └── audit.py       # append_mutation_audit
│   │       ├── execution/         # SharedSendCore — non-Qt send orchestration + result redaction
│   │       │   ├── send_core.py   # run_shared_send + apply_send_auth + agent send semaphore + body_mode
│   │       │   ├── agent_send.py  # run_agent_send_request/draft/replay/scripts + record_history
│   │       │   ├── agent_local_script.py  # run_agent_local_script via run_local_entry
│   │       │   ├── preview_url.py # resolve_execute_preview_url — Approve chrome (env-substituted + redacted)
│   │       │   ├── redact_result.py # redact_send_result for agent observations
│   │       │   ├── binary/        # Agent binary path allowlist
│   │       │   ├── graphql/       # fetch_graphql_schema
│   │       │   ├── codegen/       # generate_snippet ({{var}} auth)
│   │       │   ├── export/        # export_workspace_artifact
│   │       │   ├── oauth/         # oauth_get_token v1 (non-browser)
│   │       │   └── runner/        # run_agent_collection + run_agent_iterations (non-Qt)
│   │       ├── agent_tools.py     # tools_for_turn / max_iterations_for_turn (Ask/Plan/Agent)
│   │       ├── confirmation_payload.py # pending_actions_payload for Approve chrome
│   │       ├── attachments/       # Composer files copied in, converted to Markdown, read in chunks
│   │       │   ├── models.py      # StoredAttachment + postmark://uploaded/<name>.md vocabulary
│   │       │   ├── chunks.py      # split_markdown / chunk_at — bounded ordered DocumentChunk slices
│   │       │   ├── screenshots.py # vision flag; per-chunk images OR lazy cached OCR fallback
│   │       │   └── store.py       # store/list/resolve/read_markdown; attachments.json; ai_attachments/<hex>/
│   │       ├── provider_errors.py # summarize_provider_error — one-line transcript text for SDK/provider blobs
│   │       ├── response_text.py   # Turn-scoped thinking/answer extraction from SDK messages + stream chunks
│   │       ├── thinking_sections.py # Pack/unpack chronological thinking phases in one SQLite column
│   │       ├── compaction.py      # CHAT_CONDENSER_MAX_* constants for LLMSummarizingCondenser
│   │       ├── context_usage.py   # ContextUsageService + breakdown TypedDicts + SQLite fallback
│   │       ├── context_usage_sdk.py # OpenHands SDK View token accounting + compaction diagnostics
│   │       ├── message_usage.py   # Per-turn usage deltas, session spend rollups, assistant footer cost formatting
│   │       ├── spend_rollup.py    # Cross-session spend rollups for Settings → Budgets
│   │       ├── budget_status.py   # connection_budget_status() for chat enforcement + Spend flyout
│   │       ├── chat_run_limits.py # max_concurrent_chat_runs() — QSettings ai/max_concurrent_runs (default 10)
│   │       ├── run_registry.py    # ChatRunRegistry + _WorkerSignalBridge — concurrent per-session workers
│   │       ├── transcript_window.py # Turn-aware tail/older/newer slice helpers + paging constants
│   │       └── session_service.py # AiChatSessionService — SQLite index + SDK bridge
│   ├── assertion_service.py       # AssertionService + AssertionDict — declarative tests CRUD + compile
│   ├── local_script_service.py    # LocalScriptService + LocalScriptLoadDict
│   ├── snippet_service.py         # SnippetService — user snippet CRUD + loader cache invalidation
│   ├── environment_service.py     # EnvironmentService (variable substitution + TypedDicts)
│   ├── import_service.py          # ImportService (parse + persist)
│   ├── run_history_service.py     # RunHistoryService (run history CRUD bridge)
│   ├── history_retention_config.py # HistoryRetentionConfig + load_* — history/* QSettings (no UI imports)
│   ├── request_history_service.py # RequestHistoryService — gather_send_identity, record_send, get/list
│   ├── script_service.py          # ScriptService (script chain resolution)
│   ├── scripting/                 # Script execution sub-package
│   │   ├── local_path_policy.py   # Re-export path_policy (UI/service)
│   │   ├── local_virtual_paths.py # Re-export virtual_paths
│   │   ├── local_script_modules.py # pm.require("local:…") resolve + bundle
│   │   ├── local_scripts_project/ # Deno mirror, ESM import graph, local entry run/debug, LSP URI refcount
│   │   │   ├── mirror.py          # sync_all (prune orphans), sync_script, sync_closure; mirror_write_lock (RLock) serializes mirror writes
│   │   │   ├── deno_config.py     # ensure_ambient_pm, ensure_local_project_config
│   │   │   ├── import_graph.py    # regex static import/export-from + pm.require closure; esm_import_string_tail + relative_import_suggestions
│   │   │   ├── runner.py          # run_local_entry, debug_local_entry
│   │   │   ├── navigation.py      # resolve_esm_import_target_script_id
│   │   │   └── lsp_uri_registry.py
│   │   ├── debug_script_metadata.py # Persisted breakpoints/watches JSON (scripts.debug + local debug_metadata)
│   │   ├── dynamic_variables.py # Postman {{$…}} resolve (send-time + RestrictedPython replaceIn)
│   │   ├── json_schema_mini.py # Subset JSON Schema validator for pm.expect().jsonSchema()
│   │   ├── local_dependency_diagnostics.py # Direct local: dependency lint for host script editors
│   │   ├── local_script_require_refs.py  # Re-export require_refs_rewrite
│   │   ├── __init__.py            # TypedDicts (ScriptInput/Output, TestResult, etc.)
│   │   ├── engine.py              # ScriptEngine + run_debug_chain (re-exports find_pm_tests, find_top_level_statement_lines)
│   │   ├── pm_test_finder.py      # find_pm_tests — pm.test discovery for gutter
│   │   ├── pm_api_linter.py       # Diagnostic + pm/postman static walk helpers
│   │   ├── script_breakpoint_analyzer.py  # find_top_level_statement_lines — debugger gutter
│   │   ├── assertions_compiler.py # compile_to_js/py — declarative rows → pm.test blocks (source_name declarative)
│   │   ├── data_loader.py         # parse_data_file — CSV/JSON rows for data-driven runs
│   │   ├── context.py             # Context builders + normalize_events() + execute_sub_request() + globals persistence
│   │   ├── _subprocess_env.py     # safe_subprocess_env + restricted_python_subprocess_env (``POSTMARK_SANDBOX=1``) + terminate_process_tree + reap_zombie_children
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
│   │       ├── deno_scope.py      # CDP scope materialisation; deep expand object bindings across scopes; ``__pm_className__`` for CDP descriptions
│   │       ├── deno_debug.py      # Deno --inspect-brk + CDP (Chrome DevTools Protocol) step-through
│   │       └── py_debug.py        # Python settrace subprocess debug execution
│   ├── lsp/                       # Language Server Protocol (Deno LSP, jedi-language-server)
│   │   ├── transport.py           # LspTransport — JSON-RPC Content-Length + QThread reader
│   │   ├── client.py              # LspClient — initialize, didOpen/Change/Close, requests
│   │   ├── qt_lsp_offsets.py      # QTextDocument position ↔ LSP line/UTF-16 column
│   │   ├── pm_require_resolve.py    # npm/jsr registry latest lookup for unversioned pm.require LSP types
│   │   ├── js_lsp_preamble.py       # Triple-slash refs prepended to virtual JS buffers for Deno LSP
│   │   ├── npm_types_members.py     # @types .d.ts member extraction for npm pm.require completion fallback
│   │   ├── pm_require_types.py      # pm_require_index.ts generation + deno cache for npm/jsr specs
│   │   ├── local_script_lsp_prep.py # prepare_local_script_lsp_attach (mirror + index + closure; worker-safe)
│   │   ├── local_script_lsp_prep_worker.py # LocalScriptLspPrepWorker — QThread prep → GUI finalize
│   │   ├── stubs_generator.py     # pm.d.ts / pm.pyi from pm_api_schema
│   │   ├── server_registry.py     # LspRegistry — per-bucket warm_async; shutdown stops all _clients
│   │   ├── servers/spawn.py       # Off-GUI Popen + LspSpawnWorker; prepare_*_spawn metadata
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
│       ├── postman_parser.py      # Postman collection/environment parser (+ OpenAPI/WSDL file dispatch)
│       ├── curl_parser.py         # cURL command parser
│       ├── url_parser.py          # URL/raw-text auto-detect + try_parse_spec_text
│       ├── openapi/               # OpenAPI 3 / Swagger 2 (JSON/YAML) → collection
│       │   ├── parser.py
│       │   └── mapping.py
│       └── wsdl/                  # WSDL 1.1 → SOAP POST requests
│           ├── parser.py
│           └── soap.py
└── ui/                            # PySide6 widgets
    ├── main_window/               # Top-level MainWindow sub-package
    │   ├── window.py              # MainWindow widget + signal wiring
    │   ├── send_pipeline.py       # _SendPipelineMixin — HTTP send (re-exports debug-hover helpers)
    │   ├── history_navigation/    # _HistoryNavigationMixin — open global history into tabs + right History
    │   ├── send_pipeline_debug.py # _merge_debug_hover_values, _debug_hover_root_objects, …
    │   ├── send_pipeline_postresponse.py  # on_send_finished, run_post_response_script_with_live_response
    │   ├── send_pipeline_debug_session.py # on_debug_paused/step/finished, end_debug_ui
    │   ├── draft_controller.py    # _DraftControllerMixin — draft tab open/save
    │   ├── tab_controller.py      # _TabControllerMixin — tab open/close/switch
    │   ├── ai_chat_controller.py  # _AiChatControllerMixin — AI chat sessions + worker wiring
    │   ├── ai_chat_host_protocol.py # _AiChatHostProtocol — typing for composed mixins
    │   ├── ai_chat_runs.py        # _AiChatRunsMixin — ChatRunRegistry signal routing + re-attach; run-start workspace snapshot
    │   ├── mutation_drain/        # drain_mutation_bridge — mutate/execute GUI side effects
    │   ├── ai_chat_turn_finalize.py # _AiChatTurnFinalizeMixin — persist/stop/fail assistant turns
    │   ├── ai_chat_title.py       # _AiChatTitleMixin — AiChatTitleWorker lifecycle
    │   ├── session_restore.py   # Delayed, batched session tab restore after load_finished
    │   ├── startup_workers.py   # LocalProjectConfigWorker + AiModelBackfillWorker — delayed startup workers off GUI thread
    │   ├── tab_nav/               # Tab activation back/forward stacks
    │   │   ├── history.py         # _TabNavHistoryMixin — Go menu Ctrl+Alt+arrows
    │   │   └── __init__.py
    │   └── variable_controller.py # _VariableControllerMixin — env variable + sidebar management
    ├── local_scripts/             # Centre-pane local script editor
    │   ├── local_script_editor_widget.py  # LocalScriptEditorWidget — CodeEditorWidget + DB save
    │   └── script_filename.py     # Basename/extension display helpers for script tree + tabs
    ├── loading_screen.py          # Loading screen overlay widget
    ├── sidebar/                   # Sidebar rails + flyout panels
    │   ├── sidebar_widget.py      # RightSidebar (icon rail) + _FlyoutPanel
    │   ├── ai/                    # AI assistant chat panel
    │   │   ├── agent_mode_popup.py  # AgentModeButton + AiAgentModePopup (Agent / Ask / Plan)
    │   │   ├── chat_panel/        # AiChatPanel sub-package (panel, composer, context ring, scroll/)
    │   │   │   ├── panel.py       # AiChatPanel — transcript + composer
    │   │   │   ├── inline_edit.py # _ChatPanelInlineEditMixin — inline user-message edit
    │   │   │   ├── composer/      # AiChatComposer sub-package (docked + inline edit)
    │   │   │   │   ├── widget.py  # AiChatComposer — attachments, input, mode/model, send/stop
    │   │   │   │   ├── input.py   # ComposerInput — prompt editor (Escape → cancel in edit mode)
    │   │   │   │   ├── model_picker_button.py  # ModelPickerButton
    │   │   │   │   ├── attachments.py  # compose/split prompt attachment trailer + chip size resolvers
    │   │   │   │   └── budget_banner.py  # AiChatBudgetBanner (aiChatBudgetBanner)
    │   │   │   ├── context_ring_button.py  # ContextUsageRingButton (aiChatContextRing)
    │   │   │   ├── context_popup_mode_pill.py  # ContextPopupModePill (aiChatContextPopupMode)
    │   │   │   ├── context_usage_panel.py  # _ChatPanelContextUsageMixin — debounced refresh + popup
    │   │   │   └── scroll/        # Scroll-lock, smooth wheel, sticky prompt, widget_coords
    │   │   │       ├── scroll.py  # _ChatPanelScrollMixin — direction-based scroll-lock, turn-start anchor, viewport spacer, queued follow passes
    │   │   │       ├── smooth_scroll.py  # SmoothScroller — animated viewport wheel
    │   │   │       └── sticky_prompt.py  # _ChatPanelStickyPromptMixin — viewport sticky user prompt
    │   │   ├── chat_context_popup.py  # AiChatContextUsagePopup — Cursor-style breakdown flyout
    │   │   ├── chat_panel_streaming.py  # _ChatPanelStreamingMixin — stream orchestration + activity timer
    │   │   ├── chat_transcript_load.py  # Re-export shim → transcript.load
    │   │   ├── transcript/  # Virtualized transcript mixins
    │   │   │   ├── load.py  # _ChatPanelTranscriptLoadMixin — incremental session transcript load
    │   │   │   ├── older_loading_row.py  # TranscriptOlderLoadingRow — top-row older-page spinner
    │   │   │   ├── summarized_notice.py  # aiChatSummarizedNotice row after compaction
    │   │   │   └── window.py  # _ChatPanelTranscriptWindowMixin — tail paging, eviction, virtual spacers
    │   │   ├── chat_transcript_loading_row.py  # ChatTranscriptLoadingOverlay — viewport line animation during session load
    │   │   ├── chat_sessions/     # Session history popover + time formatting
    │   │   │   ├── history/       # Virtualized popover (model, delegate, worker, popup, actions_popup)
    │   │   │   │   ├── actions_popup.py  # SessionHistoryActionsPopup — Rename / Delete flyout
    │   │   │   │   ├── delegate.py     # SessionHistoryRowDelegate — ⋯ paint + editorEvent
    │   │   │   │   ├── model.py
    │   │   │   │   ├── popup.py          # AiSessionHistoryPopup
    │   │   │   │   └── worker.py         # SessionListLoader
    │   │   │   ├── history_popup.py  # Re-export shim → history.popup
    │   │   │   ├── session_title.py  # AiChatSessionTitle — hover + inline rename
    │   │   │   └── time_format.py
    │   │   ├── workers/           # AiChatWorker + AiChatTitleWorker (QThread)
    │   │   │   ├── chat_worker.py
    │   │   │   ├── context_usage_worker.py
    │   │   │   ├── session_load_worker.py
    │   │   │   └── title_worker.py
    │   │   ├── markdown/          # Custom assistant markdown HTML (fence split + Pygments code blocks)
    │   │   │   ├── fence_split.py
    │   │   │   ├── highlight_code.py
    │   │   │   ├── render.py
    │   │   │   ├── streaming_render.py  # StreamingMarkdownCache — incremental segment reuse
    │   │   │   └── streaming_table.py   # StreamingTableRenderer — row-by-row GFM tables + inline cell markdown during stream
    │   │   ├── message_bubble/    # ChatMessageBubble sub-package (bubble, markdown body, thought, activity)
    │   │   │   ├── bubble.py      # ChatMessageBubble — user bubble + assistant row; UserMessageStickyMetrics
    │   │   │   ├── markdown_content.py  # MarkdownContent + theme re-render registry
    │   │   │   ├── thought_section.py   # ThoughtSection collapsible block
    │   │   │   ├── activity_row.py      # AssistantActivityRow spinner row
    │   │   │   ├── wrapping_label.py    # _WrappingLabel — height-for-width QLabel
    │   │   │   ├── subagent/            # SubagentTaskCard + SubagentTaskGroup summary rows
    │   │   │   ├── tool_activity/       # ToolActivityCard + ToolActivityGroup main-agent tool rows
    │   │   │   │   ├── card.py
    │   │   │   │   └── group.py
    │   │   │   ├── confirm/             # PendingToolCard + PendingToolGroup (inline Agent Approve)
    │   │   │   │   ├── card.py
    │   │   │   │   └── group.py
    │   │   │   ├── execute/             # ExecuteResultCard + ExecuteResultGroup (agent send click-through)
    │   │   │   │   ├── card.py
    │   │   │   │   └── group.py
    │   │   │   ├── assistant_message/   # Assistant footer + actions popup
    │   │   │   │   ├── footer.py        # AssistantMessageFooterRow — model/cost + ⋯ menu
    │   │   │   │   ├── actions_popup.py # AiAssistantMessageActionsPopup — Fork chat / Copy message
    │   │   │   │   └── action_option_row.py # Shared ActionOptionRow hover rows
    │   │   │   └── user_message/        # UserMessageSection, footer, actions popup, sticky overlay
    │   │   │       ├── section.py       # Prompt body + attachment chip row (trailer lifted out of prose)
    │   │   │       ├── attachments/     # UserMessageAttachmentRow — clickable file chips above the prompt
    │   │   │       │   ├── row.py
    │   │   │       │   └── markdown_dialog.py # AttachmentMarkdownDialog — non-modal viewer for an upload's Markdown
    │   │   │       ├── footer.py
    │   │   │       ├── actions_popup.py  # Edit message + Fork chat
    │   │   │       ├── fade.py
    │   │   │       ├── overlay.py       # StickyUserPromptOverlay — viewport sticky clone
    │   │   │       └── overlay_edit_host.py  # Reparent inline AiChatComposer into sticky during edit
    │   │   ├── subagent_detail_dialog.py  # SubagentDetailDialog — non-modal task + markdown reply window
    │   │   ├── model_picker_edit.py  # AiModelPickerEditPanel flyout (context / thinking / reasoning)
    │   │   └── model_picker_popup.py  # AiModelPickerPopup — Cursor-style model list + gear
    │   ├── left_sidebar.py        # LeftSidebar — activity rail + stacked nav flyout pages
    │   ├── local_scripts_sidebar_panel.py  # Legacy empty shell (unused; MainWindow uses CollectionWidget)
    │   ├── snippets_sidebar_panel.py  # User snippets tree (language → category → leaf); search + section (i)
    │   ├── snippets_tree_constants.py  # Tree data roles / node kinds for snippets sidebar
    │   ├── snippets_tree_display.py  # Row layout + context/count labels for snippets tree
    │   ├── snippets_tree_delegate.py  # Language/snippet row painting (context tag on leaves)
    │   ├── snippets_tree_rename.py  # In-place snippet/category rename overlays
    │   ├── snippets_tree_context.py  # Snippets tree right-click menus (category/snippet CRUD)
    │   ├── variables_panel.py     # VariablesPanel — read-only variable display
    │   ├── snippet_panel.py       # SnippetPanel — inline code snippet generator
    │   ├── debug_inspector_split.py # DebugInspectorSplit — call stack + watches | scopes (horizontal splitter)
    │   ├── debug_scopes_panel.py  # DebugScopesPanel — debugScopesTree (locals / pm / globals only)
    │   ├── debug_panel.py         # DebugPanel facade — DebugControls + DebugInspectorSplit
    │   ├── debug_call_stack_panel.py  # CallStackPanel — frame list + frame_selected
    │   ├── debug_watch_in_tree.py # Watches section rows + format_watch_display / rebuild_watch_rows
    │   ├── saved_responses/           # Saved responses sub-package
    │   │   ├── panel.py               # SavedResponsesPanel — saved example list/detail flyout
    │   │   ├── search_filter.py       # _PanelSearchFilterMixin — body search/filter
    │   │   ├── helpers.py             # Formatting helpers (body size, language detect, etc.)
    │   │   └── delegate.py            # Custom delegate for saved response list items
    │   └── history/                 # Send-history flyouts (right per-request + left global); date_filter/ popup + mixin
    │       ├── panel.py               # HistoryPanel — list/detail + requestHistorySearch
    │       ├── global_mode/           # Global mode mixin + Enter key filter (left rail)
    │       ├── panel_detail_tabs.py   # Read-only Headers / Request Headers / Request Body tabs
    │       ├── delegate.py            # HistoryEntryDelegate — status badge + date group headers
    │       ├── helpers.py             # Date grouping, list populate, row meta, sent headers
    │       └── search_filter.py       # Re-exports body search mixin
    ├── styling/                   # Visual theming and icons
    │   ├── theme.py               # Palettes, colours, status bar / left-rail chrome, badge/tree geometry, left-nav panel margins, method_color(), status_color()
    │   ├── language_icons.py      # Brand SVG pixmaps for JS / TS / Python tiles
    │   ├── theme_manager.py       # ThemeManager — QPalette + QSettings
    │   ├── tab_settings_manager.py # TabSettingsManager — request-tab QSettings bridge (preview, limits, activate-on-close, wrap mode)
    │   ├── history_settings_manager.py # HistorySettingsManager — wraps history_retention_config for Settings UI
    │   ├── global_qss.py          # build_global_qss() — global stylesheet builder
    │   └── icons.py               # Phosphor font-glyph icon provider (phi(), phi_qss_image_url())
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
    │   │   ├── editor_lsp_glue.py    # attach_lsp, finalize_local_script_lsp_attach, detach_lsp, signature/hover glue
    │   │   ├── lsp_integration.py # EditorLspAdapter — LSP sync + diagnostics; local-script attach accepts prep= to skip redundant mirror/index
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
    │   │       ├── path_completions/ # pm.require('local:…') + ESM relative import path items
    │   │       │   └── items.py
    │   │       ├── mixin.py       # _CompletionMixin — triggers, filtering, parameter hint + Ctrl+hover symbol doc wiring
    │   │       ├── parameter_hint.py # ParameterHintPopup — floating call-signature hint
    │   │       ├── popup.py       # CompletionPopup — floating autocomplete widget
    │   │       └── symbol_doc_popup.py # SymbolDocPopup — Ctrl+hover / Ctrl+Q quick-doc tooltip
    │   ├── busy_spinner.py        # BrailleSpinner — shared inline busy animation
    │   ├── info_popup.py          # InfoPopup (QFrame) base + ClickableLabel
    │   ├── sidebar_section_info.py # SidebarSectionInfoPopup — (i) help for sidebar sections
    │   ├── sidebar_tree_row_info.py # Trailing row (i) paint/hit-test for local-script tree leaves
    │   ├── tree_rename_overlay.py   # TreeRenameClickAway — app-wide click-away / Escape for tree rename QLineEdit
    │   ├── lazy_editor_placeholder.py # LazyEditorPlaceholder — progress + caption until Body/Scripts editors mount
    │   ├── key_value_column_widths.py # QSettings JSON persistence for Key/Value widths
    │   ├── key_value_table.py     # Reusable key-value editor widget
    │   ├── key_value_bulk.py      # Bulk text serialize/parse for key-value tables
    │   ├── query_string.py        # URL query parse/build (raw; no encode/decode)
    │   ├── key_value_table_delegate.py # Variable {{…}} highlight delegate for key-value cells
    │   ├── search_replace_bar.py  # SearchReplaceBar — find/replace + go-to-line for CodeEditorWidget
    │   ├── deno_download_worker.py # DenoDownloadWorker — QThread background Deno download (banner + settings)
    │   ├── debug_value_tree.py    # Debug tree helpers (CLASSNAME_KEY, attach_selectable_cell_widgets, debug_tree_cell_text, fill_tree_item, populate_debug_tree, source_dot_icon, make_debug_value_tree)
    │   ├── runtime_banner.py      # RuntimeBanner — Deno install/configure prompt for JS editors
    │   ├── snippets/              # Script snippet palette (loader + SnippetsPopup)
    │   │   ├── loader.py          # load_snippets — merges data/snippets/*.json + DB user snippets
    │   │   ├── popup.py           # SnippetsPopup — search + grouped list; read-only insert (accent user rows)
    │   │   └── snippet_capture_dialog.py  # Create/edit snippets (delete via sidebar context menu); CodeEditorWidget body
    │   ├── variable_line_edit.py  # VariableLineEdit — QLineEdit with {{var}} highlighting + hover popup
    │   └── variable_popup.py      # VariablePopup — singleton hover popup for variable details
    ├── collections/               # Collection sidebar
    │   ├── collection_header.py
    │   ├── collection_widget.py  # CollectionWidget — refresh_collections + startup _start_fetch
    │   ├── new_item_popup.py      # NewItemPopup — Postman-style icon grid popup
    │   ├── new_local_script_popup.py  # NewLocalScriptItemPopup — Script / Folder tiles
    │   └── tree/                  # Tree widget sub-package
    │       ├── constants.py
    │       ├── draggable_tree_widget.py
    │       ├── collection_tree.py # CollectionTree widget
    │       ├── tree_actions.py    # _TreeActionsMixin — context menus, rename, delete
    │       ├── tree_overlay_rename.py # _TreeOverlayRenameMixin — overlay rename + click-away
    │       └── collection_tree_delegate.py  # Custom delegate for method badges
    ├── dialogs/                   # Modal dialogs
    │   ├── settings/
    │   │   ├── history_page.py    # Settings → History page (retention, bodies, storage path)
    │   │   ├── ai_provider_dialog.py # Add/edit provider credentials + model (in-dialog Test connection)
    │   │   ├── ai_provider_workers.py # Setup worker + AiRefreshUiBridge (GUI-thread refresh slot)
    │   │   ├── ai_agents/         # Settings → AI → Agents (concurrent runs, mutations, auto-approve)
    │   │   ├── ai_budget/         # Settings → AI → Budgets (page, row_actions, period_reset_panel, limits_dialog, breakdown_dialog)
    │   │   ├── ai_page.py         # Settings → AI → Models tree; refresh updates children only
    │   │   └── ai_page_actions.py # Provider actions + resizable tree header (QSettings)
    │   ├── collection_runner/
    │   │   ├── __init__.py        # Re-exports RunnerConfigView, RunnerResultsView, RunnerWorker
    │   │   ├── config.py          # RunnerConfigView (env selector, request checklist, data file, iterations, delay)
    │   │   ├── results.py         # RunnerResultsView (summary + results table + detail panel + export)
    │   │   └── worker.py          # RunnerWorker (QThread), env var substitution, scripts_enabled (imports parse_data_file from services)
    │   ├── import_dialog.py
    │   ├── save_request_dialog.py  # Save draft request to collection
    │   └── settings_dialog.py     # Settings (theme, tabs, Scripting, History, AI, private packages)
    ├── environments/              # Environment management widgets
    │   ├── environment_editor.py  # EnvironmentEditorWidget + EnvironmentEditorDialog
    │   ├── environment_selector.py
    │   └── environment_sidebar_panel.py
    ├── panels/                    # Bottom / side panels
    │   └── console_panel.py
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
        │   │   ├── assertions_guide.py  # AssertionsHelpDialog + How this works button
        │   │   ├── assertions_tab.py    # AssertionsTab — subject/operator/expected rows + guide
        │   │   └── assertions_mixin.py  # _AssertionsMixin — lazy tab + AssertionService persistence
        │   ├── data_runner/         # Inline data-driven script runner (D3)
        │   │   └── panel.py         # DataRunnerPanel — CSV/JSON picker + Run iterations
        │   └── scripts/             # Scripts sub-package
        │       ├── script_language.py # codes: javascript | typescript | python; detect/heuristics, display, normalise
        │       ├── script_editor_pane/ # ScriptEditorPane — reusable toolbar + editor + output stack
        │       ├── debug_metadata_persist.py # _DebugMetadataPersistMixin — debounced scripts.debug DB + draft session
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
        │       ├── lsp_problems_tab.py # ScriptLspProblemsTab — LSP + ``[local:…]`` dependency rows; click opens local script tab
        │       ├── local_dependency_warn.py # Warn-only Send/Run when direct local: dependencies have errors
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
        │   ├── replay_indicator.py  # ResponseReplayIndicator — replayed-send status corner pill
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
        │   └── tab_manager.py       # TabManager + TabContext (nav_token, is_debugging, local_overrides, draft_name)
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
│   │   ├── test_run_history_repository.py
│   │   ├── test_ai_chat_migration.py
│   │   ├── test_ai_chat_repository.py
│   │   ├── test_data_paths.py
│   │   ├── test_request_history_body_store.py
│   │   └── test_request_history_repository.py
│   ├── ui/                        # UI helper unit tests (may need qapp)
│   │   └── sidebar/ai/            # Chat markdown renderer tests
│   │       ├── test_chat_markdown_fence_split.py
│   │       ├── test_chat_markdown_highlight.py
│   │       ├── test_chat_markdown_highlight_cache.py
│   │       ├── test_chat_markdown_render.py
│   │       ├── test_chat_markdown_streaming.py
│   │       ├── test_chat_markdown_streaming_render.py
│   │       ├── test_streaming_table.py
│   │       ├── test_markdown_content_height.py
│   │       ├── test_markdown_content_links.py  # postmark:// deep-links vs https external
│   │       ├── test_bubble_stream_row_height.py
│   │       └── test_composer_attachments.py  # attachment paths appended to the prompt
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
│       ├── test_script_local_py_require.py
│       ├── test_script_service.py
│       ├── test_script_vendor.py
│       ├── test_script_vendor_libs.py
│       ├── test_data_loader.py
│       ├── test_script_run_worker_iterations.py
│       ├── test_script_version_service.py
│       ├── test_assertions_compiler.py
│       ├── test_deno_manager.py
│       ├── test_runtime_settings.py
│       ├── test_request_history_service.py
│       ├── ai/                    # AI config + LLM service tests
│       │   ├── test_ai_budget_config.py
│       │   ├── test_budget_period.py
│       │   ├── test_spend_rollup.py
│       │   ├── test_budget_status.py
│       │   ├── test_chat_run_limits.py
│       │   ├── test_chat_run_registry.py
│       │   ├── test_chat_run_registry_streaming.py
│       │   ├── test_ai_config.py
│       │   ├── test_chat_session_service.py
│       │   ├── test_context_usage.py
│       │   ├── test_message_usage.py
│       │   ├── test_session_transcript_window.py
│       │   ├── test_postmark_agent_registry.py
│       │   ├── test_subagent_registry.py
│       │   ├── test_subagent_events.py
│       │   ├── test_tool_activity_events.py
│       │   ├── test_execute_events.py  # Agent execute observation → clickable card records
│       │   ├── test_subagent_disk_registry.py
│       │   ├── test_subagent_transcript.py
│       │   ├── test_subagent_limits.py
│       │   ├── test_delegate_tool.py
│       │   ├── test_build_app_wiki.py
│       │   ├── test_wiki_query_tool.py
│       │   ├── test_datetime_query_tool.py  # postmark_datetime now + timezone convert
│       │   ├── test_workspace_snapshot.py
│       │   ├── test_workspace_query_tool.py
│       │   ├── test_workspace_query_audit.py
│       │   ├── test_workspace_query_variable.py
│       │   ├── test_workspace_query_insights.py  # health insights, fielded search, goals, env diff
│       │   ├── test_workspace_query_explorer.py # env_reach, dependencies, walkthrough, dead/token/response_drift
│       │   ├── test_send_core_parity.py # SharedSendCore parity vs HttpSendWorker path
│       │   ├── test_confirmation_spike.py # ConfirmRisky pause/resume/reject + whitelist
│       │   ├── test_confirmation_payload.py # human_preview + Approve title/detail (no raw tool names)
│       │   ├── test_agent_tools_for_turn.py # Ask/Plan/Agent tools_for_turn (Agent always has write tools)
│       │   ├── test_agent_tools_for_turn.py # Ask/Plan/Agent × mutations on/off
│       │   ├── test_workspace_security.py # analyzer HIGH/LOW + confirmation policy
│       │   ├── test_mutation_bridge.py # enqueue/drain GUI bridge
│       │   ├── test_mutation_auto_approve.py # whitelist CRUD + Phase 2 catalog
│       │   ├── test_workspace_mutate_collections.py # mutate CRUD + assertion_set
│       │   ├── test_document_import_tool.py # chunk paging, coverage, URI resolution, on-demand upload
│       │   ├── test_chat_attachment_chunks.py # chunk size/order/coverage; fences never split
│       │   ├── test_chat_attachment_screenshots.py # vision gate: images vs lazy cached OCR fallback
│       │   ├── test_chat_attachment_store.py # copy-in, Markdown conversion, URIs, session-delete cleanup
│       │   ├── test_provider_errors.py    # malformed tool call + unreachable provider summaries
│       │   ├── test_collection_draft_tool.py # incremental draft ops, finish persistence, risk mapping
│       │   ├── test_collection_draft_enrichment.py # params/descriptions/scripts/vars/language setting
│       │   ├── test_fabricated_link_guard.py # strip collection links no tool produced this turn
│   ├── document_import/               # PDF/DOCX extraction service tests
│   │   ├── fixtures/sample.pdf
│   │   ├── test_extract_pdf.py
│   │   ├── test_extract_docx.py
│   │   ├── test_ocr.py
│   │   ├── test_path_policy.py
│   │   └── test_to_markdown.py
│       │   ├── test_workspace_mutate_local.py # local scripts + secrets/auth/env/snippet mutate
│       │   ├── test_workspace_mutate_session.py # active env, history delete, import, version restore, folder events
│       │   ├── test_workspace_mutate_debug_metadata.py # breakpoints/watches merge mutate
│       │   ├── test_workspace_mutate_settings.py # allowlisted settings mutate
│       │   ├── test_binary_body.py # binary path policy + HttpService byte send
│       │   ├── test_agent_graphql_fetch.py # execute fetch_graphql_schema
│       │   ├── test_agent_codegen_export.py # generate_snippet + export artifact
│       │   ├── test_agent_oauth_get_token.py # oauth_get_token v1 credential-blind
│       │   ├── test_agent_runner_execute.py # run_collection + run_iterations execute ops
│       │   ├── test_agent_local_script_execute.py # run_agent_local_script + execute dispatch
│       │   ├── test_agent_send_execute.py # history record + scripts + execute dispatch
│       │   ├── test_pm_api_quickref.py
│       │   ├── test_model_metadata.py
│       │   └── test_llm_service.py
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
    ├── main_window/
    │   └── test_ai_chat_controller.py  # AI chat controller + concurrent run registry paths
    │   └── test_ai_chat_deeplink.py  # postmark:// deep-link navigation + focus_section
    │   └── test_ai_chat_attachments.py # attached document copied in and delivered to the model
    │   └── test_main_window_ai_session_restore.py  # Persist + reopen last chat session on startup
    │   └── test_ai_chat_registry_streaming.py # E2E incremental streaming via ChatRunRegistry
    │   └── test_ai_concurrent_runs.py  # E2E concurrent runs: New chat, session switch, docked send
    │   └── test_session_history_switch.py  # MainWindow session history switch during transcript load
    ├── test_main_window.py
    ├── test_main_window_tabs_navigation.py # Wrapped tab deck shortcuts + search tests
    ├── test_main_window_tab_nav_history.py # Go menu tab activation back/forward
    ├── test_main_window_save.py   # SaveButton + RequestSaveEndToEnd tests
    ├── test_main_window_draft.py  # Draft tab open/save lifecycle tests
    ├── test_main_window_session.py # Tab session persistence (save/restore) tests
    ├── styling/                   # Theme and icon tests
    │   ├── test_theme_manager.py
    │   └── test_icons.py
    ├── sidebar/                   # Sidebar widget tests
    │   ├── test_ai_chat_panel.py
    │   ├── test_ai_chat_worker.py
    │   ├── test_ai_pending_tool_cards.py  # Inline Allow/Reject/Always allow on streaming bubble
    │   ├── test_ai_tool_activity_cards.py # Main-agent tool activity cards + execute handoff
    │   ├── test_ai_session_history_popup.py
    │   ├── test_ai_active_run_badge.py
    │   ├── test_ai_user_message_attachments.py  # User-bubble attachment chips (trailer → chips, sizes, legacy)
    │   ├── test_sidebar.py
    │   ├── test_left_sidebar.py
    │   ├── test_left_sidebar_global_history.py
    │   ├── test_variables_panel.py
    │   ├── test_snippet_panel.py
    │   ├── test_debug_panel.py
    │   ├── test_saved_responses_panel.py
    │   ├── test_request_history_panel.py
    │   ├── test_global_history_panel.py
    │   └── test_global_history_open_navigation.py
    ├── widgets/                   # Shared component tests
    │   ├── test_code_editor.py
    │   ├── test_code_editor_folding.py
    │   ├── test_code_editor_painting.py
    │   ├── test_code_editor_memory.py
    │   ├── test_code_editor_minimap.py
    │   ├── test_code_editor_variables.py
    │   ├── test_completion_engine.py
    │   ├── test_completion_engine_top_level.py
    │   ├── test_completion_engine_local_paths.py
    │   ├── test_esm_import_completion_accept.py
    │   ├── test_lsp_diagnostic_debounce.py
    │   ├── test_no_debug_on_keystroke.py
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
    │   ├── test_collection_refresh.py  # refresh_collections + active folder highlight + open-tab reload
    │   ├── test_new_item_popup.py
    │   └── test_new_local_script_popup.py
    ├── dialogs/                   # Dialog tests
    │   ├── test_collection_runner.py
    │   ├── test_ai_agents_page.py
    │   ├── test_ai_budget_page.py
    │   ├── test_ai_page.py
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
        ├── conftest.py              # make_request_dict fixture factory
        ├── test_folder_editor.py
        ├── test_folder_editor_scripts.py
        ├── test_runner_panel.py
        ├── test_http_worker.py
        ├── test_request_editor.py
        ├── test_focus_section.py
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

> **CRITICAL — Do not disable pytest parallelism for full-suite runs.**
> Use plain `poetry run pytest` so `pyproject.toml` addopts apply (`-n auto`,
> `--dist loadfile`, `--timeout=120`, `--max-worker-restart=8`). Worker count is
> capped at 8 via ``pytest_xdist_auto_num_workers`` in ``tests/conftest.py``.
> in about **2–3 minutes**.
> **Never** run the full suite with `-n0` or `--numprocesses=0` for routine
> validation — single-process runs take **~10+ minutes** and feel hung.
> Reserve `-n0` only for debugging one file or one failing test (e.g.
> `poetry run pytest tests/ui/sidebar/test_chat_panel_resize.py -q -n0`).

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

## CRITICAL — A failing test is a finding, not an obstacle

When a previously-passing test fails after your change, the **default
assumption is that you introduced a regression**.  You MUST fix the code,
not the test.

**Never weaken, delete, skip, loosen, or "update" an existing test to make
it pass** unless you can first prove the test itself is wrong.  Editing a
test so it accepts the new (broken) behaviour is a **bug**, treated
identically to shipping the regression.  "It was easier to change the test"
is never valid.

Before touching ANY existing assertion that started failing, answer all
three **in writing** in your response:

1. **Was this test passing before my change?**  Determine this with
   **read-only** git commands only — `git diff` / `git diff HEAD` to see what
   you changed, `git show HEAD:<path>` to read the pre-change version,
   `git log -p -- <path>` for history.  **NEVER run `git stash`** (see Git
   safety below).  If a test you did not edit is now red, presume your change
   caused a regression.
2. **Does the test encode an intended contract?**  Read the test name, its
   assertions, and the code it covers.  If it asserts real behaviour users
   rely on, the test is right and your code is wrong.
3. **Has the spec genuinely changed?**  A test may only be updated if the
   USER explicitly requested a behaviour change that intentionally
   invalidates the old contract.  If so, state which requirement changed and
   why the old assertion no longer applies.

If you cannot satisfy #3 with an explicit, user-stated requirement, **fix
the production code**.

This rule targets **regressions in existing assertions** — it does not
discourage writing or adjusting tests for genuinely new code you are adding.

**Establish a green baseline first.**  Before implementing a feature that
touches existing behaviour, run the affected tests so you know they pass.
After your change, any newly-red test is a regression you caused until
proven otherwise.

See [`tests/AGENTS.md`](tests/AGENTS.md) for the explicit list of forbidden
test edits.

## Git safety

> **NEVER run `git stash` (or `git stash pop` / `apply` / `drop`) under any
> circumstance without the USER's direct, explicit approval first.**  It is a
> destructive, state-hiding operation.  To inspect prior behaviour, use
> read-only commands (`git diff`, `git diff HEAD`, `git log -p`,
> `git show <ref>:<path>`) instead.

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
