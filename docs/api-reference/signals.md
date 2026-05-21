# Signals Reference

Complete catalogue of all PySide6 `Signal` declarations grouped by
subsystem.  ~80 custom signals across the codebase.

## Collection Tree

### CollectionTree

Source: `ui/collections/tree/collection_tree.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `item_action_triggered` | `str, int, str` | Action type, item ID, value |
| `item_name_changed` | `str, int, str` | Item type, item ID, new name |
| `collection_rename_requested` | `int, str` | Collection ID, new name |
| `collection_delete_requested` | `int` | Collection ID |
| `request_rename_requested` | `int, str` | Request ID, new name |
| `script_rename_requested` | `int, str, str, str` | Local script ID, basename, language, module_format (`esm` \| `commonjs`) |
| `new_script_clicked` (popup) | `str, str` | Language code, module_format |
| `new_script_requested` (header) | `object, str, str` | Parent folder ID or `None`, language, module_format |
| `request_delete_requested` | `int` | Request ID |
| `request_moved` | `int, int` | Request ID, new collection ID |
| `collection_moved` | `int, object` | Collection ID, new parent ID (int or None) |
| `new_collection_requested` | `object` | Parent ID (int or None) |
| `new_request_requested` | `object` | Parent collection ID (int or None) |
| `selected_collection_changed` | `object` | Collection ID (int or None) |

### DraggableTreeWidget

Source: `ui/collections/tree/draggable_tree_widget.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `request_moved` | `int, int` | Request ID, new collection ID |
| `collection_moved` | `int, object` | Collection ID, new parent ID |

## Collection Widget and Header

### CollectionWidget

Source: `ui/collections/collection_widget.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `item_action_triggered` | `str, int, str` | Forwarded from CollectionTree |
| `item_name_changed` | `str, int, str` | Forwarded from CollectionTree |
| `load_finished` | *(none)* | Background fetch of collections completed |
| `draft_request_requested` | *(none)* | User opened a draft request |

### CollectionHeader

Source: `ui/collections/collection_header.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `new_collection_requested` | `object` | Parent ID (int or None) |
| `new_request_requested` | `object` | Parent collection ID (int or None) |
| `search_changed` | `str` | Search text changed |
| `import_requested` | *(none)* | Import button clicked |

### NewItemPopup

Source: `ui/collections/new_item_popup.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `new_request_clicked` | *(none)* | HTTP Request tile selected |
| `new_collection_clicked` | *(none)* | Collection tile selected |
| `hovered` (inner `_Tile`) | *(none)* | Mouse entered tile |

## Request Tab Deck

### RequestTabBar

Source: `ui/request/navigation/request_tabs/bar.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `currentChanged` | `int` | Current tab index changed |
| `tabCloseRequested` | `int` | Close button clicked on tab |
| `tab_close_requested` | `int` | Alias for tabCloseRequested |
| `tab_double_clicked` | `int` | Tab double-clicked |
| `new_tab_requested` | *(none)* | New blank tab requested |
| `close_others_requested` | `int` | Close all tabs except given index |
| `close_all_requested` | *(none)* | Close all tabs |
| `force_close_all_requested` | *(none)* | Force-close all tabs |
| `tab_reordered` | `int, int` | Tab indices swapped during drag |

### TabButton

Source: `ui/request/navigation/request_tabs/tab_button.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `clicked` | `int` | Tab selected |
| `close_requested` | `int` | Close button clicked |
| `double_clicked` | `int` | Tab double-clicked |
| `reorder_requested` | `int, int` | Drag-reorder source and dest |
| `context_requested` | `int, QPoint` | Right-click context menu |

## Request Editor

### RequestEditorWidget

Source: `ui/request/request_editor/editor_widget.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `send_requested` | *(none)* | Send button clicked |
| `save_requested` | *(none)* | Ctrl+S pressed |
| `dirty_changed` | `bool` | Modified state changed |
| `request_changed` | `dict` | Any field modified (debounced 500ms) |

## Response Viewer

### ResponseViewerWidget

Source: `ui/request/response_viewer/viewer_widget.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `save_response_requested` | `dict` | Save current response as example |
| `save_availability_changed` | `bool` | Response became saveable/unsaveable |

## Folder Editor

### FolderEditorWidget

Source: `ui/request/folder_editor/editor_widget.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `collection_changed` | `dict` | Any field modified (debounced 800ms) |

## Breadcrumb Navigation

### BreadcrumbBar and _EditableLabel

Source: `ui/request/navigation/breadcrumb_bar.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `rename_requested` | `str` | Last segment renamed |
| `item_clicked` | `str, int` | Non-last segment clicked |
| `last_segment_renamed` | `str` | Final segment rename confirmed |

## Worker Threads

### HttpSendWorker

Source: `ui/request/http_worker.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `finished` | `dict` | Request completed (HttpResponseDict) |
| `error` | `str` | Request failed |

