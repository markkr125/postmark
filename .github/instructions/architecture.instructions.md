---
name: "Architecture & Data Flow"
description: "Signal wiring, data schemas, implicit contracts, and known limitations"
applyTo: "src/**/*.py"
---

# Architecture and data flow

This file documents how data moves between layers, how signals are wired,
and what implicit contracts exist.

## Quick rules — read these first

1. **UI must never import from `database/`.**  Go through the service layer.
2. **Call `init_db()` before creating `MainWindow`** — the constructor
   immediately starts a background DB query.
3. **Create `ThemeManager(app)` before creating `MainWindow`** — it applies
   the global stylesheet, QPalette, and widget style on construction.
4. **Every repository function is its own transaction.** You cannot batch
   multiple calls into one commit.
5. **Always wrap programmatic tree-item edits in `blockSignals(True/False)`**
   — see `pyside6.instructions.md`.
6. **The data interchange format is a nested `dict[str, Any]`**, not ORM
   objects.  See the schema below.
7. **`_safe_svc_call` swallows all exceptions.**  Errors are logged but never
   shown to the user.
8. **`CollectionService` methods are all `@staticmethod`.**  Do not add
   instance state.
9. **Never call `setStyleSheet()` for static widget styling** — use
   `setObjectName()` and global QSS.  See `pyside6.instructions.md`.
10. **Never use `# type: ignore` to assign `None` to a non-optional
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

RequestEditorWidget  ──send_requested──►  MainWindow
  MainWindow → HttpSendWorker (QThread) → HttpService.send_request()
    → HttpSendWorker.finished(HttpResponseDict) → ResponseViewerWidget.load_response()

RequestEditorWidget  ──_on_fetch_schema──►  SchemaFetchWorker (QThread)
  → GraphQLSchemaService.fetch_schema() → SchemaFetchWorker.finished()
```

- **DO NOT** import from `database/` in any UI file.  The service layer is
  the only bridge between UI and repository.
- `ThemeManager` is created once in `main.py` and passed to `MainWindow`.
  It owns the app-wide stylesheet, QPalette, and QSettings persistence for
  theme preferences.  See `pyside6.instructions.md` for widget styling rules.
- `CollectionService` is instantiated as `self._svc = CollectionService()` in
  `CollectionWidget.__init__`, but **every method is `@staticmethod`**.
  Do not add instance state without updating every call site.
- `EnvironmentService`, `HttpService`, `GraphQLSchemaService`, and
  `SnippetGenerator` follow the same `@staticmethod` pattern.

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

## Signal flow — complete map

### Create operations

```
Header "+" menu
  → CollectionHeader.new_collection_requested(None)
    → CollectionWidget._create_new_collection(parent_id=None)

Tree context menu → "Add folder"
  → CollectionTree.new_collection_requested(parent_id)
    → CollectionWidget._create_new_collection(parent_id)

Tree context menu → "Add request"  /  Placeholder "Add a request" link
  → CollectionTree.new_request_requested(parent_collection_id)
    → CollectionWidget._create_new_request(parent_collection_id)
```

### Rename operations

```
Tree context menu → "Rename" (folder)
  → CollectionTree._rename_folder() → Qt's editItem() inline editor
  → itemChanged signal → _on_item_changed()
    → CollectionTree.collection_rename_requested(id, new_name)
      → CollectionWidget._on_collection_rename(id, new_name)
        → CollectionService.rename_collection(id, new_name)

Tree context menu → "Rename" (request)
  → CollectionTree._rename_request() → manual QLineEdit injection
  → returnPressed / editingFinished → _finish_request_rename()
    → CollectionTree.request_rename_requested(id, new_name)
      → CollectionWidget._on_request_rename(id, new_name)
        → CollectionService.rename_request(id, new_name)
```

### Delete operations

```
Tree context menu → "Delete"
  → Confirmation QMessageBox
    → CollectionTree.collection_delete_requested(id)
        or request_delete_requested(id)
      → CollectionWidget._on_collection_delete / _on_request_delete
        → CollectionService.delete_collection / delete_request
  → CollectionTree.remove_item(id, type)  (immediate visual removal)
```

### Drag-and-drop

```
DraggableTreeWidget.dropEvent() validates the drop, then:
  → DraggableTreeWidget.request_moved(request_id, new_collection_id)
    → forwarded through CollectionTree.request_moved
      → CollectionWidget._on_request_moved
        → CollectionService.move_request(id, new_collection_id)

  → DraggableTreeWidget.collection_moved(collection_id, new_parent_id)
    → forwarded through CollectionTree.collection_moved
      → CollectionWidget._on_collection_moved
        → CollectionService.move_collection(id, new_parent_id)
