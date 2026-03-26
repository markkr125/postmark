# MainWindow

Top-level application container.  Inherits from four mixins and
`QMainWindow`.

Source: `src/ui/main_window/`

## Inheritance Chain

```
QMainWindow
  _TabControllerMixin
    _DraftControllerMixin
      _VariableControllerMixin
        _SendPipelineMixin
          MainWindow
```

## Layout

```
+------------------------------------------------------------------+
| Menu bar                                                          |
+------------------------------------------------------------------+
| Collection    |  BreadcrumbBar                       |  Rail  |   |
| Sidebar       +--------------------------------------+  [ {} ]|   |
|               |  RequestTabBar (multi-row deck)      |  [ <> ]|   |
| CollectionTree+--------------------------------------+  [ [] ]|   |
|               |  RequestEditorWidget                 |        |   |
|               |  (method | URL | send button)        |Flyout  |   |
|               |  (Params|Headers|Body|Auth|Desc|Scripts)|Panel|   |
|               +--------------------------------------+        |   |
|               |  ResponseViewerWidget                |        |   |
|               |  (status | time | size | network)    |        |   |
|               |  (Body | Headers)                    |        |   |
+------------------------------------------------------------------+
| Console / History (collapsible bottom panel)                     |
+------------------------------------------------------------------+
```

## Key Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `_tabs` | `dict[int, TabContext]` | Active tabs keyed by tab-bar index |
| `_deferred_tabs` | `dict[int, dict]` | Lazy-loaded tabs from session restore |
| `_tab_bar` | `RequestTabBar` | Multi-row wrapped tab deck |
| `_editor_stack` | `QStackedWidget` | Per-tab request editor stack |
| `_response_stack` | `QStackedWidget` | Per-tab response viewer stack |
| `_breadcrumb_bar` | `BreadcrumbBar` | Path navigation bar |
| `_right_sidebar` | `RightSidebar` | Icon rail and flyout panel |
| `collection_widget` | `CollectionWidget` | Left sidebar with collection tree |
| `_history` | `list[int]` | Back/forward navigation stack |
| `_theme_manager` | `ThemeManager` | App-wide theme controller |
| `_tab_settings_manager` | `TabSettingsManager` | Tab preference controller |

## Mixin Responsibilities

### _TabControllerMixin

Tab lifecycle and history navigation.

| Method | Description |
|--------|-------------|
| `_open_request(request_id, push_history, is_preview)` | Load request into existing or new tab |
| `_open_folder(collection_id)` | Open folder detail editor tab |
| `_on_tab_changed(index)` | Active tab switched (debounced) |
| `_flush_tab_change()` | Immediate breadcrumb, sidebar, variable refresh |
| `_navigate_back()` / `_navigate_forward()` | History navigation |
| `_enforce_tab_limit_before_open()` | Apply tab-count policy |
| `_restore_tabs()` / `_save_tabs()` | Session persistence via QSettings |
| `_close_tabs(indices)` | Bulk close with cleanup |

### _DraftControllerMixin

Unsaved request tab management.

| Method | Description |
|--------|-------------|
| `_open_draft_request()` | Create tab with `request_id=None` |
| `_on_save_request()` | Show `SaveRequestDialog`, persist draft |

### _VariableControllerMixin

Environment variable resolution and sidebar refresh.

| Method | Description |
|--------|-------------|
| `_refresh_variable_map(editor, request_id, local_overrides)` | Push combined variables to editor |
| `_on_environment_changed(env_id)` | Refresh all open editor variable maps |
| `_on_variable_updated(var_name, new_value, source, source_id)` | Persist global variable change |
| `_on_local_variable_override(var_name, new_value, source, source_id)` | Store per-request override |
| `_on_reset_local_override(var_name)` | Remove temporary override |
| `_refresh_sidebar(ctx)` | Debounced sidebar panel refresh |

### _SendPipelineMixin

HTTP send/cancel/cleanup cycle.

| Method | Description |
|--------|-------------|
| `_on_send_request()` | Gather request data, spawn `HttpSendWorker` on `QThread` |
| `_on_send_finished(data)` | Load `HttpResponseDict` into viewer |
| `_on_send_error(msg)` | Display error in viewer |
| `_cancel_send()` | Cancel in-flight request |
| `_cleanup_send_thread()` | Tear down QThread and worker |

## Session Persistence

On close, `_save_tabs()` writes the open tab list to `QSettings`.
On startup, `_restore_tabs()` creates `_deferred_tabs` entries that
are only materialised when first activated.  This keeps startup fast
even with many tabs.
