---
name: service-repository-reference
description: Complete catalogue of all repository functions, service methods, and TypedDict schemas in the Postmark codebase. Use when adding new service methods, repository functions, TypedDicts, or when you need to know what API exists in the service or database layer.
---

# Service and repository reference

Complete catalogue of every public function in the repository layer and
every method in the service layer, plus all TypedDict schemas used for
cross-layer data interchange.

## Repository function catalogue

### Collection repository — CRUD (`collection_repository.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `create_new_collection(name, parent_id?)` | `CollectionModel` | Create a folder |
| `rename_collection(collection_id, new_name)` | `None` | Update name |
| `delete_collection(collection_id)` | `None` | Delete + cascade children and requests |
| `create_new_request(collection_id, method, url, name, ...)` | `RequestModel` | Create a request |
| `rename_request(request_id, new_name)` | `None` | Update name |
| `delete_request(request_id)` | `None` | Delete a single request |
| `duplicate_request(request_id)` | `RequestModel` | Clone request + saved responses + assertions; unique `` Copy`` name |
| `unique_duplicate_request_name(base_name, existing_names)` | `str` | ``{base} Copy`` or ``{base} Copy N`` |
| `update_request_collection(request_id, new_collection_id)` | `None` | Move request |
| `update_collection_parent(collection_id, new_parent_id)` | `None` | Move collection |
| `save_response(request_id, ...)` | `int` | Persist a response snapshot, return its ID |
| `rename_saved_response(response_id, new_name)` | `None` | Rename a saved response |
| `delete_saved_response(response_id)` | `None` | Delete a saved response |
| `duplicate_saved_response(response_id)` | `int` | Copy a saved response, return new ID |
| `update_collection(collection_id, **fields)` | `None` | Generic field update on a collection |
| `update_request(request_id, **fields)` | `None` | Generic field update on a request |

### Collection query repository (`collection_query_repository.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `fetch_all_collections()` | `dict[str, Any]` | All root collections as nested dict |
| `get_collection_by_id(collection_id)` | `CollectionModel \| None` | PK lookup |
| `get_request_by_id(request_id)` | `RequestModel \| None` | PK lookup |
| `get_request_auth_chain(request_id)` | `dict[str, Any] \| None` | Walk parent chain for auth config |
| `get_request_inherited_auth(request_id)` | `dict[str, Any] \| None` | Resolve inherited auth for a request (walks ancestors) |
| `get_collection_inherited_auth(collection_id)` | `dict[str, Any] \| None` | Resolve inherited auth for a collection (walks ancestors) |
| `get_request_variable_chain(request_id)` | `dict[str, str]` | Collect variables up the parent chain |
| `get_request_variable_chain_detailed(request_id)` | `dict[str, tuple[str, int]]` | Variables with source collection IDs |
| `get_collection_variable_chain_detailed(collection_id)` | `dict[str, tuple[str, int]]` | Variables from collection's parent chain with source IDs |
| `get_request_breadcrumb(request_id)` | `list[dict[str, Any]]` | Ancestor path for breadcrumb bar |
| `get_collection_breadcrumb(collection_id)` | `list[dict[str, Any]]` | Ancestor path for collection breadcrumb |
| `get_saved_responses_for_request(request_id)` | `list[dict[str, Any]]` | Saved responses for a request |
| `get_saved_response(response_id)` | `dict[str, Any] \| None` | Single saved response detail by ID |
| `count_collection_requests(collection_id)` | `int` | Total request count in folder subtree |
| `fetch_request_scripts_for_ids(ids)` | same shape | Script/events for given request ids only |
| `fetch_request_fields_for_ids(ids)` | `(id, name, body, body_mode, body_options, description, headers, auth, params)` | Bounded request field fetch for workspace search |
| `fetch_folder_scripts_for_ids(ids)` | `(id, name, events)` | Folder-level script events for workspace search |
| `fetch_assertion_counts_for_ids(ids)` | `(request_id, total, enabled)` | Bulk declarative assertion counts for `scope=insights` |
| `count_all_collections()` | `int` | Total folder row count |
| `count_all_requests()` | `int` | Requests with a valid collection parent |
| `get_recent_requests_for_collection(collection_id, ...)` | `list[dict[str, Any]]` | Recently modified requests in subtree |

### Import repository (`import_repository.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `import_collection_tree(parsed)` | `dict[str, int]` | Atomic bulk-import of a full collection tree |

### Environment repository (`environment_repository.py`)

| Function | Returns | Purpose |
|----------|---------|----------|
| `fetch_all_environments()` | `list[dict[str, Any]]` | All environments as dicts |
| `create_environment(name, values?)` | `EnvironmentModel` | Create an environment |
| `get_environment_by_id(id)` | `EnvironmentModel \| None` | PK lookup |
| `rename_environment(id, new_name)` | `None` | Update name |
| `delete_environment(id)` | `None` | Delete environment |
| `update_environment_values(id, values)` | `None` | Replace key-value pairs |

### Run history repository (`run_history_repository.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `create_run(collection_id, source?)` | `RunHistoryModel` | Start a new run record |
| `finish_run(run_id, **stats)` | `None` | Finalise a run with duration, test counts, status |
| `add_result(run_id, **fields)` | `RunResultModel` | Add a per-request result |
| `get_runs_for_collection(collection_id, limit?)` | `list[RunHistoryModel]` | Runs for a collection, newest first |
| `get_run_results(run_id)` | `list[RunResultModel]` | Results for a run, ordered by ID |
| `delete_run(run_id)` | `bool` | Delete a single run (True if found) |
| `delete_runs_for_collection(collection_id)` | `int` | Delete all runs for a collection, return count |

### Request history repository (`request_history_repository.py`)

Metadata in SQLite; bodies/snapshots via `body_store.py` under
`user_history_root()` (`postmark_user_data_dir()/history`).

