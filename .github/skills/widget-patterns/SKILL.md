---
name: widget-patterns
description: Detailed PySide6 widget implementation patterns for the Postmark codebase. Use when creating new widgets, adding tree items, implementing custom delegates, building popup dialogs, using background workers, or working with VariablePopup/VariableLineEdit.
---

# Widget implementation patterns

Detailed patterns for building PySide6 widgets in the Postmark codebase.
For core rules (enums, layouts, cursors), see `pyside6.instructions.md`.

## Tree item badge rendering

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

## Tree item column semantics

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

## Background workers — QThread + moveToThread

For blocking operations (e.g. DB fetch, HTTP requests), create a `QObject`
worker, move it to a `QThread`, and connect `thread.started` to `worker.run`.
Emit a signal with the result when done.

**Pattern:**

```python
class _MyWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)

    def run(self) -> None:
        try:
            result = some_blocking_call()
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))

# In the widget:
thread = QThread()
worker = _MyWorker()
worker.moveToThread(thread)
thread.started.connect(worker.run)
worker.finished.connect(self._on_result)
worker.finished.connect(thread.quit)
worker.finished.connect(worker.deleteLater)
thread.finished.connect(thread.deleteLater)
thread.start()
```

Existing workers:
- `_CollectionFetcher` in `collection_widget.py` — DB fetch
- `HttpSendWorker` in `http_worker.py` — HTTP request execution
- `SchemaFetchWorker` in `http_worker.py` — GraphQL schema introspection

## InfoPopup — QFrame-based tooltip popups

Use `QFrame` (not `QWidget` or `QDialog`) for tooltip-like popups.
`QWidget` does **not** reliably render QSS borders on Linux.

The `InfoPopup` base class (`ui/widgets/info_popup.py`) provides:

- **Window flags:** `Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
  | Qt.WindowType.WindowStaysOnTopHint`
- **objectName:** `"infoPopup"` — styled via global QSS
- **Click-outside dismiss:** App-wide event filter via
  `QApplication.instance().installEventFilter(self)`.  Returns `False` so
  the click propagates (e.g. to open a sibling popup without double-click).
- **150ms grace period:** Clicks within 150ms of `show_below()` are ignored
  to prevent the opening click from immediately closing the popup.
- **Copy-to-clipboard feedback:** `_copy_to_clipboard(text, btn)` copies
  text, sets the button to "Copied!" with a checkmark icon, then restores
  the original text after 1.2s via `QTimer.singleShot`.

### ClickableLabel

`ClickableLabel(QLabel)` emits a `clicked` signal on `mousePressEvent`.
Used for the response status bar labels that open popups.

## VariablePopup — singleton variable hover popup

`VariablePopup` (`ui/widgets/variable_popup.py`) is a **singleton** `QFrame` popup
shown when the user hovers over a `{{variable}}` reference in
`VariableLineEdit`.

### Rules for VariablePopup

- **Do NOT use Qt signals** for VariablePopup actions.  It uses class-level
  callbacks instead (`set_save_callback`, `set_local_override_callback`,
  `set_reset_local_override_callback`, `set_add_variable_callback`,
  `set_has_environment`).  These are classmethods that store `Callable`
  objects on the class itself.  Wired once in `MainWindow.__init__`.
- **Dismiss behaviour** follows `InfoPopup` pattern: app-wide `eventFilter`
  closes on click-outside, with 150ms grace period.
- **"Add to" panel** — for unresolved variables only.  A button toggles an
  inline `_add_panel` with collection/environment target buttons.  Do not
  replace with `QMenu` or `QComboBox` — both cause dismiss issues on Linux.

### Rules for VariableLineEdit

`VariableLineEdit` (`ui/widgets/variable_line_edit.py`) is a `QLineEdit` subclass
that paints coloured pills over `{{variable}}` references.

- Call `set_variable_map(variables: dict[str, VariableDetail])` to update
  the variable lookup used for painting and hover popups.
- `mouseMoveEvent` triggers `VariablePopup.show_variable()` after a 150ms
  `QTimer` delay when the cursor hovers over a `{{variable}}` token.
- Pill colours come from `ui.styling.theme` — do not hardcode hex values.

## Theme module contents

`theme.py` provides four categories of exports:

1. **Palette definitions** — `ThemePalette` (TypedDict), `LIGHT_PALETTE`,
   `DARK_PALETTE`.  `set_active_palette(palette)` updates the mutable
   colour aliases.  `current_palette()` returns the active dict.
2. **Colour constants** — mutable module-level aliases (`COLOR_ACCENT`,
   `COLOR_SUCCESS`, `COLOR_TEXT`, etc.).
3. **Method colour mapping** — `METHOD_COLORS: dict[str, str]` maps HTTP
   methods to colours.  `method_color(method)` returns the colour.
4. **Badge system** — `METHOD_SHORT_LABELS`, `BADGE_FONT_SIZE` (9px),
   `BADGE_MIN_WIDTH` (32px), `BADGE_HEIGHT` (16px), `BADGE_BORDER_RADIUS`
   (3px), `TREE_ROW_HEIGHT` (24px), `method_short_label(method)`.

## New widget checklist

When creating a new widget:

1. Add `from __future__ import annotations` at the top.
2. Add a module-level docstring.
3. Add a class docstring.
4. Every `QPushButton`/`QToolButton` must call
   `setCursor(Qt.CursorShape.PointingHandCursor)`.
5. Use fully qualified enums (e.g. `Qt.AlignmentFlag.AlignLeft`).
6. Use `setObjectName()` + global QSS for static styling, not
   `setStyleSheet()`.
7. Import colours from `ui.styling.theme`, icons from
   `ui.styling.icons.phi()`.
8. Add the widget to the architecture tree in `copilot-instructions.md`.
9. Create a matching test file in `tests/ui/<subpackage>/`.
10. Add the test file to the test tree in `testing.instructions.md`.
11. If the widget emits signals wired in MainWindow, update
    `signal-flow` skill.
