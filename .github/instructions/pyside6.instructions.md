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
4. **Never hardcode hex colours** — import from `ui.styling.theme`.
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

## All colours and method_color() live in ui/styling/theme.py

Never hardcode hex colour values in widget files. Import from `ui.styling.theme`:

```python
from ui.styling.theme import COLOR_ACCENT, METHOD_COLORS, DEFAULT_METHOD_COLOR, method_color
```

## Icons — Phosphor font glyphs via ui/styling/icons.py

Use the `phi()` helper from `ui.styling.icons` for all button and menu icons.
**Never** use `QIcon.fromTheme()` — it is unreliable across platforms.

```python
from ui.styling.icons import phi

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

1. **ThemeManager** (`ui/styling/theme_manager.py`) — singleton `QObject`
   created in `main.py` right after `QApplication`.  Reads/writes
   `QSettings`, resolves light/dark palette, applies
   `QApplication.setStyle()`, `QApplication.setPalette()`, and
   `QApplication.setStyleSheet()`.
2. **Global QSS** — a single application-wide stylesheet built by
   `ThemeManager._build_global_qss()` using `objectName` selectors.
   Widgets do **not** call `setStyleSheet()` for static styling; instead
   they set `setObjectName("primaryButton")` etc.
3. **QPalette** — built from a `ThemePalette` dict
   (`ui/styling/theme.py`) via `ThemeManager._build_qpalette()`.  Two
   palettes exist: `LIGHT_PALETTE` and `DARK_PALETTE`.
   `set_active_palette()` updates the mutable module-level colour aliases
   (`COLOR_ACCENT`, `COLOR_TEXT`, etc.).

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
| `variablePopupBadge` | `QLabel` | Source badge (collection/environment/unresolved/local) |
| `variablePopupName` | `QLabel` | Variable name heading |
| `variablePopupValue` | `QLineEdit` | Editable variable value field |
| `variablePopupUpdateBtn` | `QPushButton` | "Update" button (persist local override) |
| `variablePopupResetBtn` | `QPushButton` | "Reset" button (remove local override) |
| `variablePopupAddSelect` | `QPushButton` | "Add to ▾" select-box toggle |
| `variablePopupAddPanel` | `QFrame` | Expandable target panel for unresolved vars |
| `variablePopupTarget` | `QPushButton` | Collection/environment target button |
| `variablePopupNoEnv` | `QLabel` | "No environment selected" warning |
| `variablePopup` | `QFrame` | Variable popup container |
| `saveButton` | `QPushButton` | Save action button |
| `sidebarSearch` | `QLineEdit` | Collection sidebar search input |
| `sidebarSectionLabel` | `QLabel` | Sidebar section heading |
| `sidebarToolButton` | `QToolButton` | Sidebar toolbar button |

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

> **Detailed contents (palette definitions, colour constants, method colour
> mapping, badge system) are in the `widget-patterns` skill.**

### Tree item badge rendering

> **Custom delegate details, column semantics, and data role layout are in
> the `widget-patterns` skill.**  Key fact: the delegate reads
> `ROLE_METHOD` (column 0) and column 1 display text.  No per-row
> `QWidget` is created.

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

> **Full column semantics table, data role layout, and context-menu
> `_current_item` rules are in the `widget-patterns` skill.**
>
> Quick reference: folders use column 0 for display; requests use column 1
> (delegate paints badge + name from column 0 `ROLE_METHOD` + column 1
> text).

## Background workers, InfoPopup, and VariablePopup

> **QThread worker pattern, InfoPopup base class details, VariablePopup
> singleton rules, and VariableLineEdit painting rules are in the
> `widget-patterns` skill.**
>
> Key rules (always apply):
> - Use `QObject` + `moveToThread()`, not `QThread` subclass.
> - `InfoPopup` uses `QFrame` (not `QWidget`) — `QWidget` breaks QSS
>   borders on Linux.
> - `VariablePopup` uses class-level callbacks, **not** Qt signals.
> - `VariableLineEdit.set_variable_map()` takes `dict[str, VariableDetail]`.