| Function | Returns | Purpose |
|----------|---------|---------|
| `insert_entry(...)` | `dict[str, Any]` | Insert row + write body/snapshot files; truncate body to `max_response_bytes` |
| `get_entry(entry_id)` | `dict \| None` | Row + loaded body/snapshot bytes |
| `list_entries_for_sidebar(search?, limit?)` | `list[dict]` | Newest-first global list (left rail); search always capped by `limit` |
| `list_for_request(request_id, search?, limit?)` | `list[dict]` | Newest-first rows for one persisted `request_id`; search capped |
| `delete_entry(entry_id)` | `bool` | Delete one row and on-disk payload files |
| `prune_old_entries(retention_days, max_items_per_day, unlimited_per_day)` | `None` | Drop rows older than retention and over per-day cap |
| `nullify_request_id(request_id)` | `None` | Set `request_id` NULL when collection request deleted |
| `local_date(executed_at)` | `date` | Local calendar date for per-day caps |

`body_store`: `write_body`, `read_body`, `write_request_snapshot`,
`read_request_snapshot`, `delete_entry_files`, `reconcile_orphans`.

### Local script repository (`local_script_repository.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `create_folder(name, parent_id?)` | `LocalScriptFolderModel` | Create folder |
| `create_script(folder_id, name, *, language, module_format="esm", content)` | `LocalScriptModel` | Create script; ``module_format`` validated via ``_normalize_module_format`` |
| `rename_script_and_rewrite_refs(script_id, new_name, *, language?, module_format?)` | `int` | Rename + rewrite ``pm.require("local:…")`` when virtual path changes (``.js`` ↔ ``.cjs``) |
| `move_script_and_rewrite_refs(script_id, new_folder_id)` | `int` | Move + rewrite local refs |
| `update_script_content(script_id, content, language?, module_format?)` | `None` | Persist editor body |

``module_format="commonjs"`` is only valid when ``language=="javascript"``; otherwise
``ValueError``. TypeScript/Python rows always store ``"esm"``.

### Local script query repository (`local_script_query_repository.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `fetch_all_local_scripts_tree()` | `dict[str, Any]` | Nested tree; script nodes include ``module_format`` |
| `fetch_local_script_contents_for_ids(ids)` | `list[tuple[int, str, str]]` | Bulk ``(id, name, content)`` for search |
| `get_script_by_id(script_id)` | `LocalScriptModel \| None` | PK lookup |
| `get_local_script_breadcrumb(script_id)` | `list[dict[str, Any]]` | Breadcrumb segments |

## Service method catalogue

### CollectionService

All methods are `@staticmethod`.  "Passthrough" means the method delegates
directly to the repository with no added logic.

| Method | Validation added over repository |
|--------|----------------------------------|
| `fetch_all()` | Logging only |
| `get_collection(id)` | Passthrough |
| `get_request(id)` | Passthrough |
| `fetch_request_scripts_for_ids(ids)` | Passthrough |
| `fetch_request_fields_for_ids(ids)` | Passthrough |
| `fetch_folder_scripts_for_ids(ids)` | Passthrough |
| `fetch_assertion_counts_for_ids(ids)` | Passthrough |
| `count_all_collections()` | Passthrough |
| `count_all_requests()` | Passthrough |
| `create_collection(name, parent_id?)` | `name.strip()`, rejects empty |
| `rename_collection(id, new_name)` | `new_name.strip()`, rejects empty |
| `delete_collection(id)` | Logging only |
| `move_collection(id, new_parent_id)` | Rejects `id == new_parent_id` (no deeper cycle check) |
| `create_request(collection_id, method, url, name, ...)` | `name.strip()`, `method.upper()`, rejects empty |
| `rename_request(id, new_name)` | `new_name.strip()`, rejects empty |
| `delete_request(id)` | Logging only |
| `duplicate_request(id)` | Logging only; returns new `RequestModel` |
| `move_request(id, new_collection_id)` | Passthrough |
| `update_collection(id, **fields)` | Passthrough (generic field update) |
| `update_request(id, **fields)` | Passthrough (generic field update) |
| `get_request_auth_chain(request_id)` | Passthrough |
| `get_request_inherited_auth(request_id)` | Passthrough |
| `get_collection_inherited_auth(collection_id)` | Passthrough |
| `get_request_variable_chain(request_id)` | Passthrough |
| `get_request_breadcrumb(request_id)` | Passthrough |
| `get_collection_breadcrumb(collection_id)` | Passthrough |
| `get_folder_request_count(collection_id)` | Passthrough |
| `get_recent_requests(collection_id, ...)` | Passthrough |
| `get_saved_responses(request_id)` | Formats `created_at` and `body_size` into `SavedResponseDict` |
| `get_saved_response(response_id)` | Formats one row into `SavedResponseDict` |
| `save_response(request_id, ...)` | Passthrough |
| `rename_saved_response(response_id, new_name)` | `new_name.strip()`, rejects empty |
| `delete_saved_response(response_id)` | Logging only |
| `duplicate_saved_response(response_id)` | Logging only |

### SavedResponseDict (`services/collection_service.py`)

```python
class SavedResponseDict(TypedDict):
    id: int
    request_id: int
    name: str
    status: str | None
    code: int | None
    headers: list[dict[str, Any]] | None
    body: str | None
    preview_language: str | None
    original_request: dict[str, Any] | None
    created_at: str | None
    body_size: int
```

### ImportService

All methods are `@staticmethod`.  Each parses the input, then persists via
`import_collection_tree()` and `create_environment()`.  Returns an
`ImportSummary` TypedDict with counts and errors.

| Method | Input |
|--------|-------|
| `import_files(paths)` | List of JSON files (auto-detect collection vs environment) |
| `import_folder(path)` | Postman archive folder or directory of JSON files |
| `import_text(text)` | Raw text — auto-detects cURL, JSON, or URL |
| `import_curl(text)` | One or more cURL commands |
| `import_url(url)` | Fetch URL contents and parse |

### HttpService

All methods are `@staticmethod`.  `send_request()` uses `httpx` with event
hooks to capture timing, and inspects the connection for TLS/network data.

| Method | Purpose |
|--------|---------|
| `send_request(method, url, headers, body, timeout)` | Execute HTTP request, return `HttpResponseDict` |

### EnvironmentService

All methods are `@staticmethod`.  Wraps the environment repository and adds
variable substitution via `{{variable}}` syntax.

