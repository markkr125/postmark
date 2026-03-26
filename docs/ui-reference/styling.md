# Styling

Theme management, colour palettes, global stylesheet, and icon
system.

Source: `src/ui/styling/`

## Theme Module

`theme.py` defines the `ThemePalette` TypedDict, two built-in
palettes, and utility functions.

### Palettes

| Name | Description |
|------|-------------|
| `LIGHT_PALETTE` | Light background, dark text |
| `DARK_PALETTE` | Dark background, light text |

Each palette has 60+ colour slots grouped by category.  See
[ThemePalette](../api-reference/typedicts.md#themepalette) for the
complete field list.

### Utility Functions

| Function | Description |
|----------|-------------|
| `method_color(method)` | Colour for HTTP method badge (GET=green, POST=amber, etc.) |
| `status_color(code)` | Colour for HTTP status code (2xx=green, 4xx=amber, 5xx=red) |

### Badge Constants

| Constant | Description |
|----------|-------------|
| `BADGE_HEIGHT` | Method badge height in pixels |
| `BADGE_BORDER_RADIUS` | Badge corner radius |
| `BADGE_MIN_WIDTH` | Minimum badge width |
| `BADGE_H_PAD` | Horizontal padding |

## ThemeManager

Singleton `QObject` that applies style, palette, and global QSS.

### Settings (via QSettings)

| Key | Values | Description |
|-----|--------|-------------|
| `theme/style` | Fusion, Native | Qt style engine |
| `theme/color_scheme` | Auto, Light, Dark | Colour scheme |

### Key Methods

| Method | Description |
|--------|-------------|
| `apply()` | Apply style, palette, and global QSS |
| `style` (property) | Get/set saved style |
| `scheme` (property) | Get/set saved scheme |

### Signal

`theme_changed()` — emitted after theme switch for widget refresh.

### Auto Scheme

When scheme is "Auto", the manager listens to OS colour-scheme
changes (PySide6 6.5+) and re-applies automatically.

## Global QSS

`build_global_qss(palette)` returns a complete QSS string with all
60+ palette colours interpolated.

### Coverage

| Category | Examples |
|----------|---------|
| Standard widgets | QMainWindow, QDialog, QLineEdit, QComboBox, QPushButton |
| Named buttons | primaryButton, outlineButton, flatMutedButton, linkButton |
| Collection tree | Hover, selection, row height |
| Tab bar | Tab chip styling |
| Code editor | Gutter, fold badges |
| Dialogs and popups | Import drop zone, settings |

### Object Names

Widgets reference specific `objectName` values in QSS selectors.
When adding a new widget that needs global styling, set its
`objectName` and add a corresponding rule in `build_global_qss()`.

## Icons

`phi(name, color="", size=16)` returns a cached `QIcon` from the
Phosphor font.

### Font

Phosphor TTF bundled at `data/fonts/`.  Loaded once at app startup.

### Cache

Icons are cached by `(name, color, size)` tuple.  Subsequent calls
return the same `QIcon` instance.

### Usage

```python
from ui.styling.icons import phi

action.setIcon(phi("arrow-left"))
button.setIcon(phi("trash", color="#e74c3c", size=16))
```

500+ icon names available.

## TabSettingsManager

Persisted request-tab preferences via `QSettings`.

### Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `small_labels` | `bool` | False | Compact tab layout |
| `show_path_for_duplicates` | `bool` | True | Full path for same-name tabs |
| `mark_modified` | `bool` | True | Show bullet on unsaved tabs |
| `show_full_path_on_hover` | `bool` | True | Tooltip shows full path |
| `open_new_tabs_at_end` | `bool` | False | New tabs at end vs adjacent |
| `enable_preview_tab` | `bool` | True | Italic preview-mode tabs |
| `tab_limit` | `int` | 30 | Max open tabs (1-100) |
| `tab_limit_policy` | `str` | "close_unused" | Or "close_unchanged" |
| `activate_on_close` | `str` | "mru" | "left", "right", or "mru" |
| `wrap_mode` | `str` | "multiple_rows" | Or "single_row" |

### Signal

`settings_changed()` — emitted when any setting changes.
