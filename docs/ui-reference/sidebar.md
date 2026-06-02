# Sidebar

Icon rails with collapsible flyout panels: **LeftSidebar** hosts the
collections and environment picker on one stacked page, **Local scripts &
snippets** on another (Phosphor **code** icon), and workspace **History** on a
third (Phosphor **clock-counter-clockwise**); **RightSidebar** hosts variables,
snippets, saved responses, and per-request History.

Source: `src/ui/sidebar/`

## LeftSidebar

VS Code–style **activity bar** on the outer left edge.  The rail is a
fixed-width `QWidget` (`objectName` ``leftSidebarRail``); width and Phosphor
icon size follow ``LEFT_RAIL_WIDTH_EM`` and ``LEFT_RAIL_ICON_EM`` in ``theme.py``
(multiples of the primary font height).  Its background uses palette
``status_bar_bg`` (same as ``QStatusBar#appStatusBar``).  The checked
icon’s left accent is **painted** in ``_LeftRailButton.paintEvent`` at full
widget height (``LEFT_RAIL_ACCENT_STRIPE_WIDTH_PX`` wide) because Fusion-style
``QToolButton`` stylesheets often clip ``border-left`` to the content box.  The flyout uses
``objectName`` ``leftSidebarFlyout``; unlike the right rail flyout it has **no**
built-in title row (the injected ``CollectionWidget`` already owns the
``CollectionHeader`` heading).  The flyout body is a ``QStackedWidget``: page
0 is ``MainWindow``'s vertical ``_left_nav_splitter`` (collections above
environments); page 1 is a vertical splitter: ``CollectionWidget(variant="local_scripts")``
(script/folder tree) above ``SnippetsSidebarPanel`` (user snippet list with **New** /
row click → edit dialog).  Horizontal inset for the collections and environment bodies uses
``LEFT_NAV_PANEL_MARGIN_H_LEFT_PX`` /
``LEFT_NAV_PANEL_MARGIN_H_RIGHT_PX`` in ``theme.py``, applied inside
``CollectionWidget`` and ``EnvironmentSidebarPanel`` so the vertical splitter
between them stays full flyout width (only the pane content is inset).
When the splitter width is 0, the flyout applies a **local** ``setStyleSheet``
to remove borders so they are not painted on top of the main splitter handle.
When open, the flyout uses a **left** border only (vs the rail); the **right**
edge is the main horizontal splitter handle only, so there is no double line
beside the editor.  Page 0 is installed via :meth:`LeftSidebar.set_content`; page
1 via :meth:`LeftSidebar.set_local_scripts_panel` (which also reveals the second
rail icon); page 2 via :meth:`LeftSidebar.set_history_panel` (workspace send
history, ``objectName`` ``globalHistoryPanel``).

### Rail Buttons

| Button | Icon (Phosphor) | Panel |
|--------|-----------------|-------|
| Collections | `files` | Collections tree + environment rows (``_left_nav_splitter``) |
| Local scripts & snippets | `code` | Local scripts tree + ``SnippetsSidebarPanel`` (vertical splitter) |
| History | `clock-counter-clockwise` | ``HistoryPanel`` in global mode — all sends; Open navigates to editor |

### Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `panel_state_changed` | `bool` | ``True`` when flyout width becomes non-zero, ``False`` when collapsed to zero |

### Public API

| Method | Description |
|--------|-------------|
| `set_content(widget)` | Install page ``"collections"`` (collections + environments splitter) |
| `set_local_scripts_panel(widget)` | Register page ``"local_scripts"`` and show its rail icon |
| `install_in_splitter(splitter)` | Insert rail then flyout as the first two splitter children |
| `open_panel(key="collections")` | Expand flyout and activate the rail button (no-op if *key* is not registered) |
| `close_panel()` | Collapse flyout to zero width (same end state as dragging the handle closed) |
| `toggle_panel(key)` | Toggle the named panel |
| `is_open` | Property: flyout width is non-zero |

**View → Toggle Sidebar** (``Ctrl+B``) calls :meth:`close_panel` when the flyout
is open and :meth:`open_panel` when it is closed — it does not hide the
activity rail, so it matches a manual resize of the flyout to zero width.

## SnippetsSidebarPanel

