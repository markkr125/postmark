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
3. **Every repository function is its own transaction.** You cannot batch
   multiple calls into one commit.
4. **Always wrap programmatic tree-item edits in `blockSignals(True/False)`**
   — see `pyside6.instructions.md`.
5. **The data interchange format is a nested `dict[str, Any]`**, not ORM
   objects.  See the schema below.
6. **`_safe_svc_call` swallows all exceptions.**  Errors are logged but never
   shown to the user.
7. **`CollectionService` methods are all `@staticmethod`.**  Do not add
   instance state.

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
```

- **DO NOT** import from `database/` in any UI file.  The service layer is
  the only bridge between UI and repository.
- `CollectionService` is instantiated as `self._svc = CollectionService()` in
  `CollectionWidget.__init__`, but **every method is `@staticmethod`**.
  Do not add instance state without updating every call site.

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

### Selected-collection flow

```
CollectionTree.currentItemChanged
  → _on_current_item_changed
    → selected_collection_changed(collection_id | None)
      → CollectionWidget → CollectionHeader.set_selected_collection_id
        → enables / disables "New request" action in + menu
```

## Unconnected signals and unimplemented features

These signals exist in the code but are **not yet wired to anything**.
**Do not remove them** — they are intentional extension points for future
features.

| Signal / Feature | Location | Status |
|---|---|---|
| `CollectionHeader.import_requested()` | `collection_header.py` | Emitted on click, not connected — import not implemented |
| `MainWindow.run_action` | `main_window.py` | QAction created, not connected |
| `CollectionWidget.item_name_changed` | `collection_widget.py` | Forwarded from tree, nothing connects in MainWindow |
| Response viewer pane | `main_window.py` | Placeholder `QWidget` |
| `RequestEditorWidget.send_requested` | `request_editor.py` | Emitted on Send click, not connected — send not implemented |

### Recently wired signals (no longer unconnected)

| Signal / Feature | Wired in |
|---|---|
| `CollectionHeader.search_changed(str)` | `CollectionWidget` → `CollectionTree.filter_items` |
| `CollectionHeader.new_request_requested(object)` | Emitted from header + menu when collection selected |
| `CollectionWidget.item_action_triggered` | `MainWindow._on_item_action` (opens request editor) |
| Request editor pane | `RequestEditorWidget` — display-only, loaded via `MainWindow._open_request` |
| `CollectionTree.selected_collection_changed` | `CollectionWidget` → `CollectionHeader.set_selected_collection_id` |

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

## Known limitations

1. **No cycle detection for collection moves** — `move_collection` only
   prevents direct self-reference (`id == new_parent_id`).  Moving a parent
   into its own descendant would create an infinite loop.
2. ~~**DELETE method has no colour**~~ — Fixed: `COLOR_DELETE` (`#e67e22`)
   added to `METHOD_COLORS` in `theme.py`.
3. **`request_parameters` and `headers` are `String` columns** — unlike
   `scripts`, `settings`, and `events` (which are JSON columns), these store
   serialised strings.  Consuming code must handle string-to-dict conversion.
4. **Send / import not implemented** — `RequestEditorWidget.send_requested`
   and `CollectionHeader.import_requested` signals are emitted but not
   connected to any backend logic.
5. **Navigation history is in-memory only** — back/forward stack in
   `MainWindow` is lost on restart.