```

### Initial data loading

```
CollectionWidget.__init__()
  → _start_fetch()
    → QThread + _CollectionFetcher (worker with moveToThread)
      → CollectionService.fetch_all()  (runs on worker thread)
      → _CollectionFetcher.finished(dict)  (cross-thread signal)
        → CollectionWidget._on_collections_ready(dict)
          → CollectionTree.set_collections(dict)
```

### Search / filter

```
CollectionHeader.search_bar (QLineEdit) textChanged
  → CollectionHeader.search_changed(str)
    → CollectionWidget._on_search_changed(str)
      → CollectionTree.filter_items(str)
        → _filter_recursive per top-level item (hide non-matches)
        → _update_stack_visibility (show empty-state when all hidden)
```

### Double-click open & keyboard shortcuts

```
CollectionTree.itemDoubleClicked (request item)
  → _on_item_double_clicked
    → item_action_triggered("request", id, "Open")

eventFilter on tree_widget:
  F2  → _start_rename on selected item
  Del → _delete_item on selected item
```

### Request open & navigation

```
CollectionWidget.item_action_triggered("request", id, "Open")
  → MainWindow._on_item_action
    → _open_request(id)
      → CollectionService.get_request(id) → dict
      → RequestEditorWidget.load_request(dict)
      → _history append + _update_nav_actions

MainWindow back_action / forward_action
  → _navigate_back / _navigate_forward
    → _open_request(history[index])
```

### Import operations

```
CollectionHeader "Import" button click
  → CollectionHeader.import_requested()
    → CollectionWidget._on_import_requested()
      → ImportDialog(parent=self)
        → ImportDialog.import_completed → CollectionWidget._start_fetch

MainWindow File → Import (Ctrl+I)
  → MainWindow._on_import()
    → ImportDialog(parent=self)
      → ImportDialog.import_completed → CollectionWidget._start_fetch

ImportDialog internally:
  paste / file-drop / folder-select
    → _ImportWorker (QObject on QThread)
      → ImportService.import_files / import_folder / import_text
        → parser layer → import_repository → DB
      → _ImportWorker.finished(ImportSummary)
        → ImportDialog._on_import_finished → update log + emit import_completed
```

### Selected-collection flow

```
CollectionTree.currentItemChanged
  → _on_current_item_changed
    → selected_collection_changed(collection_id | None)
      → CollectionWidget → CollectionHeader.set_selected_collection_id
        → enables / disables "New request" action in + menu
```

### Send request flow

```
RequestEditorWidget.send_requested
  → MainWindow._on_send_request()
    → HttpSendWorker.set_request(method, url, headers, body, auth, settings)
    → QThread.started → HttpSendWorker.run()
      → EnvironmentService.substitute() (variable replacement)
      → HttpService.send_request() (httpx + timing/network/size)
      → HttpSendWorker.finished(HttpResponseDict)
        → MainWindow._on_response_ready(data)
          → ResponseViewerWidget.load_response(data)
    → HttpSendWorker.error(str)
        → ResponseViewerWidget.show_error(message)
```

### GraphQL schema fetch flow

```
RequestEditorWidget._on_fetch_schema()
  → SchemaFetchWorker.set_endpoint(url, headers)
  → QThread.started → SchemaFetchWorker.run()
    → GraphQLSchemaService.fetch_schema(url, headers)
    → SchemaFetchWorker.finished(SchemaResultDict)
      → RequestEditorWidget._on_schema_ready(result)
```

## Unconnected signals and unimplemented features

These signals exist in the code but are **not yet wired to anything**.
**Do not remove them** — they are intentional extension points for future
features.

| Signal / Feature | Location | Status |
|---|---|---|
| `MainWindow.run_action` | `main_window.py` | QAction created, not connected |

All other signals documented in the "Signal flow" section above are
fully wired and working.  If a signal appears in the flow diagrams, it
is connected — do not disconnect or re-wire it.

### Variable popup flow

```
VariableLineEdit.mouseMoveEvent (cursor over {{variable}})
  → 150ms QTimer delay
    → VariablePopup.show_variable(name, detail, anchor_rect)
      → displays value, source badge, edit field

VariablePopup "Save" (resolved variable)
  → _save_callback(source, source_id, name, new_value)
    → MainWindow._on_variable_updated
      → EnvironmentService.update_variable_value()
      → clear local override if any
      → _refresh_variable_map()

VariablePopup "Update" (local override)
  → _save_callback(original_source, original_source_id, name, local_value)
    → MainWindow._on_variable_updated (same path as Save)

VariablePopup "Reset" (local override)
  → _reset_local_override_callback(name)
    → MainWindow._on_reset_local_override
      → remove from TabContext.local_overrides
      → _refresh_variable_map()

