---
name: signal-flow
description: Complete signal flow diagrams, signal declaration reference, and MainWindow wiring map for the Postmark codebase. Use when wiring new signals, debugging signal connections, adding new UI actions, or understanding how data flows between widgets.
---

# Signal flow reference

This skill documents every signal flow, every `Signal(...)` declaration,
and every connection made in `MainWindow.__init__`.

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

### Tab bar flow

```
RequestTabBar.currentChanged
  → MainWindow._on_tab_changed
    → load current TabContext → update request_editor + breadcrumbs

RequestTabBar.tab_close_requested(index)
  → MainWindow._on_tab_close

RequestTabBar.tab_double_clicked(index)
  → MainWindow._on_tab_double_click

RequestTabBar.close_others_requested(index)
  → MainWindow._close_others_tabs

RequestTabBar.close_all_requested / force_close_all_requested
  → MainWindow._close_all_tabs
```

### Breadcrumb bar flow

```
BreadcrumbBar.item_clicked(type, id)
  → MainWindow._on_breadcrumb_clicked
    → _open_request(id) or _open_folder(id)

BreadcrumbBar.last_segment_renamed(new_name)
  → MainWindow._on_breadcrumb_rename
    → CollectionService.rename_request / rename_collection
```

### Environment selector flow

```
EnvironmentSelector.environment_changed(env_id | None)
  → MainWindow._on_environment_changed
    → _refresh_variable_map()

EnvironmentSelector.manage_requested
  → MainWindow._on_manage_environments
    → show EnvironmentEditor dialog
```

### Save response flow

```
ResponseViewerWidget.save_response_requested(dict)
  → MainWindow._on_save_response
    → CollectionService.save_response(request_id, ...)
```

### Folder editor flow

```
FolderEditor.collection_changed(dict)
  → MainWindow handler → CollectionService.update_collection(...)
```

### History panel flow

```
HistoryPanel.entry_clicked(method, url)
  → (wired to open or populate editor)
```

### Toggle actions flow

```
MainWindow._toggle_response_action.triggered
  → _toggle_response_pane (show/hide response viewer)

MainWindow._toggle_sidebar_action.triggered
  → _toggle_sidebar (show/hide collection sidebar)

MainWindow._toggle_bottom_action.triggered
  → _toggle_bottom_panel (show/hide console/history)

MainWindow._toggle_layout_action.triggered
  → _toggle_layout_orientation (horizontal ↔ vertical)
```

### Code snippet flow

```
MainWindow snippet_act.triggered
  → _on_code_snippet
    → CodeSnippetDialog(request_data)
      → SnippetGenerator.generate(language, ...)
```

### Settings flow

```
MainWindow settings_act.triggered
  → _on_settings
    → SettingsDialog(ThemeManager)
      → theme changes applied via ThemeManager
```

### Collection runner flow

