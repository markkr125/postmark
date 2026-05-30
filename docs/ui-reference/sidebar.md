# Sidebar

Icon rails with collapsible flyout panels: **LeftSidebar** hosts the
collections and environment picker on one stacked page and **Local scripts &
snippets** on another (Phosphor **code** icon); **RightSidebar** hosts variables,
snippets, and saved responses.

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
rail icon).

### Rail Buttons

| Button | Icon (Phosphor) | Panel |
|--------|-----------------|-------|
| Collections | `files` | Collections tree + environment rows (``_left_nav_splitter``) |
| Local scripts & snippets | `code` | Local scripts tree + ``SnippetsSidebarPanel`` (vertical splitter) |

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
| `install_in_splitter(splitter)` | Place flyout and rail as splitter children |

## FlyoutPanel

Collapsible content area as a splitter child.

Contains three stacked panels with a title bar and close button.
The flyout can snap closed via its splitter handle.

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