User-authored script snippets in a **tree** (same interaction model as local
scripts): **JavaScript**, **TypeScript**, and **Python** as separate top-level
nodes (not grouped), each containing category folders, then snippet leaves.
**New** opens ``SnippetCaptureDialog`` in sidebar-create mode (language defaults
from the selected branch); clicking a snippet opens edit (save only — use
**Remove snippet** in the tree context menu to delete).  Create and edit dialogs open at **720×580** with a
``CodeEditorWidget`` body (syntax highlighting, folding, and language-aware
completion for JavaScript, TypeScript, or Python).  Header layout matches local scripts (**Snippets** title, section
**(i)** for panel help, **Search snippets**, **New**).  Snippet leaves use the same row height and indentation as local script files.

Right-click context menus:

| Node | Actions |
|------|---------|
| Language | **Add new category** (name prompt, then create-snippet dialog with that category) |
| Category | **Add new snippet**, **Rename category**, **Remove category** (deletes all snippets in the category) |
| Snippet | **Edit snippet**, **Rename snippet** (in-place overlay, like local scripts), **Remove snippet** |

Language roots show a muted trailing count (e.g. ``3 snippets``). Snippet leaves show a
muted context tag (**Pre-request**, **Post-response**, or **Any**) on the right.
Category **Rename** uses the tree's in-place folder editor.

The snippet picker (``SnippetsPopup``) is insert-only — no delete control on
user rows.

Source: ``src/ui/sidebar/snippets_sidebar_panel.py``.

## LocalScriptsSidebarPanel (legacy)

Unused legacy shell — still re-exported from ``src/ui/sidebar/__init__.py`` but
**not** installed by ``MainWindow``.  The live local-scripts flyout top pane is
``CollectionWidget(variant="local_scripts")``.  See [Local scripts](local-scripts.md).
Source: ``src/ui/sidebar/local_scripts_sidebar_panel.py``.

## RightSidebar

Always-visible fixed-width icon rail.

### Rail Buttons

| Button | Icon | Panel |
|--------|------|-------|
| Variables | `{}` | Read-only variable list |
| Code Snippet | `<>` | Code snippet generator |
| Saved Responses | `[]` | Saved response browser |
| History | clock (counter-clockwise) | Per-request send log (read-only) |

### Key Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `_flyout` | `_FlyoutPanel` | Collapsible content panel |
| `_active_panel` | `str \| None` | Currently visible panel name |
| `_available_panels` | `set[str]` | Panels usable for current request |

### Public API

| Method | Description |
|--------|-------------|
| `load_variables(variables, local_overrides)` | Refresh variables panel |
| `load_snippet_for_request(request_id)` | Refresh snippet (live on change) |
| `load_saved_responses(request_id)` | Refresh saved responses list |
| `set_request_history_context(...)` | Configure History panel for active request |
| `install_in_splitter(splitter)` | Place flyout and rail as splitter children |

## FlyoutPanel

Collapsible content area as a splitter child (`objectName` ``sidebarPanelArea``).

Contains four stacked panels with a title bar and close button.
The flyout can snap closed via its splitter handle.  The **left** edge against
the editor is the ``mainWindowHorizontalSplitter`` handle only (no flyout
``border-left`` — a full-height left border was hidden under ``QScrollArea``
children and looked like a stray line beside the title row).  The **right**
edge uses a flyout ``border-right`` (and the same on inner ``QScrollArea``
widgets so the viewport does not paint over it) before the icon rail.

## VariablesPanel

Read-only display of resolved variables grouped by source.

### Sections (collapsible)

| Section | Content |
|---------|---------|
| Environment | Variables from active environment |
| Collection | Variables from selected collection |
| Local Overrides | Per-request temporary overrides |

Each row shows key and value as read-only line edits (selectable text); the key
column is wider than before with the full name on hover. Very long values start
collapsed behind a Phosphor caret icon (same ``data/fonts/phosphor.ttf`` set as
elsewhere via ``phi()``) to expand the full text.

### Key Method

`load_variables(variables, local_overrides, has_environment)` —
populate sections from `VariableDetail` dicts.

## Script debug widgets (`debug_inspector_split`, `debug_call_stack_panel`, `debug_watch_in_tree`)

