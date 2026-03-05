---
name: "PySide6 Conventions"
description: "Qt/PySide6 widget coding rules — enum scoping, layout casts, signal patterns"
applyTo: "src/ui/**/*.py"
---

# PySide6 coding conventions

## Quick rules — read these first

1. **Every `QPushButton` / `QToolButton` MUST call
   `setCursor(Qt.CursorShape.PointingHandCursor)`** — no exceptions.
   This applies to icon-only buttons, outline buttons, primary buttons,
   link buttons, toolbar buttons, and dialog buttons.  Always add the
   call immediately after construction.
2. **Always use fully qualified enums:** `Qt.ItemDataRole.UserRole`, not
   `Qt.UserRole`.
3. **Wrap programmatic item edits in `blockSignals(True)` / `blockSignals(False)`**
   or you will get infinite recursion from `itemChanged`.
4. **Never hardcode hex colours** — import from `ui.theme`.
5. **UI files must not import from `database/`** — use signals + service layer.
6. **Use `exec()`, not `exec_()`** for menus, dialogs, and the app event loop.
7. **Cast to `QBoxLayout`** before calling `insertWidget()` — `QLayout` does
   not have it in the type stubs.

## Enum access must always be fully qualified

PySide6 requires the scoped enum path. Short-form compiles at runtime but
Pylance / mypy reject it.

```python
# WRONG
Qt.UserRole
Qt.ItemIsEditable
QSizePolicy.Expanding
QTreeWidget.InternalMove
QMessageBox.Yes

# CORRECT
Qt.ItemDataRole.UserRole
Qt.ItemFlag.ItemIsEditable
QSizePolicy.Policy.Expanding
QTreeWidget.DragDropMode.InternalMove
QMessageBox.StandardButton.Yes
Qt.ContextMenuPolicy.CustomContextMenu
Qt.TextFormat.RichText
QTreeWidget.ScrollHint.EnsureVisible
QLineEdit.ActionPosition.LeadingPosition
QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
```

## QLayout does not have insertWidget()

`QLayout.insertWidget()` does not exist in the type stubs. Cast to `QBoxLayout`:

```python
from typing import cast
from PySide6.QtWidgets import QBoxLayout

box = cast(QBoxLayout, widget.layout())
box.insertWidget(1, new_widget)
```

## QLayout.takeAt() / itemAt() and QLayoutItem.widget() may return None

`QLayout.takeAt()` and `QLayout.itemAt()` return `QLayoutItem | None`.
`QLayoutItem.widget()` also returns `QWidget | None`.  PySide6 stub
versions vary — some mark these as non-optional, others as optional.
**Always guard both levels** to stay safe across all environments:

```python
item = layout.takeAt(0)
if item is not None:
    w = item.widget()
    if w is not None:
        w.deleteLater()

# One-liner for read access:
layout_item = layout.itemAt(1)
widget = layout_item.widget() if layout_item else None
if widget:
    widget.hide()
```

## Use exec() not exec_()

`exec_()` is deprecated. Always use `exec()` for menus, dialogs, and the
application event loop.

## UI widgets must not import from database/

Widgets live in `src/ui/` and must communicate via **Qt signals**.
The service layer (`src/services/`) connects those signals to the repository.

## Prefer named constants for custom data roles

Define roles at module level in `ui/collections/tree/constants.py`, not as
inline magic numbers:

```python
ROLE_ITEM_ID   = Qt.ItemDataRole.UserRole      # column 0
ROLE_ITEM_TYPE = Qt.ItemDataRole.UserRole + 1   # column 1
```

Import them where needed:

```python
from ui.collections.tree import ROLE_ITEM_ID, ROLE_ITEM_TYPE
```

## All colours and method_color() live in ui/theme.py

Never hardcode hex colour values in widget files. Import from `ui.theme`:

```python
from ui.theme import COLOR_ACCENT, METHOD_COLORS, DEFAULT_METHOD_COLOR, method_color
```

## Icons — Phosphor font glyphs via ui/icons.py

Use the `phi()` helper from `ui.icons` for all button and menu icons.
**Never** use `QIcon.fromTheme()` — it is unreliable across platforms.

