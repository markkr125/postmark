# Sidebar

Right-side icon rail with collapsible flyout panel containing
variables, snippets, and saved responses.

Source: `src/ui/sidebar/`

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

Each row shows key, value, and a source badge.

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
