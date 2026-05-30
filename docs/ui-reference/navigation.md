# Navigation

Tab bar, breadcrumb path, and tab state management.

Source: `src/ui/request/navigation/`

## TabManager and TabContext

`TabContext` bundles all per-tab state into a single object stored in
`MainWindow._tabs[index]`.

### TabContext Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `tab_type` | `str` | `"request"`, `"folder"`, or `"environments"` |
| `request_id` | `int \| None` | Database PK (None for drafts / non-request tabs) |
| `collection_id` | `int \| None` | Parent collection (folder tabs) |
| `editor` | `RequestEditorWidget \| None` | Request editor (request tabs); `None` for environments |
| `folder_editor` | `FolderEditorWidget \| None` | Folder editor (folder tabs) |
| `environment_editor` | `EnvironmentEditorWidget \| None` | Global environments editor (environments tab) |
| `response_viewer` | `ResponseViewerWidget \| None` | Response pane; `None` for environments |
| `thread` | `QThread \| None` | Current HTTP send thread |
| `worker` | `HttpSendWorker \| None` | Current send worker |
| `is_dirty` | `bool` | Unsaved changes flag |
| `is_sending` | `bool` | HTTP request in flight |
| `is_debugging` | `bool` | Inline script debug session active on this tab |
| `is_preview` | `bool` | Preview mode (italic tab label) |
| `draft_name` | `str \| None` | Label for unsaved draft tabs |
| `local_overrides` | `dict[str, LocalOverride]` | Per-tab variable overrides |
| `opened_order` | `int` | Creation sequence number |
| `last_activated_order` | `int` | Last activation sequence number |

### Methods

| Method | Description |
|--------|-------------|
| `require_editor()` | Return the request editor; raises when ``editor`` is absent (environments tab) |
| `require_response_viewer()` | Return the response viewer; raises when ``response_viewer`` is absent |
| `cleanup_thread()` | Quit, wait, and delete the worker thread |
| `dispose()` | Release all resources before deletion |

## RequestTabBar

Multi-row wrapped tab deck replacing `QTabBar`.

Source: `src/ui/request/navigation/request_tabs/`

### Layout

Each tab is a `TabButton` containing a `TabLabel` (request) or
`FolderTabLabel` (folder and **Environments**).  Tabs wrap to multiple rows when space
is tight.  Vertical mouse-wheel scrolling moves between rows.

```
+------+-----------+  +------+-----------+  +-----------+
| GET  | Users     |  | POST | Login     |  | + New Tab |
+------+-----------+  +------+-----------+  +-----------+
+------+-----------+  +------+-----------+
| PUT  | Profile   |  | DEL  | Session   |
+------+-----------+  +------+-----------+
```

### Tab Label Variants

| Class | Usage | Layout |
|-------|-------|--------|
| `TabLabel` | Request tabs | Method badge + request name |
| `FolderTabLabel` | Folder + Environments tabs | Folder: italic **Folder** + name; Environments: chip label |

Layout modes: STANDARD_LAYOUT (30px) and COMPACT_LAYOUT (26px),
controlled by `TabSettingsManager.small_labels`.

### Visual States

| State | Indicator |
|-------|-----------|
| Selected | Coloured background + accent bottom border |
| Preview | Italic tab label |
| Dirty | Bullet (•) before name |
| Sending | Spinner/activity indicator |
| Debugging | Trailing red bug icon (vertically centred with label text) + accent chip border (left accent when unselected) |

Set via ``RequestTabBar.update_tab(..., is_debugging=...)`` when
``ScriptEditorPane.debug()`` pins a host and cleared in ``end_debug_ui``.

### Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `currentChanged` | `int` | Active tab switched |
| `tabCloseRequested` | `int` | Close button clicked |
| `tab_double_clicked` | `int` | Tab double-clicked |
| `new_tab_requested` | *(none)* | New blank tab |
| `close_others_requested` | `int` | Close all except given |
| `close_all_requested` | *(none)* | Close all tabs |
| `force_close_all_requested` | *(none)* | Force-close all |
| `tab_reordered` | `int, int` | Drag-reorder indices |

### Key Methods

| Method | Description |
|--------|-------------|
| `add_request_tab(method, name, path, index)` | Add request tab chip |
| `add_folder_tab(name, index)` | Add folder tab chip (italic) |
| `add_environments_tab(name, index)` | Add global environments editor tab chip |
| `update_tab(index, is_preview, is_sending, is_dirty, is_debugging)` | Refresh visual state |

## TabButton

Individual tab chip with close button.  Supports click, double-click,
right-click context menu, and drag-reorder.

## BreadcrumbBar

Path navigation bar showing the location of the active request.

```
Root Collection / Subfolder / Request Name
```

Non-last segments are clickable (navigate to parent).  The last
segment is editable via double-click for inline rename.

### Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `item_clicked` | `str, int` | Non-last segment clicked |
| `last_segment_renamed` | `str` | Final segment renamed |

### Key Methods

| Method | Description |
|--------|-------------|
| `set_path(segments)` | Update breadcrumb from path data |