```python
from ui.icons import phi

button.setIcon(phi("paper-plane-right"))
action.setIcon(phi("trash", color="#e74c3c", size=16))
```

- `phi(name)` returns a cached `QIcon` rendered from the bundled Phosphor
  TTF font (`data/fonts/phosphor.ttf`).
- Default colour is `COLOR_TEXT_MUTED`; override with the `color` kwarg.
- Default size is 16 px; override with `size`.
- Icons are cached by `(name, color, size)` — each unique combo is created
  once.
- `load_font()` is called once in `main.py` after `QApplication` is created.
- `clear_cache()` is called automatically by `ThemeManager.apply()` on theme
  change so icon colours refresh.
- Browse available icon names in `data/fonts/phosphor-charmap.json`.

## Theme system — ThemeManager + global QSS + QPalette

The application uses a centralised theme system with three layers:

1. **ThemeManager** (`ui/theme_manager.py`) — singleton `QObject` created
   in `main.py` right after `QApplication`.  Reads/writes `QSettings`,
   resolves light/dark palette, applies `QApplication.setStyle()`,
   `QApplication.setPalette()`, and `QApplication.setStyleSheet()`.
2. **Global QSS** — a single application-wide stylesheet built by
   `ThemeManager._build_global_qss()` using `objectName` selectors.
   Widgets do **not** call `setStyleSheet()` for static styling; instead
   they set `setObjectName("primaryButton")` etc.
3. **QPalette** — built from a `ThemePalette` dict (`ui/theme.py`) via
   `ThemeManager._build_qpalette()`.  Two palettes exist: `LIGHT_PALETTE`
   and `DARK_PALETTE`.  `set_active_palette()` updates the mutable
   module-level colour aliases (`COLOR_ACCENT`, `COLOR_TEXT`, etc.).

### objectName conventions for styling

Widgets use `setObjectName()` to opt into global QSS rules.  These are the
standard object names:

| objectName | Widget type | Visual role |
|---|---|---|
| `primaryButton` | `QPushButton` | Accent-coloured action button |
| `dangerButton` | `QPushButton` | Red destructive action |
| `smallPrimaryButton` | `QPushButton` | Compact accent button |
| `outlineButton` | `QPushButton` | Border-only button |
| `iconButton` | `QPushButton` | Icon-only square button (no padding) |
| `linkButton` | `QPushButton` | Text-only accent link |
| `flatAccentButton` | `QPushButton` | Borderless accent text |
| `flatMutedButton` | `QPushButton` | Borderless muted text |
| `importLinkButton` | `QPushButton` | Underlined import link |
| `dismissButton` | `QPushButton` | Dialog dismiss button |
| `titleLabel` | `QLabel` | Bold 14px heading |
| `sectionLabel` | `QLabel` | 12px section heading |
| `panelTitle` | `QLabel` | Bold 12px panel title with padding |
| `mutedLabel` | `QLabel` | Small muted text |
| `emptyStateLabel` | `QLabel` | Italic muted empty-state message |
| `methodBadge` | `QLabel` | HTTP method badge (tree + tabs) |
| `monoEdit` | `QTextEdit` | Monospace text editor |
| `consoleOutput` | `QTextEdit` | Dark console output area |
| `importTabs` | `QTabWidget` | Box-style tabs in import dialog |
| `codeEditor` | `QPlainTextEdit` | Syntax-highlighted code editor |
| `gqlSplitter` | `QSplitter` | GraphQL query/variables splitter |
| `rowDeleteButton` | `QPushButton` | Row delete button in key-value table |
| `infoPopup` | `QFrame` | Response metadata popup container |
| `infoPopupTitle` | `QLabel` | Popup title heading |
| `infoPopupSeparator` | `QLabel` | Popup horizontal rule |

### When inline setStyleSheet() is still acceptable

Only use `setStyleSheet()` for **dynamic per-instance** styling that
varies at runtime and cannot be expressed with objectName selectors:

- Method badge background-color (varies by HTTP method)
- Status label colour (varies by HTTP status code)
- History row method colour
- Breadcrumb per-segment colour
- Spinner animation colours
- Drop-zone active hover overlay