| Method | Purpose |
|--------|---------|
| `fetch_all()` | All environments as list of dicts |
| `get_environment(id)` | PK lookup |
| `create_environment(name, values?)` | Create with optional initial values |
| `rename_environment(id, new_name)` | Update name |
| `delete_environment(id)` | Delete environment |
| `update_environment_values(id, values)` | Replace key-value pairs |
| `build_variable_map(environment_id)` | Build `{name: value}` dict for substitution |
| `build_combined_variable_map(env_id, request_id)` | Merged collection + environment `{name: value}` map |
| `build_combined_variable_detail_map(env_id, request_id)` | Merged map with `VariableDetail` metadata per key |
| `update_variable_value(source, source_id, key, new_value)` | Update a single variable at its collection/environment source |
| `add_variable(source, source_id, key, value)` | Add (or update) a variable to a collection or environment |
| `substitute(text, variables)` | Replace `{{key}}` placeholders in text |

### RunHistoryService

All methods are `@staticmethod`.  Wraps `run_history_repository` for run
history CRUD.

| Method | Purpose |
|--------|---------|
| `create_run(collection_id, source?)` | Start a new run record |
| `finish_run(run_id, **stats)` | Finalise a run with stats (incl. `skipped`) |
| `add_result(run_id, **fields)` | Add a per-request result |
| `get_runs(collection_id, limit?)` | Runs for a collection as list of dicts |
| `get_results(run_id)` | Results for a run as list of dicts |
| `delete_run(run_id)` | Delete a single run |
| `delete_runs(collection_id)` | Delete all runs for a collection |

### RequestHistoryService (`services/request_history_service.py`)

Module-level functions; class re-exports them as `@staticmethod` aliases.

| Method | Purpose |
|--------|---------|
| `gather_send_identity(ctx, editor, data)` | Capture method/url/name at send start |
| `record_send(identity, response, original_request, settings)` | Persist send; prune per settings; return entry id |
| `list_for_sidebar(search?, executed_from?, executed_to?, limit=500)` | Global list (left-rail global History), newest first; optional local-calendar date bounds |
| `entry_to_http_response_dict(entry)` | Map stored entry → `ResponseViewer.load_stored_response` dict |
| `list_for_request(request_id, search?)` | List sends for one saved request (right rail) |
| `latest_for_request(request_id)` | Newest send metadata for one request (`LIMIT 1`), or `None` |
| `get_entry(entry_id)` | Full row with file payloads |
| `entry_to_detail_snapshot(entry)` | Shape for HistoryPanel read-only detail tabs |
| `build_replay_request_dict(entry)` | Editor load dict from snapshot |
| `build_send_payload_from_entry(entry)` | HTTP replay worker payload |
| `delete_entry(entry_id)` | Remove row and payload files |

TypedDicts: `SendIdentityDict`, `RequestHistoryEntryDict` (includes `was_persisted_request` for `(deleted)` / `(draft)` labels).

Settings: `HistorySettingsManager` (`history/retention_days`, `max_items_per_day`,
`unlimited_per_day`, `save_responses`, `max_response_bytes`).

### AiConfig / AiLlmService (`services/ai/`)

All methods are `@staticmethod`.  No database layer.

| Class / method | Purpose |
|--------------|---------|
| `AiConfig.get_models(*, backfill_tiers=False, persist=True)` | Load models from QSettings `ai/models` (JSON); migrate missing `id`. Default path is a pure read (no `litellm`). `backfill_tiers=True` looks up LiteLLM pricing tiers; `persist=False` skips QSettings write (background worker) |
| `merge_tier_backfill_results(current, backfilled)` | Merge worker backfill into persisted rows by `id` (GUI thread); preserves unrelated fields on `current` |
| `AiConfig.set_models(entries)` | Persist model list |
| `AiConfig.get_default_model_id()` | Legacy default row id or `""` |
| `AiConfig.set_default_model_id(model_id)` | Persist/clear legacy default id |
| `AiConfig.get_chat_model_id()` / `set_chat_model_id(model_id)` | Last AI chat composer model (`ai/chat_model_id`) |
| `AiConfig.get_chat_session_id()` / `set_chat_session_id(session_id)` | Last active AI chat session (`ai/chat_session_id`; **New chat** sets `ai/chat_session_cleared`; set on session activate, load finish, first send, and window close) |
| `AiConfig.is_chat_session_restore_cleared()` | True when **New chat** intentionally blanked restore on next startup |
| `AiConfig.save_all(entries)` | Persist models; clears legacy default id |
| `AiConfig.set_model_reasoning_effort(model_id, effort)` | Persist per-model reasoning effort (clamped to `reasoning_efforts`) |
| `chat_reasoning_effort_for_litellm(entry, effort, *, streaming=True)` | Map UI effort to LiteLLM; returns `None` for Ollama + streaming (avoids broken `think` param) |
| `minimum_reasoning_effort_for(entry)` | Lowest supported reasoning/thinking token for lightweight tasks (title worker) |
| `fill_gpt5_reasoning_gaps(efforts, model_id)` | GPT-5+ only: insert ``low`` between ``none``/``medium``, ``high`` between ``medium``/``xhigh`` |
| `chat_reasoning_summary_for_llm(entry, *, usage_id, streaming)` | Return `"detailed"` for streaming `postmark-chat-*` on non-Ollama reasoning models (OpenAI Responses summaries for Thought UI) |
| `AiLlmService.build_llm(entry, *, stream=False, reasoning_effort=None, run_context_tokens=None, thinking_enabled=None, …)` | Build `openhands.sdk.LLM`; `postmark-chat-*` usage rewrites Ollama models to `ollama_chat/…` (`/api/chat`); passes `reasoning_effort=None` for Ollama chat (overrides OpenHands default `high`); sets `reasoning_summary="detailed"` for OpenAI-style reasoning chat runs; Ollama chat sets `litellm_extra_body` via `ollama_chat_litellm_extra_body` (`num_ctx`, `think`) and `num_retries=0`; Ollama entries set `extra_headers={"Content-Type": "application/json"}` for strict reverse-proxies; resolves Ollama `base_url` |
| `AiLlmService.test(entry)` | Ping completion; returns `(ok, detail)`; never raises |