VariablePopup close (value changed, not saved)
  → _local_override_callback(name, value, source, source_id)
    → MainWindow._on_local_variable_override
      → store in TabContext.local_overrides
      → _refresh_variable_map()

VariablePopup "Add to" (unresolved variable)
  → _add_variable_callback(target, target_id, name, value)
    → MainWindow._on_add_unresolved_variable
      → EnvironmentService.add_variable()
      → _refresh_variable_map()
```

### Variable map refresh

```
MainWindow._refresh_variable_map()
  → EnvironmentService.build_combined_variable_detail_map(env_id, request_id)
  → merge TabContext.local_overrides on top
  → set VariableDetail.is_local = True for overridden keys
  → request_editor.set_variable_map(merged)
    → VariableLineEdit widgets repaint with updated colours
```

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
also add explicit UI feedback (e.g. a `QMessageBox`).

### 5. Sort ordering

`set_collections()` sorts **root** collections alphabetically by name.
Children within a folder are **not sorted** — they appear in dict iteration
order (insertion order in Python 3.7+).

## Repository function catalogue

| Function | Returns | Purpose |
|----------|---------|---------|
| `fetch_all_collections()` | `dict[str, Any]` | All root collections as nested dict |
| `create_new_collection(name, parent_id?)` | `CollectionModel` | Create a folder |
| `rename_collection(collection_id, new_name)` | `None` | Update name |
| `delete_collection(collection_id)` | `None` | Delete + cascade children and requests |
| `get_collection_by_id(collection_id)` | `CollectionModel \| None` | PK lookup |
| `create_new_request(collection_id, method, url, name, ...)` | `RequestModel` | Create a request |
| `rename_request(request_id, new_name)` | `None` | Update name |
| `delete_request(request_id)` | `None` | Delete a single request |
| `update_request_collection(request_id, new_collection_id)` | `None` | Move request |
| `update_collection_parent(collection_id, new_parent_id)` | `None` | Move collection |
| `get_request_by_id(request_id)` | `RequestModel \| None` | PK lookup |
| `get_request_auth_chain(request_id)` | `dict[str, Any] \| None` | Walk parent chain for auth config |
| `get_request_variable_chain(request_id)` | `dict[str, str]` | Collect variables up the parent chain |
| `get_request_variable_chain_detailed(request_id)` | `dict[str, tuple[str, int]]` | Variables with source collection IDs |
| `get_request_breadcrumb(request_id)` | `list[dict[str, Any]]` | Ancestor path for breadcrumb bar |
| `get_collection_breadcrumb(collection_id)` | `list[dict[str, Any]]` | Ancestor path for collection breadcrumb |
| `get_saved_responses_for_request(request_id)` | `list[dict[str, Any]]` | Saved responses for a request |
| `save_response(request_id, ...)` | `SavedResponseModel` | Persist a response snapshot |
| `update_collection(collection_id, **fields)` | `None` | Generic field update on a collection |
| `update_request(request_id, **fields)` | `None` | Generic field update on a request |
| `count_collection_requests(collection_id)` | `int` | Total request count in folder subtree |
| `get_recent_requests_for_collection(collection_id, ...)` | `list[dict[str, Any]]` | Recently modified requests in subtree |
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

## Service method catalogue

All methods are `@staticmethod` on `CollectionService`.  "Passthrough" means
the method delegates directly to the repository with no added logic.

| Method | Validation added over repository |
|--------|----------------------------------|
| `fetch_all()` | Logging only |
| `get_collection(id)` | Passthrough |
| `get_request(id)` | Passthrough |
| `create_collection(name, parent_id?)` | `name.strip()`, rejects empty |
| `rename_collection(id, new_name)` | `new_name.strip()`, rejects empty |
| `delete_collection(id)` | Logging only |
| `move_collection(id, new_parent_id)` | Rejects `id == new_parent_id` (no deeper cycle check) |
| `create_request(collection_id, method, url, name, ...)` | `name.strip()`, `method.upper()`, rejects empty |
| `rename_request(id, new_name)` | `new_name.strip()`, rejects empty |
| `delete_request(id)` | Logging only |
| `move_request(id, new_collection_id)` | Passthrough |
| `update_collection(id, **fields)` | Passthrough (generic field update) |
| `update_request(id, **fields)` | Passthrough (generic field update) |
| `get_request_auth_chain(request_id)` | Passthrough |
| `get_request_variable_chain(request_id)` | Passthrough |
| `get_request_breadcrumb(request_id)` | Passthrough |
| `get_collection_breadcrumb(collection_id)` | Passthrough |
| `get_folder_request_count(collection_id)` | Passthrough |
| `get_recent_requests(collection_id, ...)` | Passthrough |
| `get_saved_responses(request_id)` | Passthrough |
| `save_response(request_id, ...)` | Passthrough |

### Import service (`ImportService`)

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

### HTTP service (`HttpService`)

All methods are `@staticmethod`.  `send_request()` uses `httpx` with event
hooks to capture timing, and inspects the connection for TLS/network data.
Returns an `HttpResponseDict` containing the response body, headers, status,
timing breakdown, network metadata, and size information.

**TypedDict schemas (defined in `services/http_service.py`):**

```python
class TimingDict(TypedDict):
    dns_ms: float
    connect_ms: float
    tls_ms: float
    send_ms: float
    wait_ms: float
    receive_ms: float
    total_ms: float