For everything else, use `setObjectName()` and let the global QSS handle it.

### Adding new styled widgets

1. Choose an appropriate `objectName` from the table above, or create a new
   one if none fits.
2. Call `widget.setObjectName("yourName")` in the widget constructor.
3. Add the corresponding QSS rule in `ThemeManager._build_global_qss()`.
4. Do **not** call `setStyleSheet()` on the widget.

### Theme module contents

`theme.py` provides four categories of exports:

1. **Palette definitions** — `ThemePalette` (TypedDict schema),
   `LIGHT_PALETTE`, `DARK_PALETTE`.  `set_active_palette(palette)` updates
   the mutable colour aliases.  `current_palette()` returns the active dict.
2. **Colour constants** — mutable module-level aliases
   (`COLOR_ACCENT`, `COLOR_SUCCESS`, `COLOR_TEXT`, etc.) that reflect the
   currently active palette.
3. **Method colour mapping** — `METHOD_COLORS: dict[str, str]` maps HTTP
   methods to colours. `DEFAULT_METHOD_COLOR` is the fallback.
   `method_color(method)` returns the colour for a given method string.
4. **Badge system** — constants and helpers for the tree item request badges:
   - `METHOD_SHORT_LABELS: dict[str, str]` — compact labels (e.g.
     `DELETE` → `DEL`, `PATCH` → `PAT`, `OPTIONS` → `OPT`).
   - `BADGE_FONT_SIZE` (9px), `BADGE_MIN_WIDTH` (32px), `BADGE_HEIGHT`
     (16px), `BADGE_BORDER_RADIUS` (3px), `TREE_ROW_HEIGHT` (24px).
   - `method_short_label(method)` — returns the short label for a method.

### Tree item badge rendering

Request items in the collection tree use a **custom delegate**
(`CollectionTreeDelegate`, a `QStyledItemDelegate` subclass) that paints the
method badge and request name directly — no per-row `QWidget` is created.
This saves ~50-60 KB per request item compared to `setItemWidget`.

The delegate reads `ROLE_METHOD` (column 0) for the HTTP method and column 1
display text for the request name.  It paints:

1. A rounded-rect badge (`BADGE_MIN_WIDTH` x `BADGE_HEIGHT`, background from
   `method_color()`, white text from `method_short_label()`).
2. The request name (elided, palette-aware text colour).

Folder items fall through to the default `QStyledItemDelegate` rendering
(standard `setText` content with a folder icon).

**Placeholder items** (empty-folder prompts) still use `setItemWidget`
because they contain clickable HTML links.

## QPushButton — icons, cursors, and icon-only buttons

### Every button must have a pointing-hand cursor

All `QPushButton` instances must set a hand cursor so users know they are
clickable:

```python
btn.setCursor(Qt.CursorShape.PointingHandCursor)
```

### Icon-only buttons must use `iconButton`, not `outlineButton`

The `outlineButton` style has `padding: 4px 12px` which leaves no room for
the icon in a compact square button.  For icon-only buttons (no text):

1. Use `setObjectName("iconButton")` — it has `padding: 0px` with hover
   and checked states.
2. Use `setFixedSize(28, 28)` (not `setFixedWidth`) so the button is a
   proper square.
3. Do **not** set text — icon only.

```python
# CORRECT — icon-only button
btn = QPushButton()
btn.setIcon(phi("funnel"))
btn.setObjectName("iconButton")
btn.setCursor(Qt.CursorShape.PointingHandCursor)
btn.setFixedSize(28, 28)

# WRONG — icon invisible due to outlineButton padding
btn = QPushButton()
btn.setIcon(phi("funnel"))
btn.setObjectName("outlineButton")
btn.setFixedWidth(28)
```

### Buttons with text + icon use `outlineButton`

When a button has both text and an icon, use `outlineButton` and let Qt
auto-size the width:

```python
btn = QPushButton("Wrap")
btn.setIcon(phi("text-align-left"))
btn.setObjectName("outlineButton")
btn.setCursor(Qt.CursorShape.PointingHandCursor)
```

## Wrap programmatic item edits in blockSignals

