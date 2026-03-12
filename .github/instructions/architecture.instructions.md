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
   Import from `ui.styling.theme_manager`.
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
- `ThemeManager` (`ui.styling.theme_manager`) is created once in `main.py`
  and passed to `MainWindow`.  It owns the app-wide stylesheet, QPalette,
  and QSettings persistence for theme preferences.  See
  `pyside6.instructions.md` for widget styling rules.
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

## Signal flow

> **Full signal flow diagrams, signal declaration tables, and MainWindow
> wiring summary are in the `signal-flow` skill.**
> Reference it when wiring new signals or debugging connections.

Key signals to know (always-on summary):

- `CollectionWidget.item_action_triggered(str, int, str)` → opens
  requests/folders in MainWindow.
- `CollectionWidget.draft_request_requested()` → opens a new draft
  (unsaved) request tab in MainWindow.
- `NewItemPopup.new_request_clicked()` / `new_collection_clicked()` →
  emitted by the icon grid popup when tiles are clicked.
- `RequestEditorWidget.send_requested()` → triggers HTTP send flow.
- `ResponseViewerWidget.save_response_requested(dict)` → saves the current live response.
- `ResponseViewerWidget.save_availability_changed(bool)` → refreshes right-sidebar saved-response affordances.
- `SavedResponsesPanel` emits `save_current_requested`,
  `rename_requested`, `duplicate_requested`, and `delete_requested` — all
  handled in `MainWindow` through `CollectionService`.
- `ThemeManager.theme_changed()` → widgets refresh dynamic styles.
- `VariablePopup` uses **class-level callbacks**, not signals — wired once
  in `MainWindow.__init__`.

## Unconnected signals

| Signal / Feature | Location | Status |
|---|---|---|
| `MainWindow.run_action` | `main_window/window.py` | QAction created, not connected |

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
8. **VariablePopup uses class-level callbacks, not Qt signals** —
   `VariablePopup` is a **singleton** `QFrame`.  Its callbacks
   (`set_save_callback`, `set_local_override_callback`,
   `set_reset_local_override_callback`, `set_add_variable_callback`,
   `set_has_environment`) are classmethods that store callables on the
   **class itself**, not on an instance.  They are wired once in
   `MainWindow.__init__` and survive popup hide/show cycles.
  9. **Saved response mutations are MainWindow-owned** —
    `SavedResponsesPanel` is a read-only/browser widget.  It never imports the
    repository or service directly for mutations; it only emits signals to
    `MainWindow`, which calls `CollectionService` and then refreshes the
    sidebar state.