TypedDict: `AiModelEntry` (`id`, `provider`, `label`, optional
`provider_display_name`, `model`, `base_url`, `api_version`, `auth_kind`,
`auth_ref`, optional `context`, `text`, `insert`, `tools`, `vision`,
`input_cost_per_token`, `output_cost_per_token`). `label` is the per-model name;
`provider_display_name` is the provider group header (auto-allocated via
`allocate_provider_display_name` when empty). Secrets: `auth_ref` → keychain
`ai:<uuid>`. Settings tree pills: `suggest`, `tools`, `vision`. Ollama refresh
reads `insert`/`tools`/`vision` from `/api/show`.

### AiBudgetConfig (`services/ai/ai_budget_config.py`)

Per-provider-connection spend limits (Settings → AI → Budgets). Persisted in QSettings `ai/provider_budgets` as JSON `{"schema": 2, "entries": [...]}`. Soft/hard caps are enforced in the AI assistant via `connection_budget_status()` (`services/ai/chat/budget_status.py`).

| Method | Purpose |
|--------|---------|
| `get_budgets()` | Load all persisted budget rows |
| `budget_for_connection(connection_key)` | One row by `provider_connection_key()` |
| `save_all(entries)` | Merge by `connection_key`; omit empty rows; skip invalid rows |
| `prune_orphaned(models)` | Drop rows whose connection keys are absent from configured models |

TypedDict: `ProviderBudgetEntry` (`connection_key`, `period`, `period_anchor`, `soft_limit_usd`, `hard_limit_usd`). Helper: `validate_budget_entry(entry) -> str | None`.

### Budget period (`services/ai/budget_period.py`)

| Function | Purpose |
|----------|---------|
| `period_window(period, anchor, *, now=None)` | Active `[start, end)` UTC window for a budget period |
| `parse_period_reset(value)` | Parse `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM` reset schedule |
| `parse_period_anchor(value)` | Parse date portion of anchor text |
| `format_period_reset(reset)` / `format_period_reset_label(period, anchor)` | Serialize or label reset schedules |
| `daily_reset_anchor` / `weekly_reset_anchor` / `monthly_reset_anchor` / `yearly_reset_anchor` | Build stored anchors from UI fields |
| `message_in_window(msg, window)` | Whether a message `created_at` falls in the window |

### Spend rollup (`services/ai/chat/spend_rollup.py`)

Cross-session spend for the Budgets page (computed on read from assistant message token columns).

| Function | Purpose |
|----------|---------|
| `global_spend_summary(*, models=None, budgets=None)` | `GlobalSpendSummary` with per-connection period/all-time totals |
| `format_budget_usd_cell(...)` | USD-only budgets table cell |
| `format_budget_tokens_cell(tokens)` | Token-only budgets table cell |
| `format_budget_limits_summary(...)` | Reset schedule + soft/hard limits summary |
| `format_budget_spend_label(...)` | Legacy combined spend cell (`~$0.38 · 278k` or token-only) |
| `format_global_spend_summary_line(...)` | Summary strip line |

TypedDicts: `ConnectionSpendSummary`, `GlobalSpendSummary`. Reuses `ModelSpendRow` from `message_usage`.

### Connection budget status (`services/ai/chat/budget_status.py`)

Chat enforcement and Spend flyout budget card for the active model's provider connection.

| Function | Purpose |
|----------|---------|
| `connection_budget_status(entry, *, spend_summary=None, models=None)` | `ConnectionBudgetStatus` — compare period `known_period_usd` vs soft/hard caps; when no caps are set and `spend_summary` is omitted, skips `global_spend_summary()` (chat chrome fast path) |
| `format_connection_budget_banner_html(status)` | Rich-text composer banner copy |
| `format_connection_budget_card_amounts(status)` | Spend flyout amounts line |
| `connection_budget_card_visible(status)` | Whether Spend tab shows `aiChatBudgetStatusCard` |
| `budget_period_dedupe_key(connection_key, period, anchor)` | Banner dedupe key within one period window |

TypedDict: `ConnectionBudgetStatus` (`state`: `ok` \| `no_limits` \| `unrated` \| `soft_exceeded` \| `hard_exceeded`).

Concurrent per-session `AiChatWorker` + `QThread` pairs for background agent turns.
Advisory threshold: `max_concurrent_chat_runs()` (`services/ai/chat/chat_run_limits.py`,
QSettings `ai/max_concurrent_runs`, default 10). UI shows a warning at/above the
threshold but does not block sends.

### Chat run limits (`services/ai/chat/chat_run_limits.py`)

| Function | Purpose |
|----------|---------|
| `max_concurrent_chat_runs()` | Read clamped advisory threshold from QSettings |
| `set_max_concurrent_chat_runs(value)` | Persist threshold (1–64) |

### Chat run registry (`services/ai/chat/run_registry.py`)

| Symbol | Purpose |
|--------|---------|
| `ChatRunRegistry` | Start/cancel runs; fan-out worker signals with `session_id` + `run_generation` |
| `_WorkerSignalBridge` | Per-run `@Slot` QObject wiring worker→registry (no lambdas on `QueuedConnection`) |
| `ChatRunHandle` | Per-run buffers (`thinking_buffer`, `content_buffer`, `status_text`, `pending_sdk_metrics`) + `bridge` |
| `AiChatRunContext` | `session_id`, `user_message_id`, `user_text`, `run_generation`, `model_id` |
| `running_sessions_changed` | Qt signal when the running set changes (header badge + history `RUNNING_ROLE`) |

| Method | Purpose |
|--------|---------|
| `start_run(...)` | Spawn worker; returns `ChatRunHandle \| None` when duplicate session |
| `run_for(session_id)` | Active handle or `None` |
| `is_running(session_id)` | Whether a worker thread is running for the session |
| `running_session_ids()` | `frozenset[str]` of in-flight session ids |
| `count_running()` | Number of active handles |
| `at_capacity()` | `True` when `count_running() >= max_concurrent_chat_runs()` |
| `cancel(session_id)` | `worker.cancel()` for one session |
| `cancel_all()` | Interrupt all runs (window teardown) |

### AiChatSessionService (`services/ai/chat/session_service.py`)

