# Architecture and data flow

This file documents how data moves between layers, how signals are wired,
and what implicit contracts exist.

## Quick rules — read these first

1. **UI must never import from `database/`.**  Go through the service layer.
2. **Call `init_db()` before creating `MainWindow`** — the constructor
   immediately starts a background DB query.
3. **Call `configure_before_qapplication()` before the first `QApplication()`**
   — see `qt_app_init.py` (used from `main.py` and `tests/conftest.py`) for
   Hi-DPI scale-factor rounding on fractional displays.
4. **Create `ThemeManager(app)` before creating `MainWindow`** — it applies
   the global stylesheet, QPalette, and widget style on construction.
   Import from `ui.styling.theme_manager`.
5. **Every repository function is its own transaction.** You cannot batch
   multiple calls into one commit.
6. **Always wrap programmatic tree-item edits in `blockSignals(True/False)`**
   — see [ui/AGENTS.md](ui/AGENTS.md).
7. **The data interchange format is a nested `dict[str, Any]`**, not ORM
   objects.  See the schema below.
8. **`_safe_svc_call` swallows all exceptions.**  Errors are logged but never
   shown to the user.
9. **`CollectionService` methods are all `@staticmethod`.**  Do not add
   instance state.
10. **Never call `setStyleSheet()` for static widget styling** — use
   `setObjectName()` and global QSS.  See [ui/AGENTS.md](ui/AGENTS.md).
11. **Never use `# type: ignore` to assign `None` to a non-optional
    attribute.**  This silences mypy but Pylance still widens the inferred
    type to `X | None`, propagating false errors everywhere the attribute
    is read.  If a field truly needs to become `None`, declare it as
    `X | None` from the start and add proper guards at usage sites.
    If you only need to drop the reference for GC, `del` the owning
    object instead.
12. **OpenHands AI tools: one user-facing job → one dedicated `postmark_*`
    tool.**  Do not bury new capabilities in mutate/execute and “fix”
    discovery with system-prompt / wiki hacks. Load the
    [`openhands-tools`](../.agents/skills/openhands-tools/SKILL.md) skill.

## Layering recap

```
UI widgets  ──signals──►  CollectionWidget  ──calls──►  CollectionService
                                                             │
                                                      (static methods)
                                                             │
                                                      Repository functions
                                                             │
                                                     get_session() context mgr
                                                             │
                                                         SQLite file

ThemeManager  ──QPalette + global QSS──►  QApplication
              ──theme_changed signal──►   widgets (refresh dynamic styles)
              ──QSettings──►              persistent user preferences

TabSettingsManager  ──QSettings──►        persistent request-tab preferences
                    ──settings_changed──► MainWindow / RequestTabBar

RequestEditorWidget  ──send_requested──►  MainWindow
  MainWindow → HttpSendWorker (QThread) → run_shared_send() (services/ai/chat/execution/)
    → HttpService.send_request() → HttpSendWorker.finished(HttpResponseDict)
    → ResponseViewerWidget.load_response()
  (Debug Send keeps step-through in HttpSendWorker only; agent execute never uses debug.)

RequestEditorWidget / FolderEditorWidget  ──open_scripting_settings_requested──►  MainWindow
  → ``SettingsDialog`` (``initial_category="Scripting"``)

RequestEditorWidget  ──_on_fetch_schema──►  SchemaFetchWorker (QThread)
  → GraphQLSchemaService.fetch_schema() → SchemaFetchWorker.finished()
```

- **DO NOT** import from `database/` in any UI file.  The service layer is
  the only bridge between UI and repository.
- `ThemeManager` (`ui.styling.theme_manager`) is created once in `main.py`
  and passed to `MainWindow`.  It owns the app-wide stylesheet, QPalette,
  and QSettings persistence for theme preferences.  See
  [ui/AGENTS.md](ui/AGENTS.md) for widget styling rules.
- `TabSettingsManager` (`ui.styling.tab_settings_manager`) is created once
  in `main.py` and passed to `MainWindow`.  It persists request-tab
  behaviour (preview enablement, compact labels, duplicate-name path
  disambiguation, wrap mode, tab limit, and close-activation policy)
  via QSettings.  It also stores the open-tab session (tab list + active
  index) for restore-on-launch via `save_open_tabs()` /
  `load_open_tabs()` / `clear_open_tabs()`.  Session data is a JSON
  string under QSettings key `tabs/session`.
- `CollectionService` is instantiated as `self._svc = CollectionService()` in
  `CollectionWidget.__init__`, but **every method is `@staticmethod`**.
  Do not add instance state without updating every call site.
- `EnvironmentService`, `HttpService`, `GraphQLSchemaService`, and
  `SnippetGenerator` follow the same `@staticmethod` pattern.