Source: `src/ui/sidebar/debug_inspector_split.py` (horizontal **Call stack |
Watches strip + unified tree**), `debug_call_stack_panel.py`, `debug_scopes_panel.py`,
`debug_watch_in_tree.py`.  Composed into `ScriptOutputPanel` during inline script
debug (see [Request Editor — Inline debug inspector](request-editor.md#inline-debug-inspector-debugger-tab)).
`DebugPanel` in `debug_panel.py` bundles step controls and
:class:`DebugInspectorSplit`.

### DebugInspectorSplit layout

```text
+------------------+---------------------------+
| Call stack       | Watches (expression strip)|
| (full height)    +---------------------------+
|                  | debugScopesTree           |
|                  |  Watches / Locals / pm …  |
+------------------+---------------------------+
```

| `objectName` | Description |
|--------------|-------------|
| `debugInspectorSplitter` | Horizontal splitter (~200px call stack \| values column) |
| `debugCallStackList` | Frame list (left column, full height) |
| `debugWatchAddEdit` | Watch expression field above the tree (+ / − icon buttons) |
| `debugScopesTree` | **Watches** section + locals / `pm` / `globalThis` / env (one tree) |

While **paused**, `DebugWatchesPane.refresh_watches()` calls
`DebugProtocol.submit_evaluate(expr)` (non-blocking). Value cells show
`cached_evaluate(expr)` immediately (placeholder `—` until the first result).
`DebugProtocol.evaluated` updates the tree when the background worker or batch
evaluator returns.  Expressions persist across `set_idle` and `clear_session`;
`set_idle` clears the eval cache and prunes orphan `pm.require` LSP workspace keys.

### CallStackPanel

| Signal | Parameters | Description |
|--------|------------|-------------|
| `frame_selected` | `int` | Stack frame index; host calls `select_frame` and refreshes variables |

| `objectName` | Description |
|--------------|-------------|
| `debugCallStackList` | Frame labels `index: name  @ line N` (1-based line in UI) |

## SnippetPanel

Inline code snippet generator.

### UI Components

| Component | Description |
|-----------|-------------|
| Language dropdown | 23 languages in 3 categories |
| Code editor | Read-only `CodeEditorWidget` |
| Copy button | Copy snippet to clipboard |
| Settings gear | Per-language option popup |

### Language Categories

| Category | Languages |
|----------|-----------|
| Shell | cURL, HTTP raw, wget, HTTPie, PowerShell |
| Dynamic | Python, JavaScript, Node.js, Ruby, PHP, Dart |
| Compiled | Go, Rust, C, Swift, Java, Kotlin, C# |

### Settings Popup Options

Indent count (1-8), indent type (space/tab), trim body, follow
redirects, timeout.  Language-specific: async/await (JS), ES6 (JS),
multiline (cURL), long-form flags, quote style, etc.

Snippets regenerate live as the request changes.

## SavedResponsesPanel

List/detail flyout for browsing saved response examples.

Source: `src/ui/sidebar/saved_responses/`

### Layout

```
+-----------------------+-----------------------+
| Saved Responses List  | Detail View           |
| (filtered by request) |                       |
|                       | Status badge + name   |
| [Response 1]          | Tabs:                 |
| [Response 2]          |   Body | Headers |    |
| [Response 3]          |   Request Body        |
+-----------------------+-----------------------+
| Refresh | Save Current                        |
+-------------------------------------------+
```

### List Item Delegate

`SavedResponseDelegate` renders each row with a coloured status code,
response name, and timestamp.

### Detail View Tabs

| Tab | Content |
|-----|---------|
| Response body | Code editor with mode selector |
| Response headers | Read-only key-value list |
| Request body | Original request body snapshot |

### Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `save_current_requested` | *(none)* | Save current response |
| `rename_requested` | `int` | Rename response |
| `duplicate_requested` | `int` | Duplicate response |
| `delete_requested` | `int` | Delete response |

### Search and Filter (_PanelSearchFilterMixin)

Filter by name and search within response bodies.

## HistoryPanel

Read-only list/detail UI for HTTP **send history**. The same widget class is
used twice:

| Instance | `objectName` | Rail | Data source |
|----------|--------------|------|-------------|
| Per-request | `requestHistoryPanel` | Right (4th button) | `RequestHistoryService.list_for_request(request_id)` |
| Workspace global | `globalHistoryPanel` | Left (3rd button) | `RequestHistoryService.list_for_sidebar()` |

Source: `src/ui/sidebar/history/` (`panel.py`, `global_mode/`).

See also [RequestHistoryService](../api-reference/services/request-history-service.md).

### objectNames

| Widget | objectName | Mode |
|--------|------------|------|
| Panel (request) | `requestHistoryPanel` | Right rail |
| Panel (global) | `globalHistoryPanel` | Left rail |
| Global header row | `globalHistoryHeader` | Left rail only (title + date filter + refresh) |
| Date filter button | `iconButton` (funnel) | Global header; per-request search row |
| Date filter popup | `infoPopup` | From/To pickers, presets (Today, 7/30 days, All), Apply, Clear |
| Date editors | `historyDateFilterEdit` | Inside the filter popup |
| Search field | `requestHistorySearch` | Both |
| List stack | `requestHistoryList` | Both |
| Tree | `requestHistoryTree` | Both |
| Replay | `requestHistoryReplayButton` | Request mode only |
| Open | `requestHistoryOpenButton` | Unused in UI (hidden); global open is single-click on tree |

**Refresh:** On the right, `RightSidebar` reparents `refresh_button()` into the
flyout title bar. On the left, refresh stays in `globalHistoryHeader`.

### Shared behaviour

- `QTreeWidget` groups sends under local calendar days (Today, Yesterday, or a
  formatted date).
- `requestHistorySearch` filters by URL, request name, and method (substring) and
  by **exact** HTTP status when the term is all digits (e.g. `200`, `400` — `40`
  does not match `400`).
- **Date range** (funnel): inline popup with local-calendar From/To dates and
  presets; filters at query time via `executed_from` / `executed_to` on
  `list_for_sidebar` / `list_for_request`. Active filter shows a checked funnel
  and a summary tooltip.
- `refresh_requested` → `refresh()` reloads metadata.

### Per-request detail (right rail only)

- Detail tabs: Body, Headers, Request Headers, Request Body (from stored snapshot).
- Full payloads load on selection in **request** mode only.
- Row meta may include `(deleted)` or `(draft)` when `request_id` is null (see
  `was_persisted_request` in the service docs).

### Request mode (right rail)

- Active **saved** request tab only; draft tabs disable the rail icons with a tooltip
  (“save the request first”, or “original request was deleted” for tabs opened from
  deleted-request history).
- Empty copy: no sends yet for this request.
- **Replay** (detail header): HTTP from stored snapshot; updates centre response only.
- Context menu: **Replay this request**, **Delete item**.
- `replay_requested` / `delete_requested` → `MainWindow` handlers.
- After replay, `responseReplayIndicator` links back to this panel (`focus_entry`).

### Global mode (left rail)

- **List only** — no Body/Headers detail stack on the left (preview lives on the
  right History panel after **Open**).
- Lists all workspace sends (including draft-tab sends and orphaned rows after
  request delete). Default cap: 500 rows (search applies the same limit).
- Empty copy: no send history yet (with hint to send a request).
- **Open** on **single-click** of a send row (also context menu and **Enter**):
  emits `entry_open_requested(entry_id)` → `MainWindow._open_from_global_history`.
  - **Existing request** (`request_id` set and still in DB): open/focus request tab,
    open right History, select the send, then load detail asynchronously (loading bar).
    Centre response viewer is unchanged.
  - **Deleted / orphan / draft history row**: new draft tab prefilled from snapshot,
    stored response in viewer; right History and Saved Responses stay disabled (hover
    the greyed rail icons for why).
- No replay/delete on the global instance (use the right panel after navigating).

### Signals

| Signal | Parameters | Mode | Description |
|--------|------------|------|-------------|
| `refresh_requested` | *(none)* | Both | Reload list for current scope |
| `entry_open_requested` | `entry_id: int` | Global | Open send in editor + right History |
| `replay_requested` | `entry_id: int` | Request | Replay selected send |
| `delete_requested` | `entry_id: int` | Request | Delete selected send |