Hybrid storage: SQLite index (`ai_chat_sessions`, `ai_chat_messages`) +
OpenHands SDK disk state under `session_disk_dir(id)`. Worker thread builds
`Conversation` via `build_conversation` (`delete_on_close=False`, `stream=True`).

| Method | Purpose |
|--------|---------|
| `new_session(entry, mode, *, first_message=None)` | Create UUID session row (lazy SDK conversation) |
| `list_sessions(search=None)` | List non-archived sessions by `updated_at` desc |
| `resolve_restore_session_id()` | Startup restore: persisted id when valid, else most recent if stored id was deleted; `None` when unset (**New chat**) |
| `get_messages(session_id)` | Transcript for repaint |
| `session_spend_breakdown(session_id, *, models=None)` | Per-model USD rollup from assistant-turn token deltas (`message_usage.session_spend_breakdown`) |
| `record_user_message` / `record_assistant_message` | Append SQLite rows + touch preview; user rows accept optional `send_snapshot` (`UserMessageSendSnapshot`) persisted as `send_*` columns |
| `count_messages_after(session_id, after_message_id)` | Count rows after a message (confirm dialog before edit) |
| `send_snapshot_from_message` / `infer_send_snapshot_fallback` | Restore per-send model/mode/agent for inline edit |
| `edit_user_message_and_rewind(session_id, user_message_id, new_content, send_snapshot)` | Update user row, delete later messages, rewind SDK disk prefix, sync session composer settings |
| `delete_message` | Delete one message row and recompute session `last_preview` |
| `build_conversation(session_id, entry, agent_id, *, callbacks, token_callbacks, composer=None, stream=True)` | OpenHands `Conversation` (worker only) |
| `generate_session_title(session_id, entry, *, max_length=50)` | Standalone title LLM from first SQLite user message (`thinking_enabled="off"`, `minimum_reasoning_effort_for`); `usage_id=postmark-chat-title-{session_id}`; no conversation resume |
| `extract_final_parts(conversation)` / `extract_final_text(conversation)` | Current turn's agent message split into thinking + answer (text = answer only) |
| `extract_latest_turn_parts(conversation)` / `extract_richest_parts(conversation)` | Richest thinking + answer from the **current turn** only (reverse-scan to last user ``MessageEvent``; fallback = last agent message) |
| `resolve_assistant_parts(conversation, thinking_buffer, content_buffer)` | Merge current-turn event extraction with per-run stream buffers |
| `message_display_parts(message)` / `chunk_parts_from_stream(chunk)` | Split SDK message or stream chunk into thinking + answer |
| `record_assistant_message(session_id, content, *, thinking="", thinking_duration_seconds=None, model_id=None, usage=None)` | Persist answer + optional thinking, frozen duration, per-turn usage deltas (`model_id`, `prompt_tokens`, `completion_tokens`, `reasoning_tokens`), and touch preview |
| `fork_session_at_message(source_session_id, message_id)` | New session with SQLite prefix through *message_id* + copied SDK disk dir (`base_state.json` id/persistence_dir rewritten); title ``{base} (N)`` via `allocate_fork_session_title` |
| `fork_session_at_user_message(source_session_id, user_message_id)` | New session with prefix **before** the user row (empty + no disk copy when first message); returns ``AiChatUserForkResult`` with ``composer_draft`` = user message text |

TypedDicts: `AiChatSessionDict`, `AiChatMessageDict` (optional `model_id`, `prompt_tokens`, `completion_tokens`, `reasoning_tokens` on assistant rows; optional `send_*` fields on user rows), `UserMessageSendSnapshot`, `AiChatUserForkResult` (`session`, `composer_draft`). Agent/tool registries:
`PostmarkAgentDef`, `DEFAULT_AGENT_ID` (`postmark-assistant`, `postmark_wiki_query` tool, `max_iteration_per_run=5`).

| Tool | Module | Purpose |
|------|--------|---------|
| `postmark_wiki_query` | `services/ai/chat/tools/wiki_query.py` | Read-only user KB lookup (`execute_wiki_query` in `app_wiki/query.py`) |
| `postmark_workspace_query` | `services/ai/chat/tools/workspace_query/` | Read-only workspace explorer: health `insights`, fielded `search` (`query_parse.py`), multi-goal `goals` (max 4), entity scopes, turn-start snapshot |

### ContextUsageService (`services/ai/chat/context_usage.py`, SDK helpers in `context_usage_sdk.py`)

Static helpers that power the composer context ring and breakdown popup.

| Method | Purpose |
|--------|---------|
| `estimate_text_tokens(text, model)` | Tokenize one text payload using LiteLLM `token_counter`, with `len(text) // 4` fallback |
| `count_system_and_tools(agent_id, model)` | Count agent system prompt + serialized tool schema tokens |
| `count_transcript_messages(messages, model)` | Count all SQLite transcript `content` + `thinking` rows |
| `count_summarized_events(session_id, model)` | Read OpenHands `Condensation` summaries from `session_disk_dir(id)/events/` |
| `measure_sdk_view(session_id, entry)` | Build OpenHands SDK `View` from persisted events and count the actual LLM-view tokens |
| `collect_compaction_diagnostics(...)` | Compare SQLite transcript estimates, SDK event/token counts, and condenser thresholds/reasons |
| `build_breakdown(...)` | Assemble the 8 Cursor-style buckets and totals, preferring SDK `View` tokens when SDK events exist and using SQLite as fallback |
| `build_breakdown_for_session(session_id, ...)` | Load the full SQLite session transcript, then call `build_breakdown` |
| `metrics_from_conversation(conv, session_id, *, baseline_accumulated_cost=None)` | SDK cumulative usage + per-turn ``turn_cost_usd`` delta |

`services/ai/chat/compaction.py` also defines:

| Constant | Value | Purpose |
|----------|-------|---------|
| `CHAT_CONDENSER_MAX_EVENTS` | `45` | Proactive event-count threshold for `LLMSummarizingCondenser` |
| `CHAT_CONDENSER_MAX_TOKEN_FRACTION` | `0.72` | Proactive token-budget threshold (72% of effective run context) |
| `CHAT_CONDENSER_MINIMUM_PROGRESS` | `0.05` | Minimum fraction of events that soft condensation must forget |
| `CHAT_CONDENSER_DIAGNOSTIC_USAGE_FRACTION` | `0.70` | Ring usage fraction that triggers `[postmark.ai]` compaction diagnostics |

