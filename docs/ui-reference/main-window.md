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

```text
+------------------------------------------------------------------------+
| Menu bar                                                                |
+------------------------------------------------------------------------+
| [|] | Collections + |  BreadcrumbBar                       |  Rail  |   |
|     | Environments  +--------------------------------------+  [ {} ]|   |
|     | (or Local     |  RequestTabBar (multi-row deck)      |  [ <> ]|   |
|     |  scripts)     |  Editor stack (request / folder / env) |  [ [] ]|   |
|     |               |  Editor stack (request / folder / env) |  [ [] ]|   |
|     |               |  + RequestEditorWidget (method | URL | send) |Flyout  |   |
|     |               |  (Params|Headers|Body|Auth|Desc|Scripts)|Panel|   |
|     |               +--------------------------------------+        |   |
|     |               |  ResponseViewerWidget                |        |   |
|     |               |  (status | time | size | network)    |        |   |
|     |               |  (Body | Headers)                    |        |   |
+------------------------------------------------------------------------+
| Console / History (collapsible bottom panel)                          |
+------------------------------------------------------------------------+
```

The narrow **left rail** (`LeftSidebar`, Phosphor **files** and **code** icons)
mirrors the right rail: it toggles a collapsible flyout with a ``QStackedWidget``
whose default page is ``_left_nav_splitter`` (collections above environments).
The **code** icon switches to ``LocalScriptsSidebarPanel`` (placeholder).  **View → Toggle Sidebar** (``Ctrl+B``)
collapses or expands that flyout to the same widths as dragging the splitter
handle; the rail stays visible.  The main central ``QHBoxLayout`` has **no**
outer margins so the left rail is flush with the window edge and its
``status_bar_bg`` fill is not separated from the chrome by the main ``bg``
strip.

| Attribute | Type | Description |
|-----------|------|-------------|
| `_tabs` | `dict[int, TabContext]` | Active tabs keyed by tab-bar index |
| `_deferred_tabs` | `dict[int, dict]` | Lazy-loaded tabs from session restore |
| `_tab_bar` | `RequestTabBar` | Multi-row wrapped tab deck |
| `_editor_stack` | `QStackedWidget` | Per-tab request editor stack |
| `_response_stack` | `QStackedWidget` | Per-tab response viewer stack |
| `_breadcrumb_bar` | `BreadcrumbBar` | Path navigation bar |
| `_left_sidebar` | `LeftSidebar` | Left activity rail + stacked flyout (collections / environments vs local scripts) |
| `_right_sidebar` | `RightSidebar` | Right icon rail and flyout panel |
| `collection_widget` | `CollectionWidget` | Collection tree + header (top of left column) |
| `_left_nav_splitter` | `QSplitter` | Vertical splitter inside the left flyout: collections above environments |
| `_local_scripts_sidebar` | `LocalScriptsSidebarPanel` | Local scripts flyout page (placeholder list shell) |
| `_env_selector` | `EnvironmentSidebarPanel` | Global environment picker: scrollable rows (name + **Set active** / **Clear**); empty list shows a hint that opens the same flow as **Manage**; attribute name kept for mixin compatibility |
| `_history` | `list[int]` | Request open-history stack (Alt+Left/Right) |
| `_tab_nav_back` / `_tab_nav_forward` | `list[int]` | Tab activation history (nav tokens; Go menu) |
| `_tab_nav_current` | `int \| None` | Active tab `nav_token` for activation history |
| `_theme_manager` | `ThemeManager` | App-wide theme controller |
| `_tab_settings_manager` | `TabSettingsManager` | Tab preference controller |

## Keyboard navigation

| Action | Shortcut | Behaviour |
|--------|----------|-------------|
| Request back | Alt+Left | Previously opened request from the collection tree |
| Request forward | Alt+Right | Forward in request open history |
| Tab back | Ctrl+Alt+Left (Go → Back) | Previously activated tab (all tab types) |
| Tab forward | Ctrl+Alt+Right (Go → Forward) | Forward in tab activation history |
| Next tab | Ctrl+Tab, Ctrl+PgDown | Next tab in the deck (wrap) |
| Previous tab | Ctrl+Shift+Tab, Ctrl+PgUp | Previous tab in the deck (wrap) |

Tab activation history is in-memory only and starts empty after session
restore. On Linux, some window managers reserve Ctrl+Alt+arrow keys for
workspace switching; use the Go menu if shortcuts do not fire.

## Mixin Responsibilities

### _TabNavHistoryMixin

Tab activation back/forward (`main_window/tab_nav/history.py`).

| Method | Description |
|--------|-------------|
| `_record_tab_activation(index)` | Push prior `nav_token` when the active tab changes |
| `_navigate_tab_back()` / `_navigate_tab_forward()` | Walk activation stacks |
| `_seed_tab_nav_after_restore()` | Clear stacks; seed current token after session restore |
| `_purge_tab_nav_token(token)` | Remove closed tab from stacks |


### _TabControllerMixin

Tab lifecycle and history navigation.

| Method | Description |
|--------|-------------|
| `_open_request(request_id, push_history, is_preview)` | Load request into existing or new tab |
| `_open_folder(collection_id, focus_scripts_kind=..., focus_runner_panel=...)` | Open folder detail editor tab; optional Scripts sub-tab or **Runs → New run** (`focus_runner_panel`).  Run menu / tree **Run** use `_on_run_collection_by_id`, which calls `_open_folder(..., focus_runner_panel=True)` |
| `_open_environments_tab()` | Open or focus the **Environments** tab (`EnvironmentEditorWidget` in the main editor stack). When no environments exist, the tab shows a sidebar hint and a placeholder instead of the name/variable editor until the first environment is created (e.g. from the left column **Add**) |
| `_on_tab_changed(index)` | Active tab switched (debounced) |
| `_flush_tab_change()` | Immediate breadcrumb, sidebar, variable refresh |
| `_navigate_back()` / `_navigate_forward()` | Request open-history navigation |
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
| `_on_environments_data_changed()` | After edits in the **Environments** tab: refresh env selector, variable maps, sidebar |
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
even with many tabs.  **Environments** tabs are included in the saved list
as ``{"type": "environments"}`` and restored as a normal tab row entry.
