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
  MainWindow → HttpSendWorker (QThread) → HttpService.send_request()
    → HttpSendWorker.finished(HttpResponseDict) → ResponseViewerWidget.load_response()

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
- `RunHistoryService` follows the same `@staticmethod` pattern.  It wraps
  `run_history_repository` for run history CRUD (create, finish, add result,
  query runs/results, delete).
- `ScriptService` and `ScriptEngine` also follow the `@staticmethod`
  pattern.  `ScriptService.build_script_chain(request_id)` walks the
  ancestor chain to collect inherited scripts.  `ScriptEngine` dispatches
  to `DenoRuntime` for **JavaScript** and **TypeScript** (``deno run`` +
  `data/scripts/deno_drain.mjs` for ``pm.sendRequest`` IPC; TypeScript uses a
  ``bundle.ts`` temp file so Deno strips types) or `PyRuntime` (Pyodide under Deno when
  :file:`data/scripts/vendor_pyodide/` is present, otherwise RestrictedPython
  subprocess via :file:`_py_sandbox.py`).
  :class:`JSRuntime` delegates execution to :class:`DenoRuntime` and provides
  bootstrap and vendor file loaders.  JavaScript parse for the linter and
  gutter uses Esprima via :mod:`esprima_deno` (Deno subprocess;
  :file:`data/scripts/esprima_parse.mjs`); **TypeScript** skips Esprima lint until a TS parser exists.
  `RuntimeSettings` (``scripting/deno_path``, ``scripting/python_path`` in
  QSettings) resolves/validates executables.  TypedDicts (`ScriptInput`, `ScriptOutput`, `TestResult`,
  `ConsoleLog`, `ScriptEntry`) live in `services/scripting/__init__.py`.
  `find_pm_tests(source, language)` in `engine.py` locates `pm.test("name", …)`
  call sites (Python AST or JavaScript/TypeScript esprima when parseable, with regex fallback) for the
  per-test script gutter.  `find_top_level_statement_lines(source, language)`
  returns 0-based top-level statement lines (where the step-debugger can pause);
  the post-response editor uses it to render unreachable breakpoints with a
  muted style.  `ScriptLinter._esprima_parse_result()` shares the
  same esprima JSON round-trip as the linter.
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
  `DebugProtocol` is a thread-safe state machine that coordinates
  pause/resume between the worker thread and the UI.
  `js_debug.debug_execute` delegates to `deno_debug.debug_execute`, which
  runs Deno with ``--inspect-brk``, drives the V8 debugger over CDP
  (WebSocket), sets breakpoints, and steps with
  `Runtime.evaluate` / `protocol.checkpoint()`.  `inject_checkpoints` and
  `js_debug` group splitting prepare statement boundaries for the inspector.
  `py_debug.debug_execute` launches a subprocess with `sys.settrace` and
  uses IPC for pause/resume.
  `engine.run_debug_chain` mirrors `_run_chain` but routes through debug
  dispatch.  TypedDicts: `DebugPauseInfo`, enums: `DebugState`, `StepMode`.
  On pause, Python `debugPause` includes a `pm.response` string in
  `locals` (built from the sandbox `pm` object).  JS variable reads merge
  `pm.response` fields into the `pm` map for the debug variables panel
  (`js_debug._READ_JS_DEBUG_VARS`).  Deno/CDP pauses extend
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
  wraps the user script in ``function __pm_debugUserScript() { … }`` so
  ``const``/``let`` bind under a ``local`` CDP scope instead of sharing the
  bundle ``module`` record with polyfills.  While paused in
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
  ``deno_scope._collect_call_frame_scopes`` walks CDP ``scopeChain``; for
  ``module`` bindings named ``pm`` or ``console`` it issues nested
  ``Runtime.getProperties`` so the inspector and merged hover locals receive
  JSON-like dicts instead of the RemoteObject description string ``Object``.
  Deno binds ``Debugger.setBreakpointByUrl`` at the union of top-level group
  starts (``js_debug._split_into_groups``) and ``DebugProtocol`` editor lines
  (``deno_debug._cdp_break_editor_lines``); pauses mapped into the user-script
  line range call ``checkpoint`` so breakpoints inside nested callbacks (e.g.
  ``pm.test`` bodies) work.  Changing breakpoints while a Deno session is
  paused does not push new CDP breakpoints until the next debug run.

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
  requests/folders in MainWindow.
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
- `NewItemPopup.new_request_clicked()` / `new_collection_clicked()` →
  emitted by the icon grid popup when tiles are clicked.
