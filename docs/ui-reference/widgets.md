# Shared Widgets

Reusable components shared across the application.

Source: `src/ui/widgets/`

## CodeEditorWidget

Rich text editor with syntax highlighting, code folding, and inline
validation.

Source: `src/ui/widgets/code_editor/`

Inherits `_PaintingMixin`, `_FoldingMixin`, `QPlainTextEdit`.

### Features

| Feature | Description |
|---------|-------------|
| Syntax highlighting | Pygments-based, 50+ languages |
| Code folding | Collapsible regions with fold badges |
| Line-number gutter | With error indicators |
| Bracket matching | Highlight matching parens/braces |
| Inline validation | JSON/XML/GraphQL error markers |
| Variable highlighting | `{{variable}}` patterns with coloured background |
| Autocomplete | Dot-path + variable completions (Ctrl+Space, `.`, `{{`) |
| Minimap | Optional bird's-eye view of the document (`set_minimap_visible()`) |
| Word wrap | Togglable |
| Prettify | Auto-format JSON/XML |

### Key Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `_language` | `str` | Active language (json, python, graphql, etc.) |
| `_errors` | `list[SyntaxError_]` | Validation results |
| `_fold_regions` | `dict[int, int]` | Start line to end line fold map |
| `_variable_map` | `dict[str, VariableDetail]` | Resolved variables |
| `_completion_engine` | `CompletionEngine` | Dot-path/variable resolver |
| `_completion_popup` | `CompletionPopup` | Floating autocomplete popup |
| `_read_only` | `bool` | Immutable mode (for responses) |

### Key Methods

| Method | Description |
|--------|-------------|
| `set_language(lang)` | Switch highlighting and validation |
| `set_variable_map(variables)` | Enable `{{variable}}` highlighting |
| `prettify()` | Auto-format (JSON/XML) |
| `set_text(text)` | Populate (and cache if read-only) |
| `set_minimap_visible(visible)` | Show/hide the right-side minimap |

### Signal

`validation_changed(list)` — emitted when linting results change.

### Performance

Large documents (5000+ lines) stay smooth.  Fold computation runs
only for the visible viewport.  Bracket search is bounded by
`_BRACKET_SEARCH_LIMIT`.

## KeyValueTableWidget

Editable key-value table with enable checkboxes.

### Columns

| Column | Widget |
|--------|--------|
| Enabled | Checkbox (on/off row) |
| Key | QLineEdit with `{{variable}}` highlighting |
| Value | QLineEdit with `{{variable}}` highlighting |
| Description | QLineEdit (optional notes) |
| Delete | Icon button (x) |

A `_VariableHighlightDelegate` draws coloured backgrounds on
`{{var}}` patterns.

### Key Methods

| Method | Description |
|--------|-------------|
| `data()` | Dict of enabled rows |
| `load(dict)` | Populate from dict |
| `set_variable_map(variables)` | Enable highlighting |

### Signal

`data_changed()` — any key, value, or checkbox changed.

## VariableLineEdit

`QLineEdit` subclass with `{{variable}}` pattern rendering.

### Rendering

- Normal text: regular colour
- `{{resolved_variable}}`: orange background box
- `{{unknown_variable}}`: red background box

### Hover Popup

Hovering over a `{{var}}` shows `VariablePopup` with value, source,
and edit/update/reset buttons.

## VariablePopup

Singleton frameless `QFrame` tool window for editing variable values.

### Content

| Element | Description |
|---------|-------------|
| Variable name | Title |
| Value input | Editable QLineEdit |
| Source badge | Environment, Collection, or Local |
| Update button | Persist value globally |
| Reset button | Remove local override |
| Add to button | Add unresolved variable to environment/collection |

### Callbacks

Set once by MainWindow:

| Callback | Trigger |
|----------|---------|
| `set_save_callback(func)` | Update button clicked |
| `set_local_override_callback(func)` | Popup closes with edited value |
| `set_reset_local_override_callback(func)` | Reset button clicked |
| `set_add_variable_callback(func)` | Add to button clicked |

### Auto-Close

- 8-second timeout without interaction
- Click outside the popup
- Escape key

## InfoPopup

Base class for floating metadata popups.

### Methods

| Method | Description |
|--------|-------------|
| `_make_header_with_copy(title)` | Title row with Copy button |
| `_copy_to_clipboard(text, button)` | Copy with button feedback |

### Auto-Close

Click outside, Escape key, or parent window move/resize.

## SearchReplaceBar

Standalone find/replace bar that attaches to any `CodeEditorWidget`.

Source: `src/ui/widgets/search_replace_bar.py`

### Features

| Feature | Description |
|---------|-------------|
| Find | Highlights all matches with `COLOR_WARNING` background |
| Replace | Replace current match or all matches |
| Go-to-line | `QInputDialog` prompt for line number |
| Keyboard shortcuts | Ctrl+F (find), Ctrl+H (replace), Ctrl+G (go-to-line) |
| Navigation | Prev/Next with wrap-around |

### Key Methods

| Method | Description |
|--------|-------------|
| `toggle_search()` | Show the search bar, or close if already visible |
| `toggle_replace()` | Show the search bar with replace row visible |
| `close_search()` | Hide bar, clear highlights, reset state |
| `goto_line()` | Show go-to-line dialog and jump |

Subclasses: `StatusPopup`, `TimingPopup`, `SizePopup`, `NetworkPopup`.

## RuntimeBanner

Notification banner shown above script editors when advanced features
(async/await, npm imports) are detected but Deno is not installed.

Source: `src/ui/widgets/runtime_banner.py`

### Features

| Feature | Description |
|---------|-------------|
| Detection message | Warning icon + explanation of why Deno is needed |
| Download button | "Download Deno" triggers background download |
| Progress bar | 4px bar with MB counter during download |
| Dismiss | X button hides the banner for the current session |

### Signals

| Signal | Description |
|--------|-------------|
| `download_completed` | Emitted when Deno download finishes successfully |
| `dismissed` | Emitted when user dismisses the banner |

### QSS objectNames

- `RuntimeBanner` — banner container (`QFrame`)
- `bannerMessage` — message label (`QLabel`)
- `bannerDownloadBtn` — download button (`QPushButton`)