### message_usage (`services/ai/chat/message_usage.py`)

Per-turn token deltas, assistant footer cost labels, and session spend rollups (computed on read from model rates).

| Function | Purpose |
|----------|---------|
| `turn_usage_delta(sdk, previous_cumulative)` | Per-turn token delta from SDK cumulative metrics |
| `message_turn_cost_usd(entry, prompt_tokens=…, …)` | USD for one turn when rates exist |
| `pricing_model_id_for_assistant_message(msg, *, messages, msg_index, session_model_id)` | Model id used to price one assistant row |
| `entry_for_model_id(model_id, *, extra_entries=None)` | Resolve configured entry; searches `extra_entries` first, then `AiConfig.get_models()` only on miss |
| `assistant_turn_cost_for_message(msg, *, messages, msg_index, …)` | `(pricing_model_id, usd_cost)` for one assistant row |
| `sum_assistant_turn_costs(messages, *, session_model_id=None, models=None)` | Sum priced USD across all assistant rows |
| `format_assistant_footer_label(…)` | Model name + optional turn cost for bubble footer |
| `session_spend_breakdown(messages, *, session_model_id=None, models=None)` | `SessionSpendBreakdown` grouped by model id |
| `format_context_ring_tooltip(used, total, summary)` | Ring hover text with optional session spend |
| `format_spend_tab_label(summary)` | Spend flyout tab (`Spend $0.042` or `Spend`) |
| `format_spend_pill_label(summary)` | Compact USD label (`$0.042` or `$0.04+`) |
| `spend_pill_visible(summary)` | Whether session has known or partial USD |

TypedDicts: `SessionSpendBreakdown`, `ModelSpendRow` (`ProviderSpendRow` alias).

### LocalScriptService (`services/local_script_service.py`)

All methods are `@staticmethod`.  UI must use this module, not `database/`.

| Method | Purpose |
|--------|---------|
| `fetch_all()` | Nested local-scripts tree dict (includes ``module_format`` on script nodes) |
| `fetch_local_script_contents_for_ids(ids)` | ``(id, name, content)`` tuples for bulk search |
| `list_virtual_paths(*, language)` | Virtual paths for ``pm.require("local:…")`` autocomplete |
| `get_script_load_dict(script_id)` | Editor open payload (see ``LocalScriptLoadDict``) |
| `create_script(folder_id, name, *, language, module_format="esm", content)` | Create script |
| `rename_script(script_id, new_name, *, language?, module_format?)` | Rename + ref rewrite |
| `save_script_content(script_id, content, language?, module_format?)` | Persist buffer |

**CJS policy:** ``.cjs`` local scripts are leaf modules — no ``pm.require("local:…")``
inside CJS bodies (enforced in ``local_script_modules.resolve_required``). Consumers
use ``pm.require("local:…/file.cjs")`` from ESM pre-request/test scripts only.

**UI signals (local scripts tree):** ``new_script_clicked(str, str)`` (language,
module_format); ``new_script_requested(object, str, str)`` on header; ``script_rename_requested(int, str, str, str)`` on ``CollectionTree`` and ``CollectionWidget``.

### SnippetService (`services/snippet_service.py`)

All methods are `@staticmethod`.  UI must use this module, not `snippet_repository`.

| Method | Purpose |
|--------|---------|
| `list_all(language)` | All user snippets for an editor language |
| `list(language, context)` | Filtered by pre/test/both context |
| `get(snippet_id)` | One user snippet row (``UserSnippetDict``) or ``None`` |
| `create(...)` / `update(...)` / `delete(...)` | User snippet CRUD |

### GraphQLSchemaService

All methods are `@staticmethod`.

| Method | Purpose |
|--------|---------|
| `fetch_schema(url, headers)` | Introspect endpoint, return `SchemaResultDict` |
| `_parse_schema(schema_data)` | Convert raw introspection JSON to structured types |
| `format_schema_summary(result)` | Human-readable schema summary text |

### SnippetGenerator

Located in `services/http/snippet_generator/` sub-package (re-exported via
`services/http/__init__.py`).  All methods are `@staticmethod`.

| Method | Purpose |
|--------|---------|
| `available_languages()` | List of 23 supported language display names |
| `get_language_info(name)` | Return `LanguageEntry` for a display name, or `None` |
| `generate(language, method, url, headers, body, auth, options)` | Dispatch to language-specific generator |

**`LanguageEntry`** (`NamedTuple`): `display_name`, `lexer`, `applicable_options`, `generate_fn`.

**Supported languages (23):** cURL, HTTP, PowerShell (RestMethod),
Shell (HTTPie), Shell (wget), Python (requests), Python (http.client),
JavaScript (fetch), JavaScript (XHR), NodeJS (Axios), NodeJS (Native),
Ruby (Net::HTTP), PHP (cURL), PHP (Guzzle), Dart (http), C (libcurl),
C# (HttpClient), C# (RestSharp), Go (net/http), Java (OkHttp),
Kotlin (OkHttp), Rust (reqwest), Swift (URLSession).

### Shared HTTP utilities (`services/http/header_utils.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `parse_header_dict(raw)` | `dict[str, str]` | Parse `Key: Value\n` lines into a dict |

### Auth handler (`services/http/auth_handler.py`)

Shared auth header injection used by both `http_worker.py` (actual send)
and `snippet_generator/generator.py` (code snippets).

| Function | Returns | Purpose |
|----------|---------|---------|
| `apply_auth(auth, url, headers, *, method, body)` | `(url, headers)` | Dispatch to type-specific handler |

Supports 12 field-based auth types: bearer, basic, apikey, oauth2, digest,
oauth1, hawk, awsv4, jwt, asap, ntlm, edgegrid.  HMAC-based JWT (HS256/384/512)
uses stdlib; RSA/EC algorithms require optional `PyJWT`.  NTLM is pass-through
(requires live challenge-response).

### OAuth2Service (`services/http/oauth2_service.py`)

OAuth 2.0 token exchange for all four grant types.