- `RequestEditorWidget.send_requested()` → triggers HTTP send flow.
- `ResponseViewerWidget.save_response_requested(dict)` → saves the current live response.
- `ResponseViewerWidget.save_availability_changed(bool)` → refreshes right-sidebar saved-response affordances.
- `SavedResponsesPanel` emits `save_current_requested`,
  `rename_requested`, `duplicate_requested`, and `delete_requested` — all
  handled in `MainWindow` through `CollectionService`.
- `ThemeManager.theme_changed()` → widgets refresh dynamic styles, including
  the wrapped request-tab deck chip styling.
- `TabSettingsManager.settings_changed()` → `MainWindow` / `RequestTabBar`
  refresh tab behaviour and label presentation, including switching
  between single-row and wrapped-row layouts.
- `MainWindow` View menu exposes `Next Tab` (`Ctrl+Tab`, `Ctrl+PgDown`)
  and `Previous Tab` (`Ctrl+Shift+Tab`, `Ctrl+PgUp`) so the wrapped deck
  keeps editor-style keyboard navigation even though it is no longer a
  native `QTabBar`. `CodeEditorWidget` uses `Ctrl+P` for parameter-info
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
5. **Navigation history is in-memory only** — back/forward stack in
   `MainWindow` is lost on restart.
6. **`TabContext.local_overrides` are in-memory only** —
   `TabContext` (in `tab_manager.py`) stores per-request variable overrides
   in `local_overrides: dict[str, LocalOverride]`.  These do **not** persist
   to the database.  When the user edits a variable value in
   `VariablePopup` and dismisses the popup without saving, the changed
   value goes into `local_overrides`.  They are merged on top of the
   combined variable map in `MainWindow._refresh_variable_map()` and
   tagged with `is_local=True` in `VariableDetail` so the popup can show
   Update/Reset buttons.
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
  **Deferred tab materialisation:** `_restore_tabs()` restores tabs
  lazily after `CollectionWidget.load_finished` fires.  Request tabs
  with `method` and `name` in the session data are created as
  lightweight tab-bar chips stored in `_deferred_tabs`; the editor and
  viewer widgets are built on first selection via
  `_materialise_deferred_tab()`.  Old-format entries (without
  `method`/`name`) fall back to eager `_open_request()` for backward
  compatibility.  Deleted requests/collections are silently skipped.
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
  defaults to `response_source_mode() == "live"`.  Clicking Run delegates to
  `MainWindow.run_post_response_script_with_live_response()` with
  `editor` set to the **scripts host** (``RequestEditorWidget`` or
  ``FolderEditorWidget`` from ``_ScriptsMixin``), not the nested
  ``CodeEditorWidget``.  The call triggers
  the normal send pipeline, skips request-level script chains for that send,
  maps `HttpResponseDict` to test context fields (`code`, `status`, `headers`,
  `body`, `responseTime`, `responseSize`), then runs only the current
  post-response script in the inline output panel.  Switching to
  `Manual mock response` keeps the existing offline inline worker path.
  `ScriptOutputPanel(..., host_kind="folder")` (folder/collection scope) omits
  the **Response source** (live) row but still shows **Mock response** (status
  + body) for `pm.response` in inline runs.  For test panels, when the mock
  body field is blank, `get_response_data()` uses ``"{}"`` as the default body
  so `pm.response.json()` does not fail on first use.
