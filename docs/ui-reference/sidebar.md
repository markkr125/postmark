# Sidebar

Icon rails with collapsible flyout panels: **LeftSidebar** hosts the
collections and environment picker; **RightSidebar** hosts variables,
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
``CollectionHeader`` heading).  Horizontal inset for the collections and
environment bodies uses ``LEFT_NAV_PANEL_MARGIN_H_LEFT_PX`` /
``LEFT_NAV_PANEL_MARGIN_H_RIGHT_PX`` in ``theme.py``, applied inside
``CollectionWidget`` and ``EnvironmentSidebarPanel`` so the vertical splitter
between them stays full flyout width (only the pane content is inset).
When the splitter width is 0, the flyout applies a **local** ``setStyleSheet``
to remove borders so they are not painted on top of the main splitter handle.
When open, the flyout uses a **left** border only (vs the rail); the **right**
edge is the main horizontal splitter handle only, so there is no double line
beside the editor.  Its body comes from :meth:`LeftSidebar.set_content` (in
``MainWindow`` this is the vertical ``_left_nav_splitter``).

### Rail Buttons

| Button | Icon (Phosphor) | Panel |
|--------|-----------------|-------|
| Collections | `files` | Collections tree + environment rows (injected content) |

### Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `panel_state_changed` | `bool` | ``True`` when flyout width becomes non-zero, ``False`` when collapsed to zero |

### Public API

| Method | Description |
|--------|-------------|
| `set_content(widget)` | Install the sole flyout body widget |
| `install_in_splitter(splitter)` | Insert rail then flyout as the first two splitter children |
| `open_panel(key="collections")` | Expand flyout and activate the rail button |
| `close_panel()` | Collapse flyout to zero width (same end state as dragging the handle closed) |
| `toggle_panel(key)` | Toggle the named panel |
| `is_open` | Property: flyout width is non-zero |

**View → Toggle Sidebar** (``Ctrl+B``) calls :meth:`close_panel` when the flyout
is open and :meth:`open_panel` when it is closed — it does not hide the
activity rail, so it matches a manual resize of the flyout to zero width.

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