| Method | Returns | Purpose |
|--------|---------|---------|
| `get_token(config)` | `OAuth2TokenResult` | Dispatch to grant-type handler |
| `refresh_token(token_url, refresh_token, client_id, client_secret, client_auth)` | `OAuth2TokenResult` | Refresh an expired token |

Grant types: Authorization Code (browser + redirect), Implicit (browser +
fragment capture), Password Credentials (direct POST), Client Credentials
(direct POST).  Browser-based flows open the system browser and start a
local HTTP server to capture the callback.

### ScriptService

All methods are `@staticmethod`.  Resolves inherited script chains
by walking the collection ancestor tree.

| Method | Returns | Purpose |
|--------|---------|---------|
| `build_script_chain(request_id)` | `tuple[list[ScriptEntry], list[ScriptEntry]]` | Collect pre-request and test scripts from ancestors + self |

### ScriptEngine

All methods are `@staticmethod`.  Orchestrates script execution across
`DenoRuntime` / `JSRuntime` (Deno ``deno run`` subprocess) and `PyRuntime` (RestrictedPython subprocess).

| Method | Returns | Purpose |
|--------|---------|---------|
| `run_pre_request_scripts(chain, context)` | `ScriptOutput` | Run pre-request chain, merge outputs |
| `run_test_scripts(chain, context)` | `ScriptOutput` | Run test chain, merge outputs |
| `run_single(script, language, context)` | `ScriptOutput` | Run one script in specified runtime |

Module-level helper in `services/scripting/engine.py` (used by the script
editor gutter; not a `ScriptEngine` method):

| Function | Returns | Purpose |
|----------|---------|---------|
| `find_pm_tests(source, language)` | `list[dict[str, Any]]` | `{"name", "line"}` (1-based) for each `pm.test` (Python AST, JS esprima + regex fallback) |
| `find_top_level_statement_lines(source, language)` | `set[int]` | 0-based lines of top-level statements (step-debugger checkpoints); empty set means do not style breakpoints as unreachable |

`ScriptLinter` exposes `_esprima_parse_result` for the shared esprima JSON
parse (linting + `find_pm_tests` and `find_top_level_statement_lines`).

**Response assertions (Postman-compat):** In `data/scripts/pm_bootstrap.js`,
`pm.response.to` is a getter that returns a new `__Expectation` wrapping the
response (so `pm.response.to.have.status(200)` works).  **`pm.require`** in JS
loads `npm:` / `jsr:` packages only when the specifier is a **string literal**
in the user script: `js_runtime._detect_pm_require_specs` validates the name and
exact semver, `js_runtime._pm_require_imports_block` emits static ESM `import`s
and registers `globalThis.__pm_require_modules` (see `deno_runtime.deno_ipc_argv_and_env`
for cache + optional `--allow-net`).  In
`services/scripting/_py_sandbox.py`, `_PmResponse.to` returns `_Expectation(self)`;
`jsonBody` is aliased to `json_body` on the Python side.

**Python (Pyodide):** When `data/scripts/vendor_pyodide/pyodide.asm.wasm` exists and
Deno is available, `PyRuntime.execute` uses `pyodide_runtime.PyodideRuntime` →
`data/scripts/pyodide_run.mjs` (`loadPyodide` from `./vendor_pyodide/pyodide.mjs`,
`micropip` for `py_runtime.detect_pm_require_py_specs` literals, then
`data/scripts/pm_bootstrap.py` — hand-maintained Pyodide bootstrap (mirrors
`_py_sandbox.py` / `pm_bootstrap.js`; do **not** run deprecated
`scripts/gen_pm_bootstrap_pyodide.py`), with
`postmark_ipc.send_request_sync`, `pm.require`, safe builtins including `print` → `_console_emit`,
and `collect_pm_output`.  Otherwise execution
stays on `_py_sandbox.py` + RestrictedPython (`PyRuntime.execute_restricted`).

Context builders and utilities in `services/scripting/context.py`:

| Function | Purpose |
|----------|---------|
| `build_pre_request_context(...)` | Build `ScriptInput` for pre-request scripts |
| `build_test_context(...)` | Build `ScriptInput` for test/post-response scripts |
| `normalize_events(events)` | Convert Postman-style event list to `{pre_request, test}` dict |
| `execute_sub_request(spec)` | HTTP bridge for `pm.sendRequest()` (scheme whitelist, rate-limited) |
| `load_globals()` | Load persisted global variables from `data/globals.json` |
| `save_globals(changes)` | Merge changes into persisted globals file |

## TypedDict schemas

### SnippetOptions (`services/http/snippet_generator/generator.py`)

```python
class SnippetOptions(TypedDict, total=False):
    indent_count: int              # default 2
    indent_type: str               # "space" or "tab", default "space"
    trim_body: bool                # default False
    follow_redirect: bool          # default True
    request_timeout: int           # seconds, 0 = no timeout
    include_boilerplate: bool      # default True — imports/main wrappers
    async_await: bool              # default False — async/await vs promise chains
    es6_features: bool             # default False — ES6 import/arrow syntax
    multiline: bool                # default True — split shell commands across lines
    long_form: bool                # default True — --header vs -H
    line_continuation: str         # default "\\" — continuation char (\, ^, `)
    quote_type: str                # default "single" — URL quoting style
    follow_original_method: bool   # default False — keep method on redirect
    silent_mode: bool              # default False — suppress progress meter
```

### HttpService TypedDicts (`services/http/http_service.py`)

```python
class TimingDict(TypedDict):
    dns_ms: float
    tcp_ms: float
    tls_ms: float
    ttfb_ms: float
    download_ms: float
    process_ms: float

class NetworkDict(TypedDict):
    http_version: str
    remote_address: str
    local_address: str
    tls_protocol: str | None
    cipher_name: str | None
    certificate_cn: str | None
    issuer_cn: str | None
    valid_until: str | None

class HttpResponseDict(TypedDict):
    elapsed_ms: float                          # always present
    status_code: NotRequired[int]
    status_text: NotRequired[str]
    headers: NotRequired[list[dict[str, str]]]
    body: NotRequired[str]
    size_bytes: NotRequired[int]
    error: NotRequired[str]
    timing: NotRequired[TimingDict]
    request_headers_size: NotRequired[int]
    request_body_size: NotRequired[int]
    response_headers_size: NotRequired[int]
    response_uncompressed_size: NotRequired[int]
    network: NotRequired[NetworkDict]