### SchemaFetchWorker

Source: `ui/request/http_worker.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `finished` | `dict` | Schema fetch completed (SchemaResultDict) |
| `error` | `str` | Fetch failed |

### SnippetGeneratorWorker

Source: `ui/request/http_worker.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `finished` | `dict` | Snippet generation completed |
| `error` | `str` | Generation failed |

## Environment Widgets

### EnvironmentSelector

Source: `ui/environments/environment_selector.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `environment_changed` | `object` | Selection changed (int or None) |
| `manage_requested` | *(none)* | "Manage Environments" selected |

### EnvironmentSidebarPanel

Source: `ui/environments/environment_sidebar_panel.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `environment_changed` | `object` | Global active environment changed (`int` or `None`) |
| `manage_requested` | *(none)* | **Manage** clicked — opens or focuses the **Environments** tab in the main tab deck |

### EnvironmentEditorWidget

Source: `ui/environments/environment_editor.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `environments_changed` | *(none)* | Environment created, renamed, deleted, or modified |

### EnvironmentEditorDialog

Source: `ui/environments/environment_editor.py`

Modal wrapper around `EnvironmentEditorWidget` (tests and legacy callers).

| Signal | Parameters | Description |
|--------|------------|-------------|
| `environments_changed` | *(none)* | Forwarded from the embedded widget |

## Saved Responses Panel

### SavedResponsesPanel

Source: `ui/sidebar/saved_responses/panel.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `save_current_requested` | *(none)* | "Save Current" clicked |
| `refresh_requested` | *(none)* | Refresh clicked |
| `rename_requested` | `int` | Rename clicked (response ID) |
| `duplicate_requested` | `int` | Duplicate clicked (response ID) |
| `delete_requested` | `int` | Delete clicked (response ID) |

## Auth Widgets

### OAuth2Page

Source: `ui/request/auth/oauth2_page.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `field_changed` | *(none)* | Any OAuth field changed |
| `get_token_requested` | *(none)* | "Get New Access Token" clicked |

## Dialogs

### ImportDialog (_ImportWorker)

Source: `ui/dialogs/import_dialog.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `finished` | `dict` | Import completed (ImportSummary) |
| `error` | `str` | Import failed |
| `files_dropped` (`_DropZone`) | `list` | Files drag-dropped onto zone |

### `_RunnerPanel` (folder inline runner)

Source: `ui/request/folder_editor/runner_panel.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `run_finished` | *(none)* | Run completed, cancelled, or errored (host refreshes history) |

### `RunnerWorker` (collection batch)

Source: `ui/dialogs/collection_runner/worker.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `progress` | `int, dict` | Request completed (index, result) |
| `finished` | `list` | All requests completed |
| `error` | `str` | Fatal error |

## Shared Widgets

### CodeEditorWidget

Source: `ui/widgets/code_editor/editor_widget.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `cursor_position_changed` | `int, int` | 1-based line and column of the cursor |
| `validation_changed` | `list` | Validation errors changed |

### KeyValueTableWidget

Source: `ui/widgets/key_value_table.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `data_changed` | *(none)* | Grid cell/checkbox changed, or bulk text applied back to the grid |

Bulk serialize/parse: `ui/widgets/key_value_bulk.py`

### ClickableLabel (in InfoPopup)

Source: `ui/widgets/info_popup.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `clicked` | *(none)* | Label clicked |

## Theme and Settings

### ThemeManager

Source: `ui/styling/theme_manager.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `theme_changed` | *(none)* | Theme switched |

### TabSettingsManager

Source: `ui/styling/tab_settings_manager.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `settings_changed` | *(none)* | Any tab setting changed |

## Panels

### ConsolePanel (_LogSignalBridge)

Source: `ui/panels/console_panel.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `log_message` | `str` | New log message received |

### HistoryPanel

Source: `ui/panels/history_panel.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `entry_clicked` | `str, str` | History entry clicked (method, url) |

## Signal Patterns

**Worker threads** use a consistent `finished`/`error` pair.  The
`finished` signal carries a typed dict payload, while `error` carries
a plain string message.

**Debounced change signals** prevent excessive updates: `request_changed`
fires 500ms after the last edit, `collection_changed` fires after 800ms.

**Signal forwarding** is used in composite widgets.  `CollectionWidget`
re-emits `CollectionTree` signals so that `MainWindow` only connects to
the top-level widget.

**`object` parameter type** is used when the value is a union such as
`int | None`, since PySide6 `Signal` does not support `Union` types
directly.