```
MainWindow run_act.triggered
  → _on_run_collection
    → CollectionRunnerWidget(collection_id)
      → CollectionRunnerWidget.progress(index, result_dict)
      → CollectionRunnerWidget.finished(results_list)
      → CollectionRunnerWidget.error(message)
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

## Unconnected signals

| Signal / Feature | Location | Status |
|---|---|---|
| `MainWindow.run_action` | `main_window.py` | QAction created, not connected |

All other signals in the flow diagrams above are fully wired.

## Complete signal declaration reference

### Collection subsystem

| Class | Signal | Signature |
|-------|--------|-----------|
| `CollectionHeader` | `new_collection_requested` | `Signal(object)` — `int \| None` |
| `CollectionHeader` | `new_request_requested` | `Signal(object)` |
| `CollectionHeader` | `search_changed` | `Signal(str)` |
| `CollectionHeader` | `import_requested` | `Signal()` |
| `CollectionTree` | `item_action_triggered` | `Signal(str, int, str)` |
| `CollectionTree` | `item_name_changed` | `Signal(str, int, str)` — `(type, id, new_name)` |
| `CollectionTree` | `collection_rename_requested` | `Signal(int, str)` |
| `CollectionTree` | `collection_delete_requested` | `Signal(int)` |
| `CollectionTree` | `request_rename_requested` | `Signal(int, str)` |
| `CollectionTree` | `request_delete_requested` | `Signal(int)` |
| `CollectionTree` | `request_moved` | `Signal(int, int)` |
| `CollectionTree` | `collection_moved` | `Signal(int, object)` |
| `CollectionTree` | `new_collection_requested` | `Signal(object)` |
| `CollectionTree` | `new_request_requested` | `Signal(object)` |
| `CollectionTree` | `selected_collection_changed` | `Signal(object)` |
| `DraggableTreeWidget` | `request_moved` | `Signal(int, int)` |
| `DraggableTreeWidget` | `collection_moved` | `Signal(int, object)` |
| `CollectionWidget` | `item_action_triggered` | `Signal(str, int, str)` |
| `CollectionWidget` | `item_name_changed` | `Signal(str, int, str)` |
| `CollectionWidget` | `load_finished` | `Signal()` |

### Request / response subsystem

| Class | Signal | Signature |
|-------|--------|-----------|
| `RequestEditorWidget` | `send_requested` | `Signal()` |
| `RequestEditorWidget` | `save_requested` | `Signal()` |
| `RequestEditorWidget` | `dirty_changed` | `Signal(bool)` |
| `RequestEditorWidget` | `request_changed` | `Signal(dict)` |
| `ResponseViewerWidget` | `save_response_requested` | `Signal(dict)` |
| `HttpSendWorker` | `finished` | `Signal(dict)` — `HttpResponseDict` |
| `HttpSendWorker` | `error` | `Signal(str)` |
| `SchemaFetchWorker` | `finished` | `Signal(dict)` — `SchemaResultDict` |
| `SchemaFetchWorker` | `error` | `Signal(str)` |

### Tab bar

| Class | Signal | Signature |
|-------|--------|-----------|
| `RequestTabBar` | `tab_close_requested` | `Signal(int)` |
| `RequestTabBar` | `tab_double_clicked` | `Signal(int)` |
| `RequestTabBar` | `new_tab_requested` | `Signal()` |
| `RequestTabBar` | `close_others_requested` | `Signal(int)` |
| `RequestTabBar` | `close_all_requested` | `Signal()` |
| `RequestTabBar` | `force_close_all_requested` | `Signal()` |

### Breadcrumb bar

| Class | Signal | Signature |
|-------|--------|-----------|
| `BreadcrumbSegment` | `rename_requested` | `Signal(str)` |
| `BreadcrumbBar` | `item_clicked` | `Signal(str, int)` — `(type, id)` |
| `BreadcrumbBar` | `last_segment_renamed` | `Signal(str)` |

### Environments

| Class | Signal | Signature |
|-------|--------|-----------|
| `EnvironmentSelector` | `environment_changed` | `Signal(object)` — `int \| None` |
| `EnvironmentSelector` | `manage_requested` | `Signal()` |
| `EnvironmentEditor` | `environments_changed` | `Signal()` |

### Folder editor

| Class | Signal | Signature |
|-------|--------|-----------|
| `FolderEditor` | `collection_changed` | `Signal(dict)` |

### Dialogs

| Class | Signal | Signature |
|-------|--------|-----------|
| `ImportDialog._ImportWorker` | `finished` | `Signal(dict)` |
| `ImportDialog._ImportWorker` | `error` | `Signal(str)` |
| `ImportDialog._DropZone` | `files_dropped` | `Signal(list)` |
| `ImportDialog` | `import_completed` | `Signal()` |
| `CollectionRunnerWidget` | `progress` | `Signal(int, dict)` |
| `CollectionRunnerWidget` | `finished` | `Signal(list)` |
| `CollectionRunnerWidget` | `error` | `Signal(str)` |

### Other widgets

| Class | Signal | Signature |
|-------|--------|-----------|
| `ThemeManager` | `theme_changed` | `Signal()` |
| `ClickableLabel` | `clicked` | `Signal()` |
| `KeyValueTable` | `data_changed` | `Signal()` |
| `CodeEditorWidget` | `validation_changed` | `Signal(list)` |
| `HistoryPanel` | `entry_clicked` | `Signal(str, str)` |

## MainWindow signal wiring summary

All connections made in `MainWindow.__init__` (and `_create_menus`):

**From collection sidebar:**
- `collection_widget.item_action_triggered` → `_on_item_action`
- `collection_widget.load_finished` → `_on_load_finished`
- `collection_widget.item_name_changed` → `_on_item_name_changed`

**From tab bar:**
- `_tab_bar.currentChanged` → `_on_tab_changed`
- `_tab_bar.tab_close_requested` → `_on_tab_close`
- `_tab_bar.tab_double_clicked` → `_on_tab_double_click`
- `_tab_bar.close_others_requested` → `_close_others_tabs`
- `_tab_bar.close_all_requested` → `_close_all_tabs`
- `_tab_bar.force_close_all_requested` → `_close_all_tabs`

**From breadcrumb bar:**
- `_breadcrumb_bar.item_clicked` → `_on_breadcrumb_clicked`
- `_breadcrumb_bar.last_segment_renamed` → `_on_breadcrumb_rename`

**From environment selector:**
- `_env_selector.environment_changed` → `_on_environment_changed`
- `_env_selector.manage_requested` → `_on_manage_environments`

**From toolbar / menus:**
- `back_action.triggered` → `_navigate_back`
- `forward_action.triggered` → `_navigate_forward`
- `import_act.triggered` → `_on_import`
- `save_act.triggered` → `_on_save_request`
- `snippet_act.triggered` → `_on_code_snippet`
- `settings_act.triggered` → `_on_settings`
- `run_act.triggered` → `_on_run_collection`
- `exit_act.triggered` → `close`
- `_toggle_response_action` → `_toggle_response_pane`
- `_toggle_sidebar_action` → `_toggle_sidebar`
- `_toggle_bottom_action` → `_toggle_bottom_panel`
- `_toggle_layout_action` → `_toggle_layout_orientation`

**Per-tab editors (wired in `_create_tab`):**
- `editor.send_requested` → `_on_send_request`
- `editor.save_requested` → `_on_save_request`
- `editor.dirty_changed` → `_sync_save_btn`
- `viewer.save_response_requested` → `_on_save_response`

**VariablePopup callbacks (classmethods, wired once):**
- `VariablePopup.set_save_callback(_on_variable_updated)`
- `VariablePopup.set_local_override_callback(_on_local_variable_override)`
- `VariablePopup.set_reset_local_override_callback(_on_reset_local_override)`
- `VariablePopup.set_add_variable_callback(_on_add_unresolved_variable)`
- `VariablePopup.set_has_environment(...)`
