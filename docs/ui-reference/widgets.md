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
| Autocomplete | Dot-path + variable completions (Ctrl+Space, `.`, `{{`); parameter info after `(` or **Ctrl+P** (works from the script find field too; cursor must be in or just after a known call on that line) |
| Symbol navigation | **Ctrl+hover** underlines the segment under the cursor and (after ~400 ms) shows a quick-doc popup; **Ctrl+click** jumps to the user-defined definition (or shows the popup for `pm.*` schema entries); **Ctrl+Q** opens the same popup at the text cursor. Keywords (`const`, `let`, `import`, ...) and unresolved locals are skipped — no underline, no popup |
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
| `_completion_engine` | `CompletionEngine` | Dot-path/variable resolver + call-signature resolution (strict and nearest-on-line) |
| `_completion_popup` | `CompletionPopup` | Floating autocomplete popup |
| `_symbol_doc_popup` | `SymbolDocPopup` | Quick-doc popup for Ctrl+hover and Ctrl+Q |
| `_symbol_hover_path` | `str \| None` | Active hovered identifier dot-path |
| `_symbol_hover_timer` | `QTimer` | 400 ms hover delay before showing the popup |
| `_symbol_link_selections` | `list[QTextEdit.ExtraSelection]` | Underline drawn under the hovered identifier segment while Ctrl is held |
| `_parameter_hint_popup` | `ParameterHintPopup` | Active call signature (JetBrains-style) |
| `_read_only` | `bool` | Immutable mode (for responses) |

### Key Methods

| Method | Description |
|--------|-------------|
| `set_language(lang)` | Switch highlighting and validation |
| `set_variable_map(variables)` | Enable `{{variable}}` highlighting |
| `prettify()` | Auto-format (JSON/XML) |
| `set_text(text)` | Populate (and cache if read-only) |
| `set_minimap_visible(visible)` | Show/hide the right-side minimap |
| `set_symbol_link_range(start, end)` | Underline the document range as a Ctrl+hover link; pass `None`/`None` to clear |

### Signal

`validation_changed(list)` — emitted when linting results change.

### Performance

Large documents (5000+ lines) stay smooth.  Fold computation runs
only for the visible viewport.  Bracket search is bounded by
`_BRACKET_SEARCH_LIMIT`.

## KeyValueTableWidget

Editable key-value table with enable checkboxes.

The horizontal header uses **Interactive** resize for **Key** and **Value** (drag borders), **Stretch** for **Description** so extra table width goes into the notes column, and **Fixed** widths for the checkbox and delete columns.  Default Key / Value pixel widths are **220** and **520** so Key/Value start wide and Description starts with less of the row.

The inner ``QTableWidget`` uses ``objectName="keyValueTable"`` for global QSS (stronger gridlines; full top/right/bottom borders on each header section so the Key/Value header row closes against the tab strip, plus ``QHeaderView::section:first`` for the **left** header edge — a border on the ``QHeaderView`` itself is covered by opaque section backgrounds).  Header sections use **4 px** vertical padding (vs **6 px** on other ``QHeaderView`` tables) so the label row stays a bit shorter.  Each checkbox column cell wraps the ``QCheckBox`` in ``objectName="keyValueCheckCell"`` so a **left** line is drawn in the body (Qt omits the left gridline when column 0 is a cell widget).  The table uses ``QFrame.NoFrame`` so the stylesheet border does not stack on the native scroll-area frame.  The host layout applies **1 px** top margin so the table clears the tab bar baseline.

**Bulk text** (Postman-style): a **Bulk** link with list icon (accent text, underline on hover) sits on the horizontal ``QHeaderView``, right-aligned in the delete column header (trash column).  In bulk mode, a ``keyValueBulkPageHeader`` strip (``bg_alt``, bordered like the table header) sits above the editor with only **Key-value edit** on the right to return to the grid.  Clicking opens a monospace text area (``objectName="keyValueBulkEdit"``).  One row per parameter; use the first ``: `` or ``=`` as the key/value separator (same as ``from_text``).  Prefix a line with ``// `` for a disabled row.  **Key-value edit** applies the text back to the table and emits ``data_changed``.  While bulk mode is open, ``get_data()`` parses the text area so Send still sees current values.  Bulk text does not include **Description** — round-tripping through bulk clears descriptions.  Helpers live in ``ui/widgets/key_value_bulk.py``.

Pass ``settings_profile`` (for example ``"params"``, ``"headers"``, ``"body_form"``) to persist Key/Value widths in ``QSettings`` under the JSON key ``ui/kv_col_widths`` — each profile stores its own ``{"key": width, "value": width}`` entry so sizes survive restarts without clashing between tables.

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

Notification banner shown above JavaScript script editors when
`RuntimeSettings` does not resolve a usable Deno executable.

Source: `src/ui/widgets/runtime_banner.py`

### Features

| Feature | Description |
|---------|-------------|
| Message | Warning icon + rich text; **Open Scripting settings** link opens `Settings` on the Scripting page |
| Download button | "Download Deno" triggers background download |
| Progress bar | 4px bar with MB counter during download |
| Visibility | Stays until Deno becomes available (no dismiss control) |

### Signals

| Signal | Description |
|--------|-------------|
| `download_completed` | Emitted when Deno download finishes successfully |
| `open_settings_clicked` | Emitted when the user clicks **Open Scripting settings** in the message |

### QSS objectNames

- `RuntimeBanner` — banner container (`QFrame`)
- `bannerMessage` — message label (`QLabel`)
- `bannerDownloadBtn` — download button (`QPushButton`)