- **`services/ai`** — `AiConfig` persists configured LLM models in QSettings
  (`ai/models` JSON list; `ai/chat_model_id` for composer selection;
  `ai/chat_session_id` for last active chat session (written on first send,
  session activate, load finish, and window close; **New chat** sets
  `ai/chat_session_cleared`; when no id was ever saved, startup falls back to
  the latest session); legacy
  `ai/default_model` cleared on save). `AiModelEntry` TypedDict
  holds per-row metadata (`label` = model name, `provider_display_name` =
  provider group header, `enabled` default false, `context`, `text`, `insert`,
  `tools`, `vision`, optional costs, `context_tiers`, `tiers_checked`). Default
  `get_models()` is a pure QSettings read (no `litellm` import). One-time tier
  backfill runs in delayed `AiModelBackfillWorker` after `load_finished`;
  results are merged and persisted on the GUI thread in
  `MainWindow._on_ai_models_backfilled`.
  Settings Models tree has an **Enabled**
  checkbox column and capability pills `suggest` / `tools` / `vision`.
  Empty provider display names auto-allocate unique catalog names on save.
  Ollama refresh derives `insert`/`tools`/`vision` from `/api/show`; optional
  `default_context` (provider dialog, 4k–1M, default 32k) fills context when the
  API omits it. API keys
  use `auth_ref`
  pointing at
  `ai:<uuid>` in `secret_store` (never in QSettings); AI callers resolve
  tokens through `secret_store.get_secret()` so keyring misses still fall back
  to legacy encrypted-file storage. `sdk_env.ensure_openhands_env`
  runs at startup (`qt_app_init`) and before SDK import — suppresses OpenHands
  banner/Rich logging and SQLAlchemy INFO noise. `AiLlmService` builds
  and tests `openhands.sdk.LLM` instances (lazy SDK import); streaming
  `postmark-chat-*` runs set `reasoning_summary="detailed"` on non-Ollama
  reasoning models so OpenAI Responses summaries populate the Thought block.
  **Multi-session AI chat:** `AiChatSessionService` (`services/ai/chat/`)
  indexes sessions/messages in SQLite (`get_session_tail` / `load_older_messages` /
  `load_newer_messages` for virtualized transcript paging;
  `get_session_with_messages` for one-shot full reads) and builds OpenHands `Conversation`
  on worker threads (`AiChatWorker`).   **Concurrent runs:** `ChatRunRegistry`
  (`services/ai/chat/run_registry.py`) owns one `AiChatWorker` + `QThread` per
  session id (advisory threshold `max_concurrent_chat_runs()` from
  `services/ai/chat/chat_run_limits.py`, QSettings `ai/max_concurrent_runs`,
  default 10; soft warning only — sends are not blocked). Per-run
  `_WorkerSignalBridge` (`@Slot` QObject) connects worker signals to the registry
  on the GUI thread — **never use Python lambdas** for cross-thread
  `QueuedConnection` (defers delivery until `worker.run()` returns and breaks
  streaming). Bridge includes `subagent_updated` for delegation lifecycle,
  `tool_activity_updated` for main-agent tool rows (query/datetime/import/mutate/execute;
  excludes wiki/delegate). Observation ingest rewrites card ``detail`` from the
  tool result for ``postmark_collection_draft`` (and other ``ok: false`` writes) so
  soft-trims / skips / failures are visible on the row; the full observation
  body is stored on ``ToolActivityRecord.output`` for expandable tool cards.
  Assistant activity is append-only and chronological:
  approval chrome immediately finalizes the active thought, approved tools replace it
  with an explicit running card, later reasoning opens a fresh thought block, and each
  subsequent tool cycle gets a new card group below that reasoning. The tracker accepts
  the SDK-emitted `postmark_workspace_import` alias as well as the registered
  `postmark_import` name, and uses the `ActionEvent.security_risk` actually chosen by the
  SDK to distinguish approval pauses from immediately executing LOW-risk actions.
  When a card becomes terminal, the shared `AssistantActivityRow` moves immediately
  below it and shows **Thinking…** until the next reasoning or answer chunk, avoiding
  a blank post-tool gap. Thinking persistence supports any number of separator-packed
  phases. Plus
  `confirmation_needed` / `confirmation_cleared` / `mutation_bridge_ready` for
  Agent workspace Approve chrome and GUI bridge drain. Worker stubs
  `approve_confirmation()` / `reject_confirmation(reason)` are invoked from the
  panel via `ChatRunRegistry` (`QMetaObject.invokeMethod`, QueuedConnection).
  Pending-action payloads for inline Approve cards come from
  `confirmation_payload.pending_actions_payload` (kinds via
  `mutation.auto_approve.kind_from_action_event`; display fields `title` /
  `detail` / `url` / `risk` from Action `human_preview` / `preview_url`).
  When OpenHands stops with `MaxIterationsReached`, the worker parks on the same
  chrome via `continue_iterations_payload` (Continue / Stop); Continue runs
  another `arun()` (fresh iteration budget), Stop finishes with a short note
  instead of ``No response from model``. Other ERROR codes still fail normally.
  Execute rows include
  `resolve_execute_preview_url` (`execution/preview_url.py`): env-substituted
  when possible, then redacted for Approve chrome.
  Successful executes enqueue bridge ``executed`` events; the GUI shows
  clickable ``ExecuteResultCard`` rows (``execute_events.py`` +
  ``message_bubble/execute/``). Pending confirms show as
  ``PendingToolCard`` rows (``message_bubble/confirm/``) on the streaming
  assistant bubble — not a composer banner. Click → ``postmark://history/<id>?focus=response``
  opens the request tab with ``load_stored_response`` in the centre viewer
  (left-rail history open without ``focus=response`` still only focuses the
  History flyout).
  `_AiChatRunsMixin` (`ui/main_window/ai_chat_runs.py`) routes worker signals by
  `session_id` + `run_generation`; only the visible session streams into
  `AiChatPanel`; background sessions buffer chunks plus ordered
  `RunActivityEntry` interrupt boundaries / `thinking_phases` on `ChatRunHandle`
  so reattachment preserves thought → tool/subagent → thought chronology, then
  persist on finish. `_drain_mutation_bridge()` delegates to
  `ui/main_window/mutation_drain/drain_mutation_bridge()` on
  finish / confirmation clear / `mutation_bridge_ready` (open_target →
  `_on_workspace_target_requested`, mutated → collection/local tree refresh +
  reload open editors, env/globals/snippets/saved_responses refresh, delete →
  close matching tabs; executed → `load_stored_response` for sends,
  run_scripts/run_local_script → Scripts/Output panels + execute cards).
  Settings → AI → Agents: auto-approve list
  (`services/ai/chat/mutation/auto_approve.py`) — Agent mode always has
  mutate/execute; writes pause for Approve unless whitelisted. Switching sessions or **New chat** does not cancel in-flight workers.
  `running_sessions_changed` refreshes `aiChatActiveRunsBadge` and session-history
  `RUNNING_ROLE`. SDK state persists under
  `session_disk_dir(id)`; searchable metadata in `ai_chat_sessions` /
  `ai_chat_messages`. Context accounting lives in
  `services/ai/chat/context_usage.py` (`ContextUsageService`,
  `ContextUsageBreakdown`, `ContextUsageSdkMetrics`) and uses the persisted
  OpenHands SDK `View` token count as the ring/popup source of truth when SDK
  events exist (`services/ai/chat/context_usage_sdk.py` — `measure_sdk_view`,
  `collect_compaction_diagnostics`, `SdkViewSnapshot`). SQLite full-transcript
  token estimates remain the fallback before SDK context is available or when
  SDK token counting fails. **Subagents** category tokens come from completed
  child conversations under ``session_subagents_root`` (final answer, else task
  prompt) via ``count_session_subagent_context_tokens``; that slice is excluded
  from Conversation to avoid double-counting tool observations. Context refreshes
  when subagent records reach ``completed``/``error`` and when the subagent poll
  timer stops. **Composer typing** must not call full
  `build_breakdown` / `measure_sdk_view` (GIL-heavy LiteLLM + SDK event walk);
  `AiChatPanel._on_composer_draft_changed` adjusts the cached breakdown's
  `draft_tokens` / conversation bucket with a char-only estimate. Full refreshes
  run on session load, model change, and run finish via `ContextUsageLoader`
  (SQLite `get_messages` stays on the worker thread). `AiChatPanel` must **not**
  shut down the
  context-usage `QThread` in `hideEvent` (panel starts hidden; hide/show races
  abort Qt) — shutdown runs from `closeEvent` /
  `MainWindow._cleanup_ai_chat_threads`. Refresh is skipped while the panel is
  not visible and re-armed on `showEvent`. After a run,
  `AiChatWorker.usage_updated` delivers SDK `conversation_stats` metrics to the
  panel (stashed as per-turn usage for `record_assistant_message` and the context
  ring); high-usage runs also log compaction diagnostics comparing SQLite rows,
  SDK events/tokens, condenser thresholds, and condensation reasons. OpenHands
  compaction tuning lives in `services/ai/chat/compaction.py`;
  `build_conversation()` attaches `LLMSummarizingCondenser` with
  `CHAT_CONDENSER_MAX_EVENTS = 45`, `CHAT_CONDENSER_MAX_TOKEN_FRACTION = 0.72`,
  `CHAT_CONDENSER_MINIMUM_PROGRESS = 0.05`, and `max_iteration_per_run >= 3`
  so summarize-then-reply completes in one send. Per-user-message send settings
  (`UserMessageSendSnapshot`, nullable `send_*` columns on `ai_chat_messages`)
  are persisted on `record_user_message` and restored for inline edit via
  `send_snapshot_from_message` / `infer_send_snapshot_fallback`.
  `edit_user_message_and_rewind` updates the user row, deletes later messages,
  and rewinds SDK disk state before the controller resubmits on the same bubble.
  User bubbles never show the composed `Attached files:` trailer as prose:
  `UserMessageSection` lifts it out with
  `composer/attachments.split_prompt_attachments` and renders it as
  `user_message/attachments/UserMessageAttachmentRow` chips (icon + name + size)
  above the prompt; `text()` still returns the full prompt so edit/fork
  round-trips the trailer. Inline edit does the same lift:
  `AiChatComposer.restore_text` splits the trailer into removable
  `aiChatAttachmentChip` rows (`_prompt_attachments`) and puts only the
  body in the input; `composed_prompt()` rewrites the trailer on submit.
  Compact docked composers still hide the chip row, but compact + edit mode
  keeps it visible. Chip sizes arrive via the bubble's
  `attachment_sizes` — from source paths on send
  (`attachment_sizes_from_sources`) and from the session store on restore
  (`attachment_sizes_from_session`). A left-click on a chip emits
  `attachment_clicked(reference)` up `_AttachmentChip → UserMessageAttachmentRow
  → UserMessageSection → ChatMessageBubble`; the panel's `_on_attachment_clicked`
  resolves the session attachment (`attachments.store.resolve_attachment`) and
  opens `user_message/attachments/AttachmentMarkdownDialog` with its stored
  Markdown (`read_markdown`).
  Postmark agent/tool registries
  (`agent_registry.py`, `tool_registry.py`, `tools/wiki_query.py`,
  `tools/datetime_query/`, `tools/workspace_query/`, `tools/delegate_tool.py`,
  `subagent_registry.py`) ship
  `DEFAULT_AGENT_ID` with `postmark_wiki_query`, `postmark_workspace_query`,
  `postmark_datetime` (current date/time + free-text timezone / Unix-epoch convert),
  `postmark_workspace_mutate` / `postmark_workspace_execute` / `postmark_import`
  (always registered; `tools_for_turn` exposes them in Agent mode only — Ask/Plan
  stay read-only; write safety is Approve / auto-approve;
  `max_iterations_for_turn` raises Agent runs to `MUTATING_MAX_ITERATIONS` (50)
  so multi-chunk document→collection builds do not die mid-import),
  OpenHands `task_tool_set` (sequential/resumable subagents), and `delegate`
  (parallel fan-out).
  Built-in subagent types: `wiki-researcher` (`postmark_wiki_query` only),
  `workspace-researcher` (`postmark_workspace_query` only), and
  `general-purpose` (no tools). Optional file agents from
  `.agents/agents/*.md` via `register_file_agents(project_root())`.
  **`postmark_datetime`** (`tools/datetime_query/`) answers wall-clock
  questions with `operation=now` (local date/time/full + UTC + Unix seconds) or
  `operation=convert` (flexible `when` / `from_tz` / `to_tz`, including Unix
  epoch seconds/ms; omitted `from_tz` → OS local except epoch→UTC; ambiguous
  labels like `australia` → documented default with an assumption note;
  convert observations include past/future relative to now). Stdlib `zoneinfo`
  only.
  **`postmark_import`** (`tools/workspace_import/`) is the dedicated OpenHands
  tool for OpenAPI/Swagger, WSDL, Postman, cURL, URL, or file import — Action
  fields `url`|`path`|`text`|`curl` (exactly one) plus optional
  `collection_name_suffix` (renames imported roots in the same call); executor
  calls `apply_workspace_import` → `ImportService`. `turn_guard.py`, cleared by
  `AiChatWorker.set_run`, returns the first successful result instead of importing
  an identical source twice in one user turn. Observations expose ready-to-copy
  named `collection_links`, not a separate raw deep-link list. Approve kind
  `mutate:create:import`. Import is **not** a mutate entity.
  **`postmark_document_import`** (`tools/document_import/`) is a read-only
  OpenHands tool that reads **one chunk** of an uploaded document: Action `uri`
  (`postmark://uploaded/<name>.md`, used only to choose among multiple uploads)
  plus `chunk` (1-based). A single upload resolves even if a small model supplies
  a damaged URI, because there is no ambiguity. Tool-activity cards label the row
  with the original upload name (`Guide.docx`), not ``attached document``: send-time
  `set_turn_attachments(..., names=…)` feeds `human_preview`, and the observation's
  `document:` line rewrites the detail to `Name (chunk X of Y)`. Every observation ends with
  `chunk X of Y` and a `next_step` line telling the agent to batch endpoints once
  their method, path, and request example/parameters have been read; response
  docs may continue into a later chunk, while TOC-only names never count. A whole
  spec does not
  fit in context, and letting the model pick page ranges made coverage depend on
  its judgement, so the document is divided once by `attachments/chunks.py` and
  reading to the end is a matter of counting. `path` is accepted only for a file
  the user named but did not attach; it is uploaded on demand and then chunked
  the same way. DOCX images are walked in body order including table cells and
  nested tables, then reconciled against `word/media/*` so header/footer/text-box
  images still appear (flagged as unpositioned). The stored Markdown holds only an
  `[image N]` marker per screenshot; the PNG goes to
  `<markdown-stem>/images/image-N.png`. **The `vision` flag on the model entry is
  the only switch** (published per session by `AiChatWorker.set_run`, read by
  `attachments/screenshots.py`): a vision model gets the chunk's screenshots as SDK
  `ImageContent`, capped at `MAX_CHUNK_IMAGES`; anything else gets text recognised
  from them placed under each marker. OCR is the **fallback only** — it never runs
  for a vision model, which reads the screenshot far better than OCR does. It is
  therefore done lazily at read time, for the chunk's images only, and cached in
  `images/ocr.json`; upload does no OCR at all (`rapidocr` + `onnxruntime`,
  optional Poetry extra `ocr` — install with `poetry install --extras ocr`;
  without it a non-vision model gets the bare marker). Images are collected
  through `ocr.ImageCollector`, which drops repeats by SHA-256 of the normalized
  PNG and images under `MIN_IMAGE_PIXELS`, warning in both cases so nothing
  disappears silently.

  **`postmark_collection_draft`** (`tools/collection_draft/`) builds a collection
  incrementally with a deliberately narrow model-facing schema: `start`,
  `add_requests` (one soft-accept batch of at most 20 endpoints), `status`, `finish`,
  `discard`.   There are no legacy single-request/folder operations or top-level
  method/URL/body fields for the model to choose accidentally. The Action and its
  nested `DraftRequestInput` set `extra="ignore"` and keep every field optional:
  models emit `path` for `url`, a header object instead of rows, and stray fields
  like `target_id`, so a `model_validator` folds `path`→`url` and header/param
  objects into `key`/`value`(/`description`) rows while real validation
  (name/method/url) happens in `ops/` — soft-caps truncate/trim with `warnings:`,
  bad items are listed in `skipped:`, empty `requests: []` (or omitted) is a soft
  no-op for TOC/prose chunks, and `ok: false` is reserved for structural failures
  (`no_draft`, every item skipped, auth/signature hard errors, malformed
  non-list `requests`) rather than hard Pydantic errors. Each nested request accepts a JSON
  object/array body directly; `ops/` serializes it, avoiding fragile escaped
  JSON strings that small models abbreviate with `...`. Batching is critical:
  replaying a 10–12K-character observation once per endpoint caused excessive
  provider calls and token usage. Caps: request `body` `MAX_BODY_CHARS` (16000,
  soft-truncate), descriptions/scripts truncated at 8000 with a `warnings:` line,
  params at 40/request (trim). Enrichment fields: markdown collection/request
  `description`, query `params` (with per-row descriptions), collection/request
  `pre_script`/`test_script`, optional `auth` (Postmark auth with `{{variables}}`
  for credentials), `default_headers` (request headers override), and up to
  `MAX_SAVED_RESPONSES` (12) saved response examples per request
  (`MAX_SAVED_RESPONSE_BODY` 6000), each with `preview_language` sniffed from the
  example body and an `original_request` Postman snapshot of the parent request
  (method/url/headers/body) for the Saved Responses **Request Body** tab.
  with a known `kind` from `collection_draft/recipes/`
  (`sha256_apikey_secret_timestamp`, `hmac_sha256`); `ops/` validates via
  `recipe_for_kind` (unknown → recoverable error; unsafe header/var override
  names that could break out of generated script string literals are rejected
  via `validate_signature_overrides`) and `build.py` prepends the
  reviewed signing script to collection `events.pre_request` plus recipe
  credential variables. **Never invent crypto in the model** — uncovered
  algorithms get a description note only. Script language comes from
  `collection_draft/config.py` `draft_script_language()` (QSettings
  `ai/draft_script_language`, default `python`; Settings → AI → Agents combo);
  emitted `scripts`/`events` dicts carry `language`/`pre_language`/`test_language`.
  At finish, `build.py` rewrites URL placeholders `{var}` / `:var` / `<var>` to
  `{{var}}` and auto-creates missing collection variables (bodies never scanned).
  Draft state lives per session in `collection_draft/state.py`, not in the model's
  context, so a drifting agent calls `status` and resumes. Only `finish` writes —
  it assembles a `ParsedCollection` and persists through
  `ImportService.import_parsed`, returning the real collection id plus an
  `enrichment:` summary (including `signature script` when a recipe was used).
  Every other operation is LOW risk (see
  `auto_approve.draft_operation_is_write`), otherwise each added request would
  raise its own Approve card. This exists because asking a small model for one
  complete Postman JSON fails silently and it narrates success instead.

  **OpenAPI security** (`import_parser/openapi/security.py`, wired from
  `mapping.build_collection_from_openapi`): maps `components.securitySchemes` +
  root `security` (falls back to the first per-operation `security` when root
  is absent). Multi-alternative OR requirements and AND of non-signature
  schemes → description note only. Hotelbeds-style `apiKey` + signature-header
  pair → `sha256_apikey_secret_timestamp` recipe pre-request + `{{apiKey}}`/
  `{{secret}}` (header names sanitized before script generation). Plain
  `apiKey` / `http basic` / `http bearer` → collection auth + credential
  variables. Expedia-style required `Authorization` (description hints at
  signing/docs) + `apikey`/`api_key` header or query **without** schemes →
  variables + “algorithm not specified” description note, **no** fabricated
  script. oauth2 / openIdConnect / mutualTLS → description note only.

  **Fabricated link guard** — `claim_guard.strip_unbacked_collection_links`
  removes any `postmark://collection/<id>` in the final message whose id no
  observation produced this turn, tracked via `write_ledger.record_collection_ids`.
  The write ledger uses shared `auto_approve.is_mutate_or_execute_tool` (via
  `claim_guard.observation_records_write`); for `postmark_collection_draft` only
  a finish observation (the `mutation_id:` marker) counts as a write — start /
  add_requests must not silence the unverified-write note. Phrase-matching alone
  is insufficient: a model can claim a write in wording the regexes miss while
  still emitting a link that opens an unrelated collection.
  **`postmark_workspace_query`** (`tools/workspace_query/`) reads the user's
  collections, requests, environments, run history, and open-tab state on demand.
  **Shared send orchestration** lives in `services/ai/chat/execution/`
  (`run_shared_send`, `apply_send_auth`, `redact_send_result`, agent wrappers in
  `agent_send.py`): UI `HttpSendWorker` (non-debug) and agent execute share this
  path; `agent_local_script.py` runs local script tabs via `run_local_entry`.
  Debug step-through stays in the worker only. Agent concurrent sends may
  set `acquire_agent_slot=True` (process-wide semaphore, max 3, wait ≤60s).
  `run_agent_scripts` runs pre/test/both without HTTP; `run_agent_local_script`
  runs a local script tab without HTTP; successful agent sends
  with `record_history=True` call `RequestHistoryService.record_send`.
  Mutate (`tools/workspace_mutate/`: `tool.py` dispatches to `collection_ops`,
  `local_ops`, `data_ops/`, `debug_ops`, `settings_ops/`; `common.py` secrets policy) supports
  collection/request CRUD + `assertion_set` replace, local scripts/folders,
  environments, **active_environment** (bridge-only UI set/clear), globals,
  snippets, saved responses, **history_entry** delete,
  **script_version** restore (merge-safe), collection **events** (folder
  scripts), **debug_metadata** (breakpoints/watches via merge APIs), and
  **settings** (allowlisted RuntimeSettings / history / tab prefs; never AI credentials).
  Create request applies
  `description`/`body_mode`/`body_options`/optional `auth` via `update_request`
  after create (auth-only collection/request updates delegate to `data_ops.apply_auth_update`).
  Binary `body_mode` paths are validated with `execution/binary/path_policy` on mutate and send.
  Execute (`tools/workspace_execute/dispatch.py` → `execution/*`) includes send/draft/replay,
  `run_scripts`, `run_local_script`, **`run_collection`**, **`run_iterations`**,
  **`fetch_graphql_schema`**, **`generate_snippet`** (auth secrets as `{{var}}`),
  **`export_workspace_artifact`**, and **`oauth_get_token`** v1 (client_credentials/password;
  token bound to env secret var; never Always-allow). Drain refreshes `_env_selector` for env CRUD / active env,
  history panels on history delete, attaches GraphQL schemas to open editors, and opens folder Runs / Scripts for
  collection / iteration executes.
  `WorkspaceQueryExecutor` resolves the parent chat session id via
  `resolve_workspace_session_id` / `parent_session_id_from_persistence_dir` when
  the tool runs inside a subagent conversation under
  ``<session_disk>/subagents/`` (live scopes still use the parent run snapshot).
  `execute_workspace_query` caps total output at `_MAX_OUTPUT_CHARS` (48k, headroom
  under OpenHands' 50k TextContent limit) via `_truncate_output` (prepends
  ``[truncated]`` and appends a trailing footer when char-capped); `open_tabs` also
  caps row count at `_MAX_RESULT_ROWS` (50). `runs` (latest 10) and `recent_history`
  (latest 25) lead with ``[partial]`` when their list limits bind. Scopes: `overview`, `open_tabs`, `active_tab`, `active_response`, `tab`, `collection_tree`, `collection`, `local_scripts`, `recent_history`,
  `request`, `request_history`, `history_entry`, `saved_responses`, `saved_response`,
  `runs`, `run`, `environments`, `env_reach`, `search`, `variable`, `script`, `script_versions`, `request_script_versions`, `script_version`, `globals`, `snippets`, `snippet`, `insights`, `dependencies`, `walkthrough`, `settings`. Search uses whitespace-split AND token matching (multi-token empties are ``[partial]``; single-token empties stay ``[authoritative]`` when exhaustive); deep hits include folder-path breadcrumbs;   unrestricted search also covers **enabled** environment/global variable keys (masked secret values and disabled keys excluded from the haystack; env/global scanning is skipped under ``within_ids``). History filters (`request_history` / `recent_history`) stay single-phrase. `scope=variable` reports definitions, an active override chain labeled with environment/request-or-collection context (collection secret-typed winners masked like Definitions; ``{{key}}`` usage matching is case-sensitive / exact spelling, and always includes the search needle spelling so case-mismatched unresolved refs are still found), and bounded usages. `scope=env_reach` maps requests to resolved hostnames under an environment (`target_id` or snapshot current; `search=diff:<idA>:<idB>` compares hosts). `scope=dependencies` builds a static producer→consumer graph from literal `pm.*.set("key", …)` plus `{{key}}` usages (standing static-analysis caveat). `scope=walkthrough` assembles a collection narrative from those edges. Search script bodies via
  `CollectionService.fetch_request_scripts_for_ids()` and folder scripts via
  `fetch_folder_scripts_for_ids()`; request bodies/headers/auth via
  `fetch_request_fields_for_ids()` (includes ``request_parameters``); local-script bodies via
  `LocalScriptService.fetch_local_script_contents_for_ids()` (bounded to first 200
  items in tree order). `scope=request` / `scope=collection` surface ``Last edited``;
  `scope=request` also shows ``Last sent`` via `RequestHistoryService.latest_for_request`
  (failed sends print the literal ``error``, never raw exception text).
  `scope=insights` is workspace health (`render/insights/scans/`): missing tests / declarative assertions
  (`fetch_assertion_counts_for_ids`), duplicate method+URL (non-empty URLs;
  ``_truncate_url`` / ``_redact_url``), unresolved ``{{vars}}``, unused definitions,
  case-mismatch refs, disabled-but-referenced, auth gaps, secret hygiene (keys only),
  local-script breakage (`collect_direct_local_dependency_diagnostics`), request drift
  vs last send, script regressions, dead requests (`request_ids_with_history` /
  `request_ids_with_saved_responses`), JWT token expiry (relative only; `now`-injected),
  and response-shape drift (typed paths of latest two 2xx JSON sends via
  `latest_two_json_success_entry_ids`). Optional ``within_ids`` / ``search`` section
  filter. ``scope=search`` supports fielded operators via ``query_parse.py``
  (``in:``/``method:``/``has:``/``missing:``/``resolved:1``/OR/NOT/phrases); the agent
  prompt + tool description require translating plain-language finds into those
  operators silently (never ask the user to type them; never quote operators /
  coverage jargon in the chat reply — follow-ups stay plain English). Assertions
  via ``in:assert``; optional ``goals`` (max 4) batches multi-goal explorations with
  ``within=`` chaining (`goals.py`). Overview uses `count_all_collections()` / `count_all_requests()`
  instead of loading the full tree; the active-tab line includes dirty/deferred state
  plus method/URL when available, and stamps `captured_at` from the turn-start
  snapshot. Open tabs,
  unsaved editor payloads (dirty request ``request_data``; dirty folder ``collection_data``;
  dirty environments flagged), per-tab `last_response` scalars, masked `local_overrides`,
  deferred-tab chips (`is_deferred` → ``[deferred]`` not ``[saved]``),
  and the live response (including `send_error` / `viewing_stored_entry_id` when the
  viewer shows a failed send or stored history entry, plus `test_results`, `console_logs`,
  `timing`, `network`, size breakdown ints, and bounded `variable_changes` /
  `pre_request_variable_changes` when scripts ran) are captured in
  `workspace_snapshot.py` on the GUI thread at chat run start
  (`_AiChatRunsMixin._build_ai_workspace_snapshot`; request tabs call
  `RequestEditorWidget.get_request_data(cancel_pending_persist=False)` so snapshot reads
  do not cancel debounced debug-metadata writes); cleared when the session's last
  run finishes (`clear_workspace_snapshot` in `_on_registry_run_finished`, which also
  clears `set_last_search_hits` / last search hit ids for refine). The tool
  executor reads that snapshot plus live DB slices off the worker thread. Form /
  opaque bodies and env/collection variables redact sensitive keys (not only
  `type=secret`); secret-like search needles get a ``[partial]`` redaction warning
  instead of an authoritative empty. Assistant
  replies may link items as `postmark://request|collection|script|tab|history|environment|saved_response/<id>` (optional
  `?focus=test`, etc.); unsaved open-tab drafts use 1-based `postmark://tab/<n>` (tab
  index at turn start + 1) in `open_tabs` and `active_tab` (`open_tabs` notes that
  indices are turn-start). The default agent prompt
  and `WORKSPACE_QUERY_DESCRIPTION` require self-contained answers (tool output is
  never shown in the chat UI — never refer to "search output above"), named
  markdown links only (never bare numeric ids, never ask the user for an id;
  example rows use `postmark://request/<id>` not a literal id). Non-linkable
  entities (runs, snippets, versions) put numeric
  ids only in an ``Ids for follow-up calls (tool arguments only…)`` block — list
  rows stay free of ``[id=N]`` / ``run #N`` priming. History sends, environments, and
  saved examples use named deep-links. Partial/authoritative/capped
  markers are placed at the **top** of observations so 48k truncation cannot drop
  them. Prefer ``active_tab``/``open_tabs`` over ``scope=request`` for dirty open
  tabs; past sends of the open request use ``scope=request_history`` + ``search=``
  (not ``scope=search``); refining a prior result list uses ``scope=search`` with
  ``within_ids`` from previous ``postmark://request/<id>`` links, or
  ``within_ids=[-1]`` to reuse the session's last search hit set (full ids before
  display cap; cleared with the workspace snapshot). Invalid ``within_ids`` error
  out (never unrestricted). ``scope=request`` merges dirty open-tab
  ``request_data`` over DB when the snapshot has a matching dirty tab. Search
  covers params tables (after secret redaction), bodies, headers/auth, scripts,
  assertions (``in:assert``), and environment/global variable keys (non-secret values);
  history bodies only via ``request_history`` ``body:`` (always partial). `MarkdownContent` emits `workspace_target_requested` →  `AiChatPanel` → `MainWindow._on_workspace_target_requested` to open/focus tabs
  (`tab` → `_focus_open_tab`; `history` → `_open_from_global_history`, with a
  status tip when a second open arrives while busy; malformed `postmark://`
  paths never fall through to `QDesktopServices`;
  `environment` → `_open_environments_tab`; `saved_response` → open request + Saved
  Responses panel; `?focus=` applied only for supported keys when the active tab's
  `request_id` matches — unsupported focus tips after open; unknown kinds, stale
  tabs, and missing entities show a status-bar tip instead of silently no-opping).
  Subagent runs persist under ``<session_disk>/subagents/{uuid}/`` (per parent
  chat session). ``PostmarkDelegateExecutor`` registers spawn id → folder at
  spawn time (`subagent_disk_registry.py`); ``SubagentEventTracker``
  (`subagent_events.py`) parses task/delegate SDK events in ``AiChatWorker.event_cb``
  and emits ``subagent_updated``. Records include ``task_prompt`` (full delegated
  task)   and ``disk_path`` (child conversation dir). Inline wiki/task observations also store
  ``result_markdown`` (full tool reply for ``SubagentDetailDialog``) alongside a short
  ``result_preview`` (card/activity clip). Reload falls back to task-text
  matching under the session ``subagents/`` dir when the in-memory registry is empty.
  Clicking a transcript card opens ``SubagentDetailDialog`` (non-modal) with
  a type chip + colored status pill header, conditional Task callout (hidden when
  redundant with the title), live Activity steps (lightbulb steps filtered;
  reasoning only in Thought block) with inline detail previews, a collapsible Thought
  block from ``SubagentTranscriptView.thinking_markdown`` (scroll-capped in the dialog),
  markdown reply from disk via ``load_subagent_disk_snapshot`` when ``disk_path`` is set,
  otherwise the full ``result_markdown`` (not the clipped preview), and a footer
  **Copy message** control for the reply markdown;
  ``_apply_subagent_update``
  pushes worker updates (including terminal) to an open dialog.
  Parallel delegate
  cap: `max_parallel_subagents()` (`subagent_limits.py`, QSettings
  `ai/max_parallel_subagents`, default 5). `max_iteration_per_run` is 10 for
  delegation + wiki tool loops.
  MainWindow wiring: `_AiChatControllerMixin` (`ai_chat_controller.py`) with
  `_AiChatRunsMixin`, `_AiChatTurnFinalizeMixin`, `_AiChatTitleMixin`.
  Settings UI: tree branch **AI** (overview) → **Models** and **Budgets** children;
  `ui/dialogs/settings/ai_page.py` + `AiProviderDialog` (per-provider credentials,
  **Budgets** in
  `ui/dialogs/settings/ai_budget/` with `AiBudgetConfig` (`ai/provider_budgets`),
  `budget_period.py`, and `spend_rollup.global_spend_summary()` for period/all-time
  spend on the Budgets page. Chat enforcement uses
  `services/ai/chat/budget_status.connection_budget_status()` against
  `global_spend_summary()` period totals when soft/hard caps are configured
  (skips the rollup when no caps are set — New chat / send-gate chrome only needs
  spend for enforcement). Soft exceed shows a composer banner;
  hard exceed disables send (including edit-resend) until the period resets or
  limits change in Settings. `message_usage.entry_for_model_id` searches
  caller-supplied `extra_entries` before reading `AiConfig.get_models()` so
  spend rollups do not re-parse QSettings per lookup. **New chat**
  (`_on_ai_new_chat`) clears the panel once — `panel.clear()` already resets
  context/budget chrome (do not call `_reset_context_usage_chrome` again).
  Session USD spend is computed on read in `message_usage.session_spend_breakdown`
  (per-model rows) and shown on the **Spend** tab inside `AiChatContextUsagePopup`
  (composer ring unchanged). Per-message footer costs and the Spend rollup share
  `pricing_model_id_for_assistant_message()` (assistant `model_id`, else preceding
  user `send_model_id`, else session default). Assistant rows persist SDK per-turn
  USD in `cost_usd` (OpenHands ``accumulated_cost`` delta per run, including cache
  pricing); older rows without `cost_usd` fall back to token-rate estimates. When limits are configured for the active connection,
  the Spend tab also shows period spend vs soft/hard caps (`aiChatBudgetStatusCard`).
  Apply calls `AiPageController.apply()`.
- `RunHistoryService` follows the same `@staticmethod` pattern.  It wraps
  `run_history_repository` for run history CRUD (create, finish, add result,
  query runs/results, delete).
- `RequestHistoryService` (`request_history_service.py`) persists HTTP **send**
  history: `gather_send_identity` at send start, `record_send` at the end of
  `on_send_finished` (skipped when `_suppress_history_record` is set during
  debug replay); refreshes `_global_history_panel` always and
  `_request_history_panel` when the active tab matches the recorded request.
  Settings: `services/history_retention_config.py` is the single source of
  truth for `history/*` QSettings keys/defaults/clamps (`load_history_retention_config`);
  `HistorySettingsManager` wraps it for the Settings UI. Bodies and
  snapshots under `user_history_root()`; metadata in `request_history_entries`.
  **Lists:** `list_for_sidebar` (left global rail; optional `limit`, default 500;
  workspace `recent_history` uses `limit=25`), `list_for_request` (right
  per-request), `latest_for_request` (newest send metadata, `LIMIT 1`). **Labels:** `was_persisted_request` drives `source_label`
  `(deleted)` vs `(draft)` when `request_id` is null. **Display:**
  Orphan/deleted rows: draft tab opens instantly from metadata; full payload loads
  on a worker thread (`history_navigation/orphan_open.py`). ``TabContext.variable_collection_id``
  restores collection variables/auth when ``request_id`` is ``None``.
  `entry_to_http_response_dict` → `ResponseViewer.load_stored_response` (not
  live/saveable). **Replay:** `build_send_payload_from_entry`; `delete_entry`
  removes row and files. **Global open:** `_HistoryNavigationMixin`
  (`history_navigation/`) — `entry_open_requested` → `_open_from_global_history`
  (existing tab + right `focus_entry` only; centre `load_stored_response` for orphans).
- `ScriptService` and `ScriptEngine` also follow the `@staticmethod`
  pattern.  `ScriptService.build_script_chain(request_id)` walks the
  ancestor chain to collect inherited scripts.  `ScriptEngine` dispatches
  to `DenoRuntime` for **JavaScript** and **TypeScript** (``deno run`` +
  `data/scripts/deno_drain.mjs` for ``pm.sendRequest`` IPC; TypeScript uses a
  ``bundle.ts`` temp file so Deno strips types) or `PyRuntime` (Pyodide under Deno when
  :file:`data/scripts/vendor_pyodide/` is present, otherwise RestrictedPython
  subprocess via :file:`_py_sandbox.py`; subprocess env sets ``POSTMARK_SANDBOX=1``
  via :func:`restricted_python_subprocess_env` so ``services`` package inits skip
  OpenHands/Deno re-exports).
  Python ``pm.require("local:…py")`` is resolved on the host via
  ``local_script_modules.resolve_required`` / ``py_runtime.local_module_sources``
  and injected as a ``local_modules`` map into the Pyodide payload
  (:file:`pyodide_run.mjs` → ``__pm_local_modules_json`` / ``pm_bootstrap.py``),
  the RestrictedPython sandbox payload (:file:`_py_sandbox.py` loader +
  ``_Pm.require`` ``local:`` branch), and the Python debug payload
  (:file:`debug/py_debug.py`). There is no static ``import`` between Python
  local scripts (JS/TS mirror only).
  :class:`JSRuntime` delegates execution to :class:`DenoRuntime` and provides
  bootstrap and vendor file loaders.  JavaScript parse for the linter and
  gutter uses Esprima via :mod:`esprima_deno` (Deno subprocess;
  :file:`data/scripts/esprima_parse.mjs`); **TypeScript** skips Esprima lint until a TS parser exists.
  `RuntimeSettings` (``scripting/deno_path``, ``scripting/python_path``,
  ``scripting/lsp_enabled`` in QSettings) resolves/validates executables and
  toggles IDE-style language servers for script editors. LSP/editor debounce
  intervals (ms, QSettings keys under ``scripting/lsp_*_debounce_ms``):
  ``lsp_did_change_debounce_ms`` (default 250),
  ``lsp_pm_require_debounce_ms`` (350),
  ``lsp_diag_clear_debounce_ms`` (250),
  ``lsp_dep_diag_debounce_ms`` (300); read by
  ``EditorLspAdapter`` timers in ``lsp_integration.py``. Debounced
  ``pm_require_index.ts`` generation and ``deno cache`` for literal
  ``pm.require('npm:…'|'jsr:…')`` specifiers in JS/TS script editors.
  :mod:`services.lsp.js_lsp_preamble` prepends triple-slash references to
  ``stubs/pm.d.ts`` and ``pm_require_index.ts`` on virtual buffers sent to Deno LSP
  (without this, ``pm`` and npm return types are invisible to completions). Private package
  registries (`scripting/registries/entries` JSON list, `scripting/pypi/*`)
  are read by :func:`services.scripting.deno_runtime._build_npmrc_text` and
  :func:`services.scripting.pyodide_runtime._resolve_pypi_index_urls` — see
  [docs/scripting/external-packages.md](../docs/scripting/external-packages.md).
  Tokens live in :mod:`services.scripting.secret_store` (OS keychain
  preferred via `_pin_platform_keyring_backend` — never loads foreign
  keyring entry points such as macOS-on-Linux; encrypted-file fallback)
  and never appear in `QSettings`.
  ``CodeEditorWidget.notify_lsp_diagnostics`` / ``lsp_diagnostics_changed`` expose
  ``textDocument/publishDiagnostics`` to the script **Problems** tab (see
  ``ui/widgets/code_editor/lsp_integration.py`` ``EditorLspAdapter``).
  Local script editors (JS/TS) also offer deterministic **ESM relative import path**
  auto-suggest inside ``import`` / ``export … from`` string literals
  (``completion/path_completions``; requires ``CompletionEngine._local_script_id``).
  During an active debug session, ``editor_lsp_glue.set_debug_session_active``
  suspends LSP ``didChange``, fold/validate timers, format-on-idle, test-gutter
  rescans, and LSP completion/hover (schema completion still works).
  ``LspRegistry.warm_async(bucket)`` spawns Deno/jedi on a worker thread
  (``services.lsp.servers.spawn``); ``warm(bucket=None)`` schedules both buckets.
  First script attach calls ``warm_async`` for that bucket only. Editors may set
  ``set_lsp_attach_deferred(True)`` until visible (request pre/test sub-tabs).
  **Local script tabs (JS/TS):** ``ScriptEditorPane.load_content`` starts
  ``LocalScriptLspPrepWorker`` (``prepare_local_script_lsp_attach`` on a
  background thread: mirror, one ``build_module_index``, import closure,
  ``pm_require_index.ts``) and calls ``finalize_local_script_lsp_attach`` on the
  GUI thread when prep and the Deno bucket are both ready. ``EditorLspAdapter.attach(prep=…)``
  skips redundant sync when prep succeeded. ``CodeEditorWidget._lsp_attach_token``
  invalidates stale worker callbacks on tab close/switch. Set
  ``ASYNC_LOCAL_LSP_PREP = False`` in ``local_script_lsp_prep`` to restore
  synchronous attach. Request/folder script editors are unchanged.
  Script output strip tab (Output / Debugger / …) is persisted per script type
  under ``scripting/output_sub_tab/{pre_request|test}`` via
  ``script_output_tab_prefs``; ``hide_debug_controls`` no longer forces Output;
  Inline debug completion never auto-switches to Output (``focus_output=False``);
  use **Run** or open the Output tab to view console/tests. Tab choice is persisted.
  ``end_debug_ui`` / ``resume_all_debug_suspended_editors`` must run on every
  session exit (tracked via a WeakSet) so LSP is not left suspended after crash
  or tab close.
  Direct ``pm.require('local:…')`` dependencies are linted via
  ``local_dependency_diagnostics.collect_direct_local_dependency_diagnostics``
  (Problems rows prefixed ``[local:path]``; gutter squiggles on the require line).
  ``services.lsp.client.Diagnostic`` optional ``related_local_*`` fields drive
  Problems-tab navigation to the local script editor.
  ``pm_require_types.prune_orphan_specs`` / ``reset_workspace`` drop stale
  ``pm_require_index.ts`` workspace keys; ``DebugWatchesPane.set_idle`` prunes
  against ``EditorLspAdapter.live_js_buffer_keys()`` (settings dialog **Reset
  LSP workspace caches** calls ``reset_workspace``).
  Diagnostic severities ``error`` / ``warning`` / ``info`` / ``hint`` map through to
  ``SyntaxError_`` and drive distinct wave underlines plus line-number gutter tint
  (``gutter.normalize_validation_severity``, ``line_worst_validation_severity``).
  TypedDicts (`ScriptInput`, `ScriptOutput`, `TestResult`,
  `ConsoleLog` (optional ``source_line`` for inline editor annotations),
  `ScriptEntry`) live in `services/scripting/__init__.py`.
  ``CodeEditorWidget.set_inline_log_annotations`` / ``clear_inline_log_annotations``
  paint faint trailing console output after script runs
  (wired from ``ScriptOutputPanel`` / ``ScriptEditorPane``).
  `find_pm_tests(source, language)` in `engine.py` locates `pm.test("name", …)`
  call sites (Python AST or JavaScript/TypeScript esprima when parseable, with regex fallback) for the
  per-test script gutter.  `find_top_level_statement_lines(source, language)`
  returns 0-based top-level statement lines (where the step-debugger can pause);
  the post-response editor uses it to render unreachable breakpoints with a
  muted style.  `ScriptLinter._esprima_parse_result()` shares the
  same esprima JSON round-trip as the linter.
  `ScriptLinter.check_es_module()` (see `es_module_rules.py`) flags
  CommonJS ``module.exports`` / non-vendor ``require()`` in script editors
  and merges into LSP gutter + Problems tab; Deno LSP CommonJS→ESM hints
  (TS 80001) are **not** filtered. Deno stderr is stripped via
  ``format_process_stderr()`` before UI display.
  `DenoManager` manages a **downloaded** Deno under
  `~/.local/share/postmark/runtimes/deno-<version>/` (`managed_deno_path()`);
  full resolution also uses `PATH` and `RuntimeSettings` (see
  `runtime_settings.py`).
  `pm.sendRequest()` uses a host-side HTTP bridge (`execute_sub_request`
  in `context.py`) with a trampoline loop (JS) or IPC protocol (Python).
  The JS-side rate limit is 10 calls; the host enforces a hard cap of 50
  total sub-requests per execution (`_MAX_TOTAL_SUBREQUESTS`).  Responses
  larger than 10 MB are rejected (`_MAX_RESPONSE_BYTES`).
  `pm.globals` are persisted to `data/globals.json` via `load_globals()`
  / `save_globals()` in `context.py`.
  Vendor libraries (CryptoJS, lodash, moment, chai, tv4, ajv, xml2js,
  csv-parse) live in `data/scripts/vendor/` and are **lazily loaded** —
  only when the script contains a matching `require()` call or uses a
  known global (e.g. `CryptoJS`).  Detection is in `_detect_required_modules()`
  with `_REQUIRE_MAP` and `_GLOBAL_IMPLIES`.  `require('uuid')` is built
  into the bootstrap.  The `postman` legacy API object delegates to
  `pm.environment`/`pm.globals`.
  Postman-style response assertions: `pm.response.to` (JS getter on the
  response object; Python ``@property`` on ``_PmResponse``) returns a fresh
  ``__Expectation`` / :class:`_Expectation` for ``.have.status`` / ``.header`` /
  ``.jsonBody`` (Python also ``json_body``) on the mock/live response.
- **Debug sub-package** (`services/scripting/debug/`):
  `DebugProtocol` (:class:`QObject`) is a thread-safe state machine that coordinates
  pause/resume between the worker thread and the UI.   Watch re-evaluation uses :class:`_EvalWorker` (``threading.Thread``, not
  ``QThread`` — evaluate callbacks are registered from the debug worker thread
  while :class:`DebugProtocol` stays on the GUI thread): UI calls
  :meth:`submit_evaluate` / :meth:`cached_evaluate`; results arrive on
  :attr:`evaluated` (``expr``, ``value``) via a queued main-thread invoke.
  :meth:`set_evaluate_callback` starts the worker;
  :meth:`set_evaluate_callback_sync` registers a callback without a worker
  (unit tests). :meth:`set_evaluate_batch_callback` batches multiple expressions
  per drain (Python sandbox ``evalMany`` IPC; Deno pipelined CDP in
  ``evaluate_many``). :meth:`clear_eval_cache` on pause/frame change and
  ``DebugWatchesPane.set_idle``. Display placeholder: ``WATCH_VALUE_PLACEHOLDER``
  (em dash) in ``protocol.py``.
  `js_debug.debug_execute` delegates to `deno_debug.debug_execute`, which
  runs Deno with ``--inspect-brk``, drives the V8 debugger over CDP
  (WebSocket), sets breakpoints, and steps with
  `Runtime.evaluate` / `protocol.checkpoint()`.  `inject_checkpoints` and
  `js_debug` group splitting prepare statement boundaries for the inspector.
  `py_debug.debug_execute` launches a subprocess with `sys.settrace` and
  uses IPC for pause/resume.
  `engine.run_debug_chain` mirrors `_run_chain` but routes through debug
  dispatch.  TypedDicts: `CallFrame`, `DebugPauseInfo` (includes `call_stack`,
  `selected_frame_index`), enums: `DebugState`, `StepMode`.
  Runtime adapters registered by `deno_debug` / `py_debug` while paused:
  :meth:`submit_evaluate` / batch callback for watches;
  :meth:`evaluate` remains for sync callers and tests;
  :meth:`select_frame(index)` refreshes locals via the frame-locals callback.
  Breakpoints are ``dict[int, str | None]`` (line → optional condition).
  JS conditions pass to CDP ``Debugger.setBreakpointByUrl``; Python sandbox
  evaluates conditions fail-open in ``sys.settrace``.
  On pause, Python `debugPause` includes a `pm.response` string in
  `locals` (built from the sandbox `pm` object).  JS variable reads merge
  `pm.response` fields into the `pm` map for the debug variables panel
  (`js_debug._READ_JS_DEBUG_VARS` — nested ``pm`` hover snapshot:
  ``info``, ``request``, ``response`` (or ``null``), ``variables``,
  ``environment``, ``collectionVariables``, ``globals``, ``iterationData``,
  ``cookies``, ``execution``).  Deno/CDP pauses extend
  `checkpoint(..., local_vars=...)` with optional ``locals`` (flat name→value
  map, innermost lexical binding wins) and ``scopes`` (ordered list of
  ``{type, name, vars}`` from ``callFrames[0].scopeChain``) for the debug
  panel and editor hover.  ``send_pipeline._merge_debug_hover_values`` flattens
  ``globals``/``pm`` into one map for word hover; ``send_pipeline._debug_hover_root_objects``
  passes whole ``pm`` and ``console`` dicts via ``CodeEditorWidget.set_debug_locals(..., root_values=...)``
  so the identifier ``pm`` still resolves after flattening, and dict/list values
  use ``debug_hover_popup.DebugValuePopup`` (expandable tree; stays until a
  mouse press outside the popup on the editor or main window or Escape in the editor;
  the editor does not dismiss it when ``_var_at_cursor`` flickers off the token).
  :func:`deno_runtime.build_debug_bundle_text`
  wraps the user script in ``async function __pm_debugUserScript() { … }``
  so ``const``/``let`` bind under a ``local`` CDP scope instead of sharing
  the bundle ``module`` record with polyfills.  The wrapper **must** be
  ``async`` because user scripts may use top-level ``await pm.sendRequest(…)``
  (Postman API parity); a sync wrapper would make ``await`` a parse error and
  no breakpoints could fire.  The call site is ``await __pm_debugUserScript();``
  so the trailing drain code (which queues ``__done__``) runs **after** the
  user script's awaits resolve — without the outer ``await``, ``pm.test``
  results queued post-await would race the drain and be lost.  Adding any
  new debug-bundle wrapper for a future language must follow the same
  rule: if user code can ``await`` (or ``async`` block, etc.), the wrapper
  must allow it AND the drain hook must wait for it.  See the comment
  above ``_DEBUG_USER_SCRIPT_HEAD`` in
  :file:`src/services/scripting/deno_runtime.py`.  While paused in
  ``__pm_debugUserScript`` or ``__denoIpcDrain``, the ``module`` scope is
  skipped entirely; otherwise ``module`` property names starting with ``__``
  are dropped.  Collected scope types include ``module``, ``local``, ``block``,
  etc.  ``pm_bootstrap.js`` assigns ``globalThis.__pm_state`` and ``globalThis.pm``,
  including ``pm.require`` for ``npm:`` / ``jsr:`` specifiers pre-bundled as static
  imports in ``deno_runtime._build_bundle_text``, so ``Debugger.evaluateOnCallFrame`` (paused inside the user wrapper) can read
  ``variable_changes`` for the debug panel.  The debug bundle mirrors
  ``__pm_baseline_json`` onto ``globalThis`` so the same evaluation can parse the
  globals baseline without a ``ReferenceError`` on module-only ``var`` bindings.
  CDP ``evaluateOnCallFrame`` nests the RemoteObject under ``result``;
  ``js_debug.cdp_evaluation_result_string`` unwraps the JSON string, and
  ``js_debug.cdp_runtime_evaluate_json_object`` reads ``variable_changes`` /
  ``global_variable_changes`` via ``Runtime.evaluate`` when the call-frame read
  is empty.
  ``deno_scope._collect_call_frame_scopes`` walks CDP ``scopeChain`` and deep
  expands object bindings (all scope types) via nested ``Runtime.getProperties``
  so the inspector and merged hover locals receive JSON-like dicts instead of
  RemoteObject description strings like ``Object`` / ``Array(...)``.
  Deno binds ``Debugger.setBreakpointByUrl`` at the union of top-level group
  starts (``js_debug._split_into_groups``) and ``DebugProtocol`` editor lines
  (``deno_debug._cdp_break_editor_lines``); pauses mapped into the user-script
  line range call ``checkpoint`` so breakpoints inside nested callbacks (e.g.
  ``pm.test`` bodies) work.  Changing breakpoints while a Deno session is
  paused does not push new CDP breakpoints until the next debug run.

## Snippets (script editors)

Declarative **script snippets** (Postman-style one-click insert) combine shipped
JSON under `data/snippets/` with **user snippets** in the ``snippets`` table
(``SnippetService`` / ``snippet_repository``).  ``ui/widgets/snippets/loader.py``
merges both sources (user categories first) and memoises per
``(language)``; ``invalidate_snippet_cache()`` runs
on user-snippet CRUD.  ``ui/widgets/snippets/popup.py`` is the
read-only insert popover (user rows styled with ``userSnippetLabel``); create/edit/delete
live in ``snippet_capture_dialog.py`` and ``ui/sidebar/snippets_sidebar_panel.py``
(tree: JavaScript / TypeScript / Python → category → snippet; ``ts`` vs ``js`` in DB;
right-click menus in ``snippets_tree_context.py`` (edit/rename/remove;
``SnippetService.delete_snippets_in_category``, ``rename_category``).
**Save as snippet…** opens the
dialog from ``CodeEditorWidget``; ``MainWindow.refresh_snippets_sidebar()`` refreshes
the sidebar list and an open picker after CRUD.  The **Snippets** toolbar control
lives in ``ScriptEditorPane``.  Authoring guide: ``data/snippets/README.md``.

Shipped JSON includes **Workflows**, **Variables**, **Tests** (e.g. status code or reason
phrase, ``to.have.body``, ``to.be.oneOf`` / ``one_of``), and **Pre-request helpers**.
Assertion helpers live in ``data/scripts/pm_bootstrap.js`` and ``data/scripts/pm_bootstrap.py``;
the RestrictedPython subprocess path mirrors the same expectations in
``services/scripting/_py_sandbox.py`` (keep Python snippet bodies on the injected
stdlib shims documented in that module and in ``data/snippets/README.md``).

**Postman API parity:** ``src/services/scripting/pm_api_schema.py`` is the linter /
schema source of truth; ``tests/unit/services/test_pm_api_schema_drift.py`` probes
that every schema path exists on the live ``pm`` / ``postman`` objects inside
``data/scripts/pm_bootstrap.js``. Both Python runtimes
(``data/scripts/pm_bootstrap.py`` for Pyodide and
``src/services/scripting/_py_sandbox.py`` for RestrictedPython) now mirror the JS
surface: ``HeaderList``, ``Url``, discriminated ``RequestBody``, resolved
``pm.variables``, ``pm.test.skip``, ``pm.execution.location``, response helpers
(``originalRequest`` / ``cookies`` / ``reason`` / ``mime`` / ``dataURI`` / ``size``),
``pm.cookies.jar()``, bare-name ``pm.require``, legacy globals (``responseBody``,
``responseCode``, ``responseHeaders``, ``tests``, ``xml2Json``), the ``postman``
v1 shim, and a ``pm.visualizer.set`` stub that raises a documented error. Python
keeps ``snake_case`` attributes and adds ``camelCase`` aliases
(``pm.collectionVariables`` etc.) so Postman scripts pasted unchanged into a
Python tab still resolve. **Note:** Python ``pm.send_request`` is synchronous —
pyodide / RestrictedPython have no event loop, so no ``await``. New Python
parity coverage lives in ``tests/unit/services/test_pm_python_parity.py``.

## The dict interchange schema

`fetch_all_collections()` in the repository converts ORM objects to a nested
dict **inside the open session** (required because relationships are loaded
lazily per-query).  This dict is the canonical data format that flows from
DB through the service layer, across the thread boundary, and into
`CollectionTree.set_collections()`.

```python
# Top-level: str(collection.id) -> collection dict
{
  "42": {
    "id": 42,                    # int — database PK
    "name": "My Folder",         # str
    "type": "folder",            # literal "folder"
    "children": {                # str(child_id) -> child dict
      "99": {                    # request child
        "type": "request",
        "id": 99,
        "name": "Get Users",
        "method": "GET",
      },
      "43": {                    # nested folder child
        "type": "folder",
        "id": 43,
        "name": "Subfolder",
        "children": { ... },
      },
    },
  },
}
```

`CollectionDict` (a `TypedDict` in `collection_widget.py`) describes a single
node.  When constructing dicts for `add_collection()` or `add_request()`,
follow this schema exactly.

**Key rules for the dict schema:**
- Top-level keys are `str(collection.id)` — always strings, never ints.
- `"type"` is always `"folder"` or `"request"` — use these exact strings.
- Requests have a `"method"` key (e.g. `"GET"`); folders do not.
- Folders have a `"children"` dict; requests do not.

### Known issue — ID namespace collision

Collections and requests share the same `children` dict, both keyed by
`str(id)`.  A collection with `id=5` and a request with `id=5` would
collide because they are in different DB tables but the same dict.  Unlikely
with SQLite auto-increment, but be aware of it.

## Signal flow

> **Full signal flow diagrams, signal declaration tables, and MainWindow
> wiring summary are in the `signal-flow` skill.**
> Reference it when wiring new signals or debugging connections.

Key signals to know (always-on summary):

- `CollectionWidget.item_action_triggered(str, int, str)` → opens
  requests/folders in MainWindow (or scripts when `variant="local_scripts"`).
- `MainWindow.local_scripts_widget` — second `CollectionWidget` instance
  (`tree_kind="local_scripts"`) in the left flyout; leaf type `script` opens
  `TabContext.tab_type == "local_script"` with `LocalScriptEditorWidget`
  (wraps `ScriptEditorPane` — same advanced editor as request Scripts tab).
- **Local script module formats:** `LocalScriptModel.module_format` is `esm`
  (``.js`` / ``.ts`` / ``.py`` virtual paths) or `commonjs` (JavaScript-only,
  ``.cjs``). Create via **+ New → JavaScript (CommonJS)**; consume from ESM
  request scripts with `pm.require("local:…/file.cjs")`. CJS bodies are leaf
  modules (no nested `pm.require`, no vendor `require()`). Editor uses
  `CodeEditorWidget._script_module_format` — syntax via Esprima, not ESM rules.
- `CollectionWidget.draft_request_requested()` → opens a new draft
  (unsaved) request tab in MainWindow.
- `CollectionWidget.run_collection_requested(int)` →
  `MainWindow._on_run_collection_by_id` opens/focuses the folder tab on
  **Runs → New run** (inline runner in `FolderEditorWidget`).
- `_RunnerPanel.run_finished()` (internal to folder editor) → host reloads
  run history via `RunHistoryService.get_runs`.
- `_RunnerPanel._collect_requests(collection_id)` walks each root from
  `CollectionService.fetch_all()`, DFS-finds the folder whose `id` matches
  (nested folders are not top-level keys), then depth-first collects all
  descendant `request` nodes for the inline runner checklist.
- `RunnerWorker` builds a single substitution map for each iteration: current
  data-file row (if any), then environment variables; on duplicate keys the
  environment value wins.  That map is applied to URL, headers, and body
  `{{var}}` placeholders before scripts run; `pm.iterationData` still
  reflects the current row for script APIs.
- **Inline data-driven runner (D3):** post-response `ScriptOutputPanel` embeds
  `DataRunnerPanel` (CSV/JSON picker) and an **Iterations** matrix tab.
  `ScriptRunWorker.set_iteration_data()` loops rows on one QThread, emitting
  `iteration_finished(int, ScriptOutput, float)` per row and `finished(list, float)`
  when done.  Shared parsing lives in `services.scripting.data_loader.parse_data_file`
  (also used by the collection runner).  This is single-request inline scope only —
  the folder/collection runner remains separate.
- `NewItemPopup.new_request_clicked()` / `new_collection_clicked()` →
  emitted by the icon grid popup when tiles are clicked.
- `RequestEditorWidget.send_requested()` → triggers HTTP send flow.
- `RequestEditorWidget` lazy-loads the **Body** and **Scripts** heavy editors
  when those tabs are first selected (or via `_ensure_body_editors()` /
  `_ensure_scripts_editors()`). Until then, placeholders (`LazyEditorPlaceholder`)
  are shown; `load_request` / `get_request_data` use `_loaded_request_snapshot`
  when those sections are not materialised yet.
- `ResponseViewerWidget.save_response_requested(dict)` → saves the current live response.
- `ResponseViewerWidget.save_availability_changed(bool)` → refreshes right-sidebar saved-response affordances.
- `ResponseViewerWidget.load_stored_response(dict)` → history/replay display from
  `entry_to_http_response_dict`; clears test/pre-request tabs, disables Save Response,
  does not set `_last_live_response`. `show_loading()` discards stored body when no
  live response is loaded.
- `SavedResponsesPanel` emits `save_current_requested`,
  `rename_requested`, `duplicate_requested`, and `delete_requested` — all
  handled in `MainWindow` through `CollectionService`.
- `ThemeManager.theme_changed()` → widgets refresh dynamic styles, including
  the wrapped request-tab deck chip styling.
- `TabSettingsManager.settings_changed()` → `MainWindow` / `RequestTabBar`
  refresh tab behaviour and label presentation, including switching
  between single-row and wrapped-row layouts.
- `MainWindow` exposes three tab navigation models: **request open history**
  (`back_action` / `forward_action`, Alt+Left/Right — requests opened from
  the collection tree, `_history` in `_TabControllerMixin`); **tab activation
  history** (Go → Back/Forward, `tab_back_action` / `tab_forward_action`,
  Ctrl+Alt+Left/Right — `_TabNavHistoryMixin` in `main_window/tab_nav/`,
  stable `TabContext.nav_token` from `allocate_tab_nav_token()` in
  `tab_manager.py`, in-memory stacks cleared on quit, empty after session
  restore); **cyclic deck** (View → Next/Previous Tab, Ctrl+Tab /
  Ctrl+Shift+Tab). `CodeEditorWidget` uses `Ctrl+P` for parameter-info
  hints when the script editor has focus.  Autocomplete, parameter-hint,
  symbol-doc, and debug-hover popups are **app-wide singletons**
  (`ui/widgets/code_editor/popup_registry.py`); ``CompletionPopup`` signals
  are re-targeted to the active editor on each show.
- `VariablePopup` uses **class-level callbacks**, not signals — wired once
  in `MainWindow.__init__`.

## Unconnected signals

No unconnected signals at this time.

## Implicit contracts

### 1. `init_db()` must precede `MainWindow()`

`MainWindow` creates `CollectionWidget`, whose constructor immediately spawns
a background thread that queries the DB.  If `init_db()` has not been called,
`get_session()` raises `RuntimeError`.

### 2. Session-per-function isolation

Every repository function opens and closes **its own session** via
`get_session()`.  There is no way to batch multiple operations in a single
transaction from the service or UI layer.  Each call auto-commits
independently.

**Exception:** `import_repository.import_collection_tree()` uses a **single
session** for the entire collection tree so import is atomic — if any part
fails, the whole import rolls back.

### 3. ORM objects and detached access

`get_session()` uses `expire_on_commit=False`, so scalar attributes on
returned ORM objects survive session close.  However, **navigating
un-loaded relationships on a detached object raises
`DetachedInstanceError`**.  Both `children` and `requests` use
`lazy="selectin"` to eagerly load one level, but for deeper trees the
repository converts to dicts inside the session (see dict schema above).

### 4. Exception swallowing in `_safe_svc_call`

`CollectionWidget._safe_svc_call` catches **all** exceptions and only logs
them.  Service validation errors (empty names, missing parents) are silently
discarded.

**If you add a new service method**, its errors will be invisible unless you
also add explicit UI feedback (e.g. a `QMessageBox`).  For user-visible
errors, pair the service call with `QMessageBox.warning()` or emit a status
signal instead of relying on `_safe_svc_call`.

### 5. Sort ordering

`set_collections()` sorts **root** collections alphabetically by name.
Children within a folder are **not sorted** — they appear in dict iteration
order (insertion order in Python 3.7+).

### 6. Auth inheritance convention

`auth = None` in the database means "inherit from parent" — the request
or folder walks up its ancestor chain until it finds a folder with an
explicit `auth` dict.  `{"type": "noauth"}` means "no authentication" and
**stops** the inheritance chain.  The UI maps `None` to
`"Inherit auth from parent"` in the auth type combo.

- `_get_auth_data()` returns `None` for inherit, `{"type": "noauth"}` for
  explicit no-auth.
- `_load_auth(None)` / `_load_auth({})` → selects "Inherit auth from parent".
- `get_request_inherited_auth(request_id)` / `get_collection_inherited_auth(collection_id)`
  resolve the effective auth by walking ancestors.

### 7. Saved responses are now split across two UI surfaces

- **Saving** a response remains a response-viewer action.  The live response
  viewer emits `save_response_requested(dict)` only when it has a live
  `HttpResponseDict` loaded.
- **Browsing/managing** saved responses now lives in the right sidebar's
  `SavedResponsesPanel`, alongside Variables and Snippets.
- The panel is fully self-contained: selecting a saved response shows its
  details (headers, body, metadata) inline, with built-in search and filter.
- The old plain-text Saved tab in `ResponseViewerWidget` has been removed.

### 8. Saved response data contract

`CollectionService` now normalizes saved responses into `SavedResponseDict`:

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

`get_saved_responses_for_request()` orders rows newest-first by
`created_at DESC, id DESC`, and `CollectionService` formats `created_at`
into `%Y-%m-%d %H:%M` strings for the UI.

## Repository and service reference

> **Full repository function catalogues, service method tables, TypedDict
> schemas, and response viewer docs are in the `service-repository-reference`
> skill.**  Reference it when adding or modifying repository/service methods.

## Known limitations

1. **No cycle detection for collection moves** — `move_collection` only
   prevents direct self-reference (`id == new_parent_id`).  Moving a parent
   into its own descendant would create an infinite loop.
2. ~~**DELETE method has no colour**~~ — Fixed: `COLOR_DELETE` (`#e67e22`)
   added to `METHOD_COLORS` in `theme.py`.
3. **`request_parameters` and `headers` are `String` columns** — unlike
   `scripts`, `settings`, and `events` (which are JSON columns), these store
   serialised strings.  Consuming code must handle string-to-dict conversion.
4. ~~**Send not implemented**~~ — Fixed: `RequestEditorWidget.send_requested`
   is wired to `MainWindow._on_send_request` which uses `HttpSendWorker` +
   `HttpService.send_request()`.
5. **Navigation history is in-memory only** — request `_history` and tab
   activation stacks (`_tab_nav_back` / `_tab_nav_forward`) are lost on
   restart; open tabs still restore from `TabSettingsManager` session JSON.
6. **`TabContext.local_overrides` are in-memory only** —
   `TabContext` (in `tab_manager.py`) stores per-request variable overrides
   in `local_overrides: dict[str, LocalOverride]`.  These do **not** persist
   to the database.  When the user edits a variable value in
   `VariablePopup` and dismisses the popup without saving, the changed
   value goes into `local_overrides`.  They are merged on top of the
   combined variable map in `MainWindow._refresh_variable_map()` and
   tagged with `is_local=True` in `VariableDetail` so the popup can show
   Update/Reset buttons.  For draft tabs from deleted-request history,
   pass `collection_id=ctx.variable_collection_id` (same as
   `_refresh_sidebar`) so Auth/URL fields resolve collection variables.
7. **`TabContext.draft_name` tracks the display name of unsaved tabs** —
   Set to `"Untitled Request"` when a draft tab is opened.  Updated when
   the user renames via the breadcrumb bar.  Used as fallback label in the
   save-to-collection dialog.  `None` for persisted request tabs.
8. **Request-tab behaviour is settings-driven** — preview tabs, compact
  labels, duplicate-name path suffixes, tab insertion position, wrap
  mode, tab limit, and close-activation policy are read from
  `TabSettingsManager`.
  `RequestTabBar` is a custom wrapped multi-row widget, not a native
  `QTabBar`; it keeps a small compatibility API (`currentIndex()`,
  `setCurrentIndex()`, `count()`, `tabRect()`, `tabButton()`,
  `tabToolTip()`, `select_next_tab()`, `select_previous_tab()`,
  `tab_request_info()`) so `MainWindow` and tests
  do not depend on Qt tab-bar internals.  `MainWindow` enforces the
  limit/promotion policies when opening and closing tabs.
  **Session persistence:** `_TabControllerMixin._persist_open_tabs()` saves
  the current tab list (type + DB id + method + name for requests) and
  active index after every tab open/close/reorder and in `closeEvent`.
  **Environments** tabs are saved as ``{"type": "environments"}`` (no id)
  and recreated on restore in their saved order.
  **Deferred tab materialisation:** `session_restore.begin_session_restore`
  (via delayed `_restore_tabs()`) runs after `CollectionWidget.load_finished`.
  A parallel `SessionPrefetchWorker` bulk-loads request rows, breadcrumbs,
  local scripts, and folder names on a background thread (sync on offscreen
  platform in tests).  All deferred chips (requests, folders, local scripts,
  old-format requests enriched from prefetch) restore in one batched pass with
  `tab_bar.blockSignals(True)` — no 25 ms inter-tab pacing.  Draft tabs
  restore in a single eager batch after chips.  `_materialise_deferred_tab()`
  and `_materialise_deferred_folder_tab()` read the prefetch cache first.
  `_finish_session_restore` activates the saved tab and materialises it when
  deferred.  `_session_prefetch_result` stays available for later tab opens
  until `closeEvent`.
  Draft (unsaved) tabs are serialized with `type: "draft"` and an inline
  snapshot of the editor state (`get_request_data()` + `draft_name`).
  On restore, `_restore_draft()` calls `_open_draft_request()` and
  replays the saved state into the editor.
9. **Manual tab reorder changes close-unchanged priority** — when the user
  drags tabs into a new visible order, `_TabControllerMixin._on_tab_reordered`
  rewrites `TabContext.opened_order` to match that order.  The
  `close_unchanged` limit policy then evicts the leftmost eligible,
  unchanged tab instead of an older pre-drag ordering.
10. **VariablePopup uses class-level callbacks, not Qt signals** —
   `VariablePopup` is a **singleton** `QFrame`.  Its callbacks
   (`set_save_callback`, `set_local_override_callback`,
   `set_reset_local_override_callback`, `set_add_variable_callback`,
   `set_has_environment`) are classmethods that store callables on the
   **class itself**, not on an instance.  They are wired once in
   `MainWindow.__init__` and survive popup hide/show cycles.
11. **Saved response mutations are MainWindow-owned** —
  `SavedResponsesPanel` is a read-only/browser widget.  It never imports the
  repository or service directly for mutations; it only emits signals to
  `MainWindow`, which calls `CollectionService` and then refreshes the
  sidebar state.
12. **Post-response inline Run defaults to live response mode** —
  In `RequestEditorWidget` Scripts → Post-response, `ScriptOutputPanel`
  adds **Mock response** as a tab beside Output and Problems (status,
  editable headers, JSON body editor with folding) and
  defaults to `response_source_mode() == "live"`.  Clicking Run delegates to
  `MainWindow.run_post_response_script_with_live_response()` with
  `editor` set to the **scripts host** (``RequestEditorWidget`` or
  ``FolderEditorWidget`` from ``_ScriptsMixin``), not the nested
  ``CodeEditorWidget``.  The call triggers
  the normal send pipeline, skips request-level script chains for that send,
  maps `HttpResponseDict` to test context fields (`code`, `status`, `headers`,
  `body`, `responseTime`, `responseSize`), then runs only the current
  post-response script in the inline output panel.  Switching to
  `Manual mock response` on that tab keeps the existing offline inline worker path.
  `ScriptOutputPanel(..., host_kind="folder")` (folder/collection scope) omits
  the **Response source** (live) row but still shows **Mock response** (status,
  headers table, JSON body editor) on that tab for `pm.response` in inline runs.
  For test panels, when the mock body field is blank, `get_response_data()` uses ``"{}"`` as the default body
  so `pm.response.json()` does not fail on first use.