`QTreeWidget` emits `itemChanged` whenever item text is modified — including
programmatic changes.  If a slot connected to `itemChanged` also modifies
items, you get infinite recursion or spurious rename signals.

**Always** wrap bulk or programmatic updates:

```python
self._tree.blockSignals(True)
try:
    item.setText(0, new_name)
    item.setData(1, ROLE_OLD_NAME, new_name)
finally:
    self._tree.blockSignals(False)
```

Every call to `blockSignals(True)` must have a matching
`blockSignals(False)` — prefer a `try/finally` block.

## Tree item column semantics differ by type

The `CollectionTree` uses a **two-column** `QTreeWidget` with asymmetric
semantics:

| | Column 0 | Column 1 |
|---|---|---|
| **Folder** | Display name (text + icon) | Type metadata only (via data roles) |
| **Request** | Empty text `""` (delegate paints badge + name) | Raw name text (used for rename and delegate display) |

Because of this asymmetry:
- Folder rename uses Qt's built-in `editItem()` on column 0.
- Request rename creates an overlay `QLineEdit` on the tree viewport.
- Reading a request's display name: use `item.text(1)` (column 1).

## Data role layout on QTreeWidgetItems

All constants are defined in `ui/collections/tree/constants.py`.

| Role constant | Value | Stored on | Content |
|---|---|---|---|
| `ROLE_ITEM_ID` | `UserRole` | Column 0 | Database PK (`int`) |
| `ROLE_ITEM_TYPE` | `UserRole + 1` | Column 1 | `"folder"` or `"request"` |
| `ROLE_OLD_NAME` | `UserRole + 2` | Column 1 | Original name stashed during rename |
| `ROLE_LINE_EDIT` | `UserRole + 3` | Column 1 | (legacy — unused with delegate approach) |
| `ROLE_NAME_LABEL` | `UserRole + 4` | Column 1 | (legacy — unused with delegate approach) |
| `ROLE_MIME_DATA` | `UserRole + 5` | Column 3 | (legacy — unused, drag reads data roles directly) |
| `ROLE_METHOD` | `UserRole + 6` | Column 0 | HTTP method string (requests only) |
| `ROLE_PLACEHOLDER` | `UserRole + 10` | Column 1 | `"placeholder"` marker string |

Gap at `+7` through `+9` is reserved for future roles.

## Context-menu state — `_current_item`

`CollectionTree._current_item` is set on right-click and read by the
triggered menu action.

- It is **per-menu-invocation** state, not per-selection.
- **DO NOT** read `_current_item` outside a context-menu handler — its value
  is only reliable between the right-click and the menu action.

## Background workers use QThread + moveToThread

For blocking operations (e.g. DB fetch, HTTP requests), create a `QObject`
worker, move it to a `QThread`, and connect `thread.started` to `worker.run`.
Emit a signal with the result when done.  Examples:

- `_CollectionFetcher` in `collection_widget.py` — DB fetch
- `HttpSendWorker` in `http_worker.py` — HTTP request execution
- `SchemaFetchWorker` in `http_worker.py` — GraphQL schema introspection

## InfoPopup — QFrame-based tooltip popups

Use `QFrame` (not `QWidget` or `QDialog`) for tooltip-like popups.
`QWidget` does **not** reliably render QSS borders on Linux.

The `InfoPopup` base class (`ui/info_popup.py`) provides:

- **Window flags:** `Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
  | Qt.WindowType.WindowStaysOnTopHint`
- **objectName:** `"infoPopup"` — styled via global QSS
- **Click-outside dismiss:** App-wide event filter via
  `QApplication.instance().installEventFilter(self)`.  The filter returns
  `False` so the click propagates to the widget underneath (e.g. to open
  a sibling popup without needing a double-click).
- **150ms grace period:** Clicks within 150ms of `show_below()` are ignored
  to prevent the opening click from immediately closing the popup.
- **Copy-to-clipboard feedback:** `_copy_to_clipboard(text, btn)` copies
  text, sets the button to "Copied!" with a checkmark icon, then restores
  the original text after 1.2s via `QTimer.singleShot`.

### ClickableLabel

`ClickableLabel(QLabel)` emits a `clicked` signal on `mousePressEvent`.
Used for the response status bar labels that open popups.