class NetworkDict(TypedDict):
    remote_ip: str
    remote_port: int
    protocol: str
    tls_version: str | None
    tls_cipher: str | None
    tls_cert_issuer: str | None
    tls_cert_subject: str | None
    tls_cert_expiry: str | None

class HttpResponseDict(TypedDict):
    status_code: int
    status_text: str
    headers: dict[str, str]
    cookies: dict[str, str]
    body: str
    raw_body: bytes
    timing: TimingDict
    network: NetworkDict
    size_request_headers: int
    size_request_body: int
    size_response_headers: int
    size_response_body: int
```

### Environment service (`EnvironmentService`)

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

**TypedDict schemas (defined in `services/environment_service.py`):**

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

### GraphQL schema service (`GraphQLSchemaService`)

All methods are `@staticmethod`.  Sends an introspection query to a GraphQL
endpoint and parses the schema into a structured result.

| Method | Purpose |
|--------|---------|
| `fetch_schema(url, headers)` | Introspect endpoint, return `SchemaResultDict` |
| `_parse_schema(schema_data)` | Convert raw introspection JSON to structured types |
| `format_schema_summary(result)` | Human-readable schema summary text |

### Snippet generator (`SnippetGenerator`)

All methods are `@staticmethod`.  Generates code snippets for a given request
in multiple languages.

| Method | Purpose |
|--------|---------|
| `curl(method, url, headers, body)` | cURL command |
| `python_requests(method, url, headers, body)` | Python requests library |
| `javascript_fetch(method, url, headers, body)` | JavaScript fetch API |
| `available_languages()` | List of supported language names |
| `generate(language, method, url, headers, body)` | Dispatch to language-specific generator |

## Response viewer and popup system

`ResponseViewerWidget` displays the HTTP response with four tabs:
Body, Headers, Cookies, and Saved.

### Body tab structure

- **Format toolbar** — Pretty/Raw/Preview combo, Beautify button, stretch
- **`CodeEditorWidget`** — `QPlainTextEdit` subclass (read-only) with
  Pygments syntax highlighting, line numbers, fold gutter, word wrap, and
  built-in search (Ctrl+F)
- **Search bar** — hidden by default, toggled via Ctrl+F or toolbar button

### Status bar (below tabs)

Four clickable labels show response metadata. Each opens an `InfoPopup`
subclass:

| Label | Popup | Data source |
|-------|-------|-------------|
| Status code + text | `StatusPopup` | `status_code`, `status_text` |
| Response time | `TimingPopup` | `TimingDict` |
| Response size | `SizePopup` | `size_*` fields + `TimingDict` |
| Network info | `NetworkPopup` | `NetworkDict` |

### InfoPopup base class (`ui/info_popup.py`)

`InfoPopup(QFrame)` provides the shared popup infrastructure:

- **Window flags:** `Tool | FramelessWindowHint | WindowStaysOnTopHint`
- **Positioning:** `show_below(anchor)` places the popup below the anchor
  widget, adjusting for screen edges
- **Dismiss:** App-wide event filter closes on click-outside (returns
  `False` to propagate the click), Escape key, or window move/resize
- **Copy helper:** `_make_header_with_copy(title)` returns a header row with
  a copy button; `_copy_to_clipboard(text, btn)` copies text and shows
  "Copied!" feedback for 1.2s via QTimer
- **Text selectability:** `show_below()` automatically sets
  `TextSelectableByMouse` on all child `QLabel` widgets

`ClickableLabel(QLabel)` emits a `clicked` signal on `mousePressEvent`,
used for the status bar labels.

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
7. **VariablePopup uses class-level callbacks, not Qt signals** —
   `VariablePopup` is a **singleton** `QFrame`.  Its callbacks
   (`set_save_callback`, `set_local_override_callback`,
   `set_reset_local_override_callback`, `set_add_variable_callback`,
   `set_has_environment`) are classmethods that store callables on the
   **class itself**, not on an instance.  They are wired once in
   `MainWindow.__init__` and survive popup hide/show cycles.
