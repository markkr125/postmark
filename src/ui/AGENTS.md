# PySide6 coding conventions

## Quick rules — read these first

1. **Every `QPushButton` / `QToolButton` MUST call
   `setCursor(Qt.CursorShape.PointingHandCursor)`** when the control is
   **enabled and meant to be clicked**.  If the button is
   `setEnabled(False)` (e.g. **Cancel** while a runner is idle), use
   `Qt.CursorShape.ArrowCursor` so the pointer does not look clickable.
   This applies to icon-only buttons, outline buttons, primary buttons,
   link buttons, toolbar buttons, and dialog buttons.
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
  Glyphs on `dangerButton` (e.g. debug **Stop** in `DebugControls`) must use
  `color=COLOR_WHITE` so they contrast the red fill (`COLOR_WHITE` tracks
  `ThemePalette["bg"]` — white in light theme, near-black in dark).
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
   (`COLOR_ACCENT`, `COLOR_TEXT`, etc.).  The code editor palette includes
   `editor_breakpoint_unreachable` for breakpoint dots on lines where the
   step-debugger cannot pause (nested callbacks).

### objectName conventions for styling

Widgets use `setObjectName()` to opt into global QSS rules.  These are the
standard object names:

| objectName | Widget type | Visual role |
|---|---|---|
| `primaryButton` | `QPushButton` | Accent-coloured action button (label + icon use ``solid_button_fg`` in QSS; Phosphor icons: ``phi(..., color=COLOR_SOLID_BUTTON_FG)``) |
| `environmentEditorSaveVarsButton` | `QPushButton` | **Environments** tab: compact **Save Variables** (accent + hover; disabled until vars differ from last save) |
| `dangerButton` | `QPushButton` | Red destructive action |
| `smallPrimaryButton` | `QPushButton` | Compact accent button |
| `outlineButton` | `QPushButton` | Border-only button |
| `iconButton` | `QPushButton` | Icon-only square button (no padding) |
| `iconDangerButton` | `QPushButton` | Icon-only button with danger-red hover |
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
| `methodBadge` | `QLabel` | HTTP method badge (request tree + request tabs) |
| `monoEdit` | `QTextEdit` | Monospace text editor |
| `consoleOutput` | `QTextEdit` | Dark console output area |
| `importTabs` | `QTabWidget` | Box-style tabs in import dialog |
| `codeEditor` | `QPlainTextEdit` | Syntax-highlighted code editor |
| `scriptEditorToolbarChrome` | `QWidget` | Script editor toolbar host: find/run row (6px top / 8px bottom inset) |
| `scriptEditorDebugStatusLabel` | `QLabel` | ``Paused at line N …`` on ``scriptEditorStatusBar`` after char count; hidden when not debugging |
| `scriptOutputDebugControls` | `DebugControls` | Breakpoint tools + separator + **Start debug** (idle) + continue/step/stop; step buttons disabled until pause |
| `debugBreakpointToolbarButton` | `QPushButton` | Breakpoint toolbar actions (always enabled; `bg_alt` + full-contrast icons) |
| `breakpointsDialog` | `BreakpointsDialog` | JetBrains-style breakpoints manager (920×620 default) |
| `breakpointsDialogTree` | `QTreeWidget` | Grouped breakpoint list (left pane) |
| `breakpointsDialogPreview` | `CodeEditorWidget` | Read-only code excerpt (right pane) |
| `scriptOutputDebuggerControlsSep` | `QFrame` | 1px rule under step controls (inside ``scriptOutputDebuggerFrame``) |
| `scriptToolbarSeparator` | `QFrame` | 1×20px vertical rule between toolbar icon groups |
| `scriptEditorOutputSplitter` | `QSplitter` | Scripts tab: vertical editor/output split — handle chrome suppressed; full-width line from ``scriptSplitFullWidthLine`` |
| `scriptSplitFullWidthLine` | `QFrame` | Non-layout 1px overlay on ``RequestEditorWidget`` / ``FolderEditorWidget`` / ``LocalScriptEditorWidget`` — spans host width; aligned to ``scriptEditorOutputSplitter`` seam when Scripts (or local script tab) is shown |
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
| `scriptHistoryLinkButton` | `QToolButton` | Script editor status strip: version history (accent underlined link) |
| `scriptLanguageLinkButton` | `QToolButton` | Script editor status strip: language picker (accent underlined link) |
| `scriptOutputTabs` | `QTabWidget` | Script panel: **Output**, **Debugger**, **Problems (n)**, **Iterations** (data file + matrix), **Mock response**; Run/Run all focus Output, Debug focuses Debugger; Problems title shows diagnostic count; ``::pane`` uses **6px** top padding under the tab bar |
| `scriptOutputDebuggerPage` | `QWidget` | Debugger tab page (layout host) |
| `scriptOutputDebuggerFrame` | `QFrame` | Bordered debugger surface (``DebugInspectorSplit``); matches ``scriptOutputScroll`` chrome |
| `scriptOutputIterationsPage` | `QWidget` | Iterations tab page — **DataRunnerPanel** above the results matrix |
| `scriptRunBusyOverlay` | `QWidget` | Indeterminate progress overlay on the script editor during inline run/debug |
| `dataRunnerPreviewTable` | `QTableWidget` | DataRunnerPanel — first N CSV/JSON rows preview |
| `scriptOutputIterationsTable` | `QTableWidget` | Iterations tab — iteration×test pass/fail matrix |
| `scriptMockResponseSection` | `QWidget` | Mock response tab page — bottom border matches Output page (global QSS) |
| `scriptLspProblemsList` | `QListWidget` | Problems tab: severity **Phosphor** icons + tinted text; click jumps; context **Copy**; ``_ScriptProblemsItemDelegate`` — square **1px** accent border + light selection tint (no ``HighlightedText`` wash-out) |
| `scriptLspProblemsEmptyFrame` | `QFrame` | Problems tab empty state — same border / ``input_bg`` as the list (global QSS) |
| `sidebarSearch` | `QLineEdit` | Collection sidebar search input |
| `sidebarSectionLabel` | `QLabel` | Sidebar section heading |
| `scriptTreeRenameEdit` | `QLineEdit` | Local script inline rename: full ``basename.ext`` field over the name column |
| `sidebarSectionInfoButton` | `QToolButton` | Sidebar section (i) icon; opens ``SidebarSectionInfoPopup`` |
| `infoPopupCloseButton` | `QToolButton` | Dismiss (×) control on ``SidebarSectionInfoPopup`` header |
| `sidebarToolButton` | `QToolButton` | Sidebar toolbar button |
| `environmentSidebarPanel` | `QWidget` | MainWindow left column: environments section under collections |
| `environmentSidebarScroll` | `QScrollArea` | Environment list viewport (no frame) |
| `environmentSidebarList` | `QWidget` | Bordered list frame (background + border QSS) |
| `environmentSidebarListBody` | `QWidget` | Inner host for rows (shimmed inside the frame so hover does not clip the border) |
| `environmentSidebarRow` | `QWidget` | One environment row (hover like collection tree) |
| `environmentSidebarNameLabel` | `QLabel` | Environment name in sidebar list |
| `environmentSidebarRowIcon` | `QLabel` | Globe icon beside each environment name |
| `environmentSidebarEmptyHint` | `ClickableLabel` | Empty list: "Click here to add one." (same action as **Manage**) |
| `environmentSidebarSetActiveButton` | `QPushButton` | Choose this environment for variable substitution |
| `environmentSidebarClearButton` | `QPushButton` | Clear global active environment (shown on active row) |
| `localScriptsSidebarPanel` | `QWidget` | Left flyout **Local scripts** page: section header + scroll + bordered list shell |
| `localScriptsSidebarScroll` | `QScrollArea` | Local scripts list viewport (no frame) |
| `localScriptsSidebarList` | `QWidget` | Bordered list frame (background + border QSS) |
| `localScriptsSidebarListBody` | `QWidget` | Inner host inside the list frame |
| `snippetsSidebarPanel` | `QWidget` | Left flyout snippets section (under local scripts splitter) |
| `snippetsSidebarScroll` | `QScrollArea` | Snippets list viewport |
| `snippetsSidebarList` | `QWidget` | Bordered snippets list frame |
| `snippetsSidebarListBody` | `QWidget` | Inner host for `snippetsTree` (padded like environments list) |
| `snippetsTree` | `QTreeWidget` | Snippets tree; `SnippetsTreeDelegate` paints language/snippet rows |
| `snippetsTree` | `QTreeWidget` | Snippets flyout: language → category → snippet |
| `userSnippetLabel` | `QLabel` | Accent-colored user snippet name (snippet picker only) |
| `newItemPopup` | `QDialog` | Postman-style "Create New" dialog |
| `newItemTile` | `QPushButton` | Tile button inside the new-item dialog |
| `settingsDenoPathEdit` | `QLineEdit` | Scripting: Deno executable path |
| `settingsDenoStatusLabel` | `QLabel` | Scripting: Deno validation / status line |
| `settingsDenoDownloadBtn` | `QPushButton` | Scripting: download managed Deno |
| `settingsDenoDownloadProgress` | `QProgressBar` | Scripting: Deno download progress |
| `settingsDenoAutodetectBtn` | `QPushButton` | Scripting: clear custom Deno path (auto-detect) |
| `settingsPythonPathEdit` | `QLineEdit` | Scripting: Python executable path |
| `settingsPythonStatusLabel` | `QLabel` | Scripting: Python validation / status line |
| `newItemTileLabel` | `QLabel` | Tile label text inside the dialog |
| `newItemTitle` | `QLabel` | Dialog heading ("What do you want to create?") |
| `newItemDescription` | `QLabel` | Description text below tiles |
| `collectionTree` | `QTreeWidget` | Collection tree in SaveRequestDialog |
| `mainWindowHorizontalSplitter` | `QSplitter` | Main horizontal splitter (left rail + flyouts + centre); thin hairline handles via global QSS |
| `sidebarRail` | `QWidget` | Always-visible icon rail (RightSidebar widget) |
| `sidebarRailButton` | `QToolButton` | Checkable icon button in the right rail |
| `leftSidebarRail` | `QWidget` | Left activity rail: background uses palette ``status_bar_bg`` (same as ``QStatusBar#appStatusBar``); no outer layout padding |
| `leftSidebarRailButton` | `QToolButton` | Rail icon (``_LeftRailButton``): width ``round(LEFT_RAIL_WIDTH_EM * em)``, icon ``round(LEFT_RAIL_ICON_EM * em)``, height ``icon_size + LEFT_RAIL_BUTTON_EXTRA_HEIGHT_PX``; checked left accent **painted** full height (``LEFT_RAIL_ACCENT_STRIPE_WIDTH_PX``); QSS margin/padding ``0`` |
| `sidebarPanelArea` | `QWidget` | Right sidebar collapsible flyout panel (separate splitter child) |
| `leftSidebarFlyout` | `QWidget` | Left collections flyout: ``border-left`` vs rail only; right edge uses the main splitter handle (no ``border-right``, avoids a double line when open). At 0 width uses a local ``setStyleSheet`` to strip chrome. Nav horizontal inset lives on ``CollectionWidget`` / ``EnvironmentSidebarPanel`` (``LEFT_NAV_PANEL_MARGIN_H_*`` in ``theme.py``) so the collections|environments splitter handle is not inset. |
| `sidebarTitleLabel` | `QLabel` | Bold panel title in **right** flyout header; debug panel position label (left flyout has no title row) |
| `variableKeyLabel` | `QLineEdit` | Variable key (read-only, selectable) in variables / debug KV rows |
| `variableValueLabel` | `QLineEdit` | Variable value preview (read-only, selectable); long values use a collapsible row in legacy KV rows |
| `variableValueEditor` | `QPlainTextEdit` | Expanded full value in collapsible KV rows (flat debug locals) |
| `kvValueExpandToggle` | `QToolButton` | Phosphor caret; expands long KV values (flat locals path; see ``phi`` in ``icons.py``) |
| `sidebarSourceDot` | `QLabel` | Colour-coded variable source dot |
| `sidebarSeparator` | `QFrame` | Separator line in sidebar panels |
| `completionPopup` | `QFrame` | Code editor autocomplete popup container |
| `completionPopupList` | `QListWidget` | Completion item list inside popup |
| `completionPopupDoc` | `QLabel` | Selected-item doc/signature label |
| `snippetsPopup` | `QFrame` | Script snippet palette (search + list) |
| `snippetsSearch` | `QLineEdit` | Filter field inside the snippet palette |
| `snippetsList` | `QListWidget` | Grouped snippet rows inside the palette |
| `parameterHintPopup` | `QFrame` | Code editor parameter-info tooltip (`Ctrl+P` when cursor is inside a call, also after typing `(`) |
| `parameterHintPopupLabel` | `QLabel` | Rich-text signature inside the parameter hint |
| `symbolDocPopup` | `QFrame` | Code editor quick-doc tooltip (`Ctrl+Q`, `Ctrl+hover`, `Ctrl+click` on `pm.*`) |
| `symbolDocPopupLabel` | `QLabel` | Rich-text body inside the symbol quick-doc popup |
| `debugHoverValueTree` | `QTreeWidget` | Paused-script debug hover: expandable object inspector (Name / Value columns) |
| `debugInspectorSplitter` | `QSplitter` | Horizontal split: call stack (left) \| watch strip + unified tree (right) |
| `debugInspectorVSeparator` | `QFrame` | Full-height 1px overlay on the horizontal splitter seam |
| `debugInspectorSeparator` | `QFrame` | 1px rule between watch strip and ``debugScopesTree`` |
| `debugCallStackList` | `QListWidget` | Stack frame list (left column) |
| `debugScopesTree` | `QTreeWidget` | Watches section + scope variables (right column) |
| `debugScopesTree` | `QTreeWidget` | Scope variable sections only (right column); header hidden |
| `debugVariablesTree` | `QTreeWidget` | Legacy alias in QSS (same styling as watches/scopes trees) |
| `debugWatchAddEdit` | `QLineEdit` | Watch expression add field above scopes (+/− icon buttons) |
| `debugShowInternalsCheck` | `QCheckBox` | Watches-strip toggle to show/hide internal ``__pm_*`` debug globals |
| `debugWatchRowValueHost` | `QWidget` | Watch row value column host (value label + trash, full width) |
| `debugWatchRowRemoveButton` | `QPushButton` | Per-watch trash at the right edge of the value column |
| `debugTreeCellLabel` | `QLabel` | Per-cell name/value in debug trees (``TextSelectableByMouse``; section rows use native painting) |
| `RuntimeBanner` | `QFrame` | Deno download prompt banner container |
| `bannerMessage` | `QLabel` | Banner message text |
| `bannerDownloadBtn` | `QPushButton` | "Download Deno" action button |
| `keyValueTable` | `QTableWidget` | Key-value tables (Params, Headers, etc.): clearer grid/header borders |
| `keyValueBulkPageHeader` | `QFrame` | Bulk mode: header strip above the text editor (``Key-value edit`` right) |
| `keyValueBulkEnter` | `QPushButton` | Key-value table: ``Bulk`` accent link + list icon in header → bulk text editor |
| `keyValueBulkEdit` | `QTextEdit` | Key-value bulk editor (monospace; ``:`` / ``=`` lines, ``//`` disabled) |
| `keyValueCheckCell` | `QWidget` | Key-value table checkbox cell wrapper: left edge (widget cells omit gridlines) |
| `assertionsHelpRow` | `QWidget` | Assertions tab: heading + **How it works** button (`assertionsHowItWorksButton`) |
| `assertionsHowItWorksButton` | `QPushButton` | Opens `AssertionsHelpDialog` (outline-style, question icon) |
| `assertionsHelpBody` | `QTextBrowser` | Selectable HTML help text in the assertions guide dialog |
| `assertionsTab` | `QWidget` | Declarative assertion editor (subject/operator/expected rows) |

**URL ↔ Params sync (`RequestEditorWidget`):** The URL bar holds the
canonical query string; the Params `KeyValueTableWidget` mirrors it via
``_on_url_text_changed_sync`` / ``_on_params_changed_sync`` (helpers in
``ui.widgets.query_string`` — brace-aware ``{{…}}`` parsing; flag-style
segments without ``=`` round-trip via row ``flag``). On load, if the URL
contains ``?``, parse the query into the table (disabled rows from stored
params are kept at the bottom); otherwise promote enabled stored params
into the URL. Params bulk-edit mode sets the URL bar read-only and syncs
the query when leaving bulk (`bulk_mode_changed`). Do not build HTTP query
strings from ``get_params_text()`` or ``KeyValueTableWidget.to_text()`` —
use ``query_string.build_query`` / ``build_url_with_query``.

`RequestEditorWidget` and `FolderEditorWidget` call
`_update_runtime_banners()` at the end of their load/clear entry points
(`load_request` / `clear_request`, `load_collection` / `clear`) so the
Deno prompt appears after script text is applied under `_loading` (the
debounced check from `textChanged` is skipped while loading).  Language
combo changes also re-schedule the check.  The banner’s **Open Scripting
settings** link emits `open_scripting_settings_requested` on the editor
and opens ``SettingsDialog`` on the Scripting category.

### QTabBar overflow scroll buttons

When a `QTabWidget` has more tabs than fit, Qt shows left/right
`QToolButton` scroll arrows inside the `QTabBar`.  These are styled
globally in `global_qss.py` with:

- `background: input_bg`
- `border: 1px solid border` (sharp corners, `border-radius: 0`)
- `border-color: accent` on hover

Do **not** override or remove the default platform arrows.  Do **not**
add `border-radius`, `bg_alt` hover fills, or `image: none` rules.
The global rule is unscoped — it applies to every `QTabBar` in the app.

### When inline setStyleSheet() is still acceptable

Only use `setStyleSheet()` for **dynamic per-instance** styling that
varies at runtime and cannot be expressed with objectName selectors:

- Method badge background-color (varies by HTTP method)
- Status label colour (varies by HTTP status code)
- History row method colour
- Breadcrumb per-segment colour
- Spinner animation colours
- Drop-zone active hover overlay
- ``LeftSidebar`` flyout at **zero splitter width** — strips borders with a
  local sheet so they do not stack on the main splitter handle (global QSS
  ``bool`` dynamic-property selectors are unreliable here)

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
