---
name: "PySide6 Conventions"
description: "Qt/PySide6 widget coding rules — enum scoping, layout casts, signal patterns"
applyTo: "src/ui/**/*.py"
---

# PySide6 coding conventions

## Quick rules — read these first

1. **Always use fully qualified enums:** `Qt.ItemDataRole.UserRole`, not
   `Qt.UserRole`.
2. **Wrap programmatic item edits in `blockSignals(True)` / `blockSignals(False)`**
   or you will get infinite recursion from `itemChanged`.
3. **Never hardcode hex colours** — import from `ui.theme`.
4. **UI files must not import from `database/`** — use signals + service layer.
5. **Use `exec()`, not `exec_()`** for menus, dialogs, and the app event loop.
6. **Cast to `QBoxLayout`** before calling `insertWidget()` — `QLayout` does
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

### Theme module contents

`theme.py` provides three categories of exports:

1. **Colour constants** — semantic (`COLOR_ACCENT`, `COLOR_SUCCESS`, etc.),
   neutral (`COLOR_WHITE`, `COLOR_TEXT`, etc.), and import-dialog-specific
   (`COLOR_DROP_ZONE_BORDER`, etc.).
2. **Method colour mapping** — `METHOD_COLORS: dict[str, str]` maps HTTP
   methods to colours. `DEFAULT_METHOD_COLOR` is the fallback.
   `method_color(method)` returns the colour for a given method string.
3. **Badge system** — constants and helpers for the tree item request badges:
   - `METHOD_SHORT_LABELS: dict[str, str]` — compact labels (e.g.
     `DELETE` → `DEL`, `PATCH` → `PAT`, `OPTIONS` → `OPT`).
   - `BADGE_FONT_SIZE` (9px), `BADGE_MIN_WIDTH` (32px), `BADGE_HEIGHT`
     (16px), `BADGE_BORDER_RADIUS` (3px), `TREE_ROW_HEIGHT` (24px).
   - `method_short_label(method)` — returns the short label for a method.

### Tree item badge rendering

Request items in the collection tree use a **custom item widget** (set via
`QTreeWidget.setItemWidget`).  The widget is an `HBoxLayout` containing:

1. A fixed-width `QLabel` badge (32×16px, monospace font, centered text,
   coloured background from `method_color()`).
2. A `QLabel` showing the request name (elided).

Folder items use **no custom widget** — they show standard `setText` content
with a folder icon.

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
| **Request** | Custom widget (`setItemWidget` — method badge + label), text is `""` | Raw name text (used for rename storage) |

Because of this asymmetry:
- Folder rename uses Qt's built-in `editItem()` on column 0.
- Request rename injects a manual `QLineEdit` into the custom widget layout.
- Reading a request's display name requires fetching from the `QLabel` inside
  the item widget, **not** from `item.text(0)` (which is always empty).

## Data role layout on QTreeWidgetItems

All constants are defined in `ui/collections/tree/constants.py`.

| Role constant | Value | Stored on | Content |
|---|---|---|---|
| `ROLE_ITEM_ID` | `UserRole` | Column 0 | Database PK (`int`) |
| `ROLE_ITEM_TYPE` | `UserRole + 1` | Column 1 | `"folder"` or `"request"` |
| `ROLE_OLD_NAME` | `UserRole + 2` | Column 1 | Original name stashed during rename |
| `ROLE_LINE_EDIT` | `UserRole + 3` | Column 1 | Temp `QLineEdit` ref during request rename |
| `ROLE_NAME_LABEL` | `UserRole + 4` | Column 1 | `QLabel` ref during request rename |
| `ROLE_MIME_DATA` | `UserRole + 5` | Column 3 | `QMimeData` for drag |
| `ROLE_PLACEHOLDER` | `UserRole + 10` | Column 1 | `"placeholder"` marker string |

Gap at `+6` through `+9` is reserved for future roles.

## Context-menu state — `_current_item`

`CollectionTree._current_item` is set on right-click and read by the
triggered menu action.

- It is **per-menu-invocation** state, not per-selection.
- **DO NOT** read `_current_item` outside a context-menu handler — its value
  is only reliable between the right-click and the menu action.

## Background workers use QThread + moveToThread

For blocking operations (e.g. DB fetch), create a `QObject` worker, move it
to a `QThread`, and connect `thread.started` to `worker.run`. Emit a signal
with the result when done. See `_CollectionFetcher` in `collection_widget.py`
for the canonical pattern.