```

### OAuth2TokenResult (`services/http/oauth2_service.py`)

```python
class OAuth2TokenResult(TypedDict):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: str
    error: str
```

### CollectionService TypedDicts (`services/collection_service.py`)

```python
class RequestLoadDict(TypedDict, total=False):
    name: str
    method: str
    url: str
    body: str | None
    request_parameters: str | list[dict[str, Any]] | None
    headers: str | list[dict[str, Any]] | None
    description: str | None
    scripts: dict[str, str] | None
    body_mode: str | None
    body_options: dict[str, Any] | None
    auth: dict[str, Any] | None
```

### LocalScriptService TypedDicts (`services/local_script_service.py`)

```python
class LocalScriptLoadDict(TypedDict, total=False):
    id: int
    name: str
    language: str
    module_format: str  # "esm" | "commonjs"
    content: str
```

### EnvironmentService TypedDicts (`services/environment_service.py`)

```python
class VariableDetail(TypedDict, total=False):
    value: str           # resolved value
    source: str          # "collection", "environment", or "local"
    source_id: int       # collection_id or environment_id (0 for local)
    is_local: bool       # True when value is a per-request override

class LocalOverride(TypedDict):
    value: str                # overridden value
    original_source: str      # "collection" or "environment"
    original_source_id: int   # PK of the original source
```

### AI chat context TypedDicts (`services/ai/chat/context_usage.py`)

```python
class ContextUsageCategory(TypedDict):
    id: str
    label: str
    tokens: int

class ContextUsageBreakdown(TypedDict):
    used_tokens: int
    total_tokens: int
    categories: list[ContextUsageCategory]
    has_summarized: bool
    is_estimated: bool
    sqlite_message_count: NotRequired[int]
    sqlite_transcript_tokens: NotRequired[int]
    sdk_event_count: NotRequired[int]
    sdk_view_tokens: NotRequired[int]
    transcript_larger_than_sdk: NotRequired[bool]
    used_sqlite_fallback: NotRequired[bool]
    condenser_max_size: NotRequired[int]
    condenser_max_tokens: NotRequired[int | None]
    condenser_minimum_progress: NotRequired[float]
    condensation_reasons: NotRequired[list[str]]

class ContextUsageSdkMetrics(TypedDict, total=False):
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    per_turn_token: int
```

### GraphQLSchemaService TypedDicts (`services/http/graphql_schema_service.py`)

```python
class SchemaTypeDict(TypedDict):
    name: str
    kind: str
    description: str

class SchemaResultDict(TypedDict):
    query_type: str
    mutation_type: str
    subscription_type: str
    types: list[SchemaTypeDict]
    raw: dict
```

### Import parser TypedDicts (`services/import_parser/models.py`)

```python
class ParsedSavedResponse(TypedDict): ...
class ParsedFolder(TypedDict): ...
class ParsedCollection(TypedDict): ...
class ParsedEnvironment(TypedDict): ...
class ImportResult(TypedDict): ...
class ImportSummary(TypedDict): ...
```

See `services/import_parser/models.py` for full field definitions.

### Scripting TypedDicts (`services/scripting/__init__.py`)

```python
class ScriptInput(TypedDict):
    request: dict[str, Any]       # method, url, headers, body
    response: dict[str, Any]      # status, headers, body, elapsed_ms (test only)
    variables: dict[str, str]     # combined environment + collection vars
    environment_vars: dict[str, str]  # environment-scoped variables
    collection_vars: dict[str, str]   # collection-scoped variables
    global_vars: NotRequired[dict[str, str]]  # persisted global variables
    info: dict[str, Any]          # request name, iteration index
    iteration_data: NotRequired[dict[str, Any]]  # data-driven row (runner only)

class ScriptOutput(TypedDict):
    test_results: list[TestResult]          # pm.test() assertion results
    console_logs: list[ConsoleLog]          # console.log/warn/error output
    variable_changes: dict[str, str]        # pm.variables/environment/collection changes
    global_variable_changes: NotRequired[dict[str, str]]  # pm.globals changes
    request_mutations: dict[str, Any] | None  # pm.request.* mutations
    next_request: NotRequired[str | None]   # pm.execution.setNextRequest()
    skip_request: NotRequired[bool]         # pm.execution.skipRequest()

class ScriptEntry(TypedDict):
    code: str                     # script source code
    language: str                 # "javascript", "typescript", or "python"
    source_name: str              # display label (e.g. "Collection > Test")

class TestResult(TypedDict):
    name: str                     # test description
    passed: bool                  # assertion outcome
    error: str | None             # failure message
    duration_ms: float            # execution time

class ConsoleLog(TypedDict):
    level: str                    # "log", "warn", "error", "info"
    message: str                  # formatted message
    timestamp: float              # time.time() value
    source_line: NotRequired[int | None]  # 0-based editor line (best-effort)
```

### Theme TypedDict (`ui/styling/theme.py`)

```python
class ThemePalette(TypedDict): ...
```

See `ui/styling/theme.py` for full field definitions.

## Response viewer and popup system

`ResponseViewerWidget` displays the HTTP response with five tabs:
Body, Headers, Cookies, Test Results (hidden), and Pre-request (hidden).

### Body tab

- **Format toolbar** — Pretty/Raw/Preview combo, Beautify button
- **`CodeEditorWidget`** — `QPlainTextEdit` subclass (read-only) with
  Pygments syntax highlighting, line numbers, fold gutter, word wrap,
  and search (Ctrl+F)

### Status bar (below tabs)

Four clickable labels show response metadata.  Each opens an `InfoPopup`
subclass:

| Label | Popup | Data source |
|-------|-------|-------------|
| Status code + text | `StatusPopup` | `status_code`, `status_text` |
| Response time | `TimingPopup` | `TimingDict` |
| Response size | `SizePopup` | `size_*` fields + `TimingDict` |
| Network info | `NetworkPopup` | `NetworkDict` |
