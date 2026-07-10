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
- `phi_qss_image_url(name, color=…, size=…)` writes a cached PNG under the app
  cache dir and returns `url(postmark-qss:…)` for Qt stylesheet `image` rules
  (e.g. `QSpinBox::up-arrow`). CSS border triangles and `data:` URLs do not work
  on spinbox arrows in QSS.
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
| `smallPrimaryButton` | `QPushButton` | Compact accent button (text: `padding: 4px 12px`; icon-only chat send/stop sets dynamic `iconOnly=true` → `padding: 0` — QSS padding is inset under `setFixedSize` and does not space the button from parent edges; use layout `contentsMargins`) |
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
| `aiModelsSearch` | `QLineEdit` | Settings → AI → Models page search filter |
| `aiModelsTree` | `QTreeWidget` | Settings → AI → Models tree; provider header rows use `bg_alt` background |
| `aiProviderActionsButton` | `QPushButton` | Borderless gear at the far right of the models tree **Capabilities** column on provider rows (opens `aiProviderActionsMenu`) |
| `aiProviderActionsMenu` | `QMenu` | Gear menu on provider rows; selected items use accent + white text/icons (`phi_menu`) |
| `aiProviderDialogSeparator` | `QFrame` | Horizontal rule between Connection and Models found in add/edit provider dialog |
| `aiProviderModelsListPanel` | `QFrame` | Bordered container for the models preview list in add/edit provider dialog |
| `aiProviderModelsList` | `QListWidget` | Model preview list inside `aiProviderModelsListPanel` (frameless; border on panel) |
| *(none)* | — | Settings → AI → Models capability pills are painted by `AiModelsTreeDelegate` (`ui/widgets/ai_models_tree_delegate.py`), not QLabel widgets |
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
| `sidebarRail` | `QWidget` | Always-visible icon rail (RightSidebar widget); no ``border-left`` (flyout ``sidebarPanelArea`` ``border-right`` is the only seam) |
| `sidebarRailButton` | `QToolButton` | Checkable icon button in the right rail |
| `leftSidebarRail` | `QWidget` | Left activity rail: background uses palette ``status_bar_bg`` (same as ``QStatusBar#appStatusBar``); no outer layout padding |
| `leftSidebarRailButton` | `QToolButton` | Rail icon (``_LeftRailButton``): width ``round(LEFT_RAIL_WIDTH_EM * em)``, icon ``round(LEFT_RAIL_ICON_EM * em)``, height ``icon_size + LEFT_RAIL_BUTTON_EXTRA_HEIGHT_PX``; checked left accent **painted** full height (``LEFT_RAIL_ACCENT_STRIPE_WIDTH_PX``); QSS margin/padding ``0`` |
| `sidebarPanelArea` | `QWidget` | Right sidebar collapsible flyout panel (separate splitter child); title bar has no close button (collapse via rail toggle, splitter drag, or Ctrl+B); open width ``RIGHT_FLYOUT_OPEN_WIDTH_EM`` × em, min width ``RIGHT_FLYOUT_MIN_WIDTH_EM`` × em; ``border-right`` vs icon rail only — left edge is ``mainWindowHorizontalSplitter`` handle (no ``border-left``); right-sidebar installs an event filter on that splitter handle so AI pane resize coalescing starts on mouse press before transcript child layout is queried |
| `aiChatSessionTitleBar` | `QWidget` | Conversation title row in flyout chrome (below ``sidebarTitleLabel``, above ``sidebarSeparator``): text-hugging ``aiChatSessionTitleSlot`` left, optional ``aiChatActiveRunsBadge`` count pill when any chat runs are in flight, checkable session-history + new chat ``iconButton``s right; visible only when AI panel is open |
| `aiChatActiveRunsBadge` | `QLabel` | Accent pill between session title and history button; ``{n} active`` when ``ChatRunRegistry.count_running() > 0``; updated via ``RightSidebar.set_ai_active_run_count`` |
| `aiChatSessionTitleSlot` | `QWidget` | Expanding left-aligned host for the inline title group; empty space to the right is not hoverable |
| `aiChatSessionTitleInline` | `QWidget` | Tight group around elided ``aiChatSessionTitle`` + ``aiChatSessionTitlePencil``; gentle ``ai_session_title_hover_bg`` pill on hover (`titleHovered` dynamic property) |
| `aiChatSessionTitle` | `QLabel` | Elided single-line session title; full text in tooltip; click to rename; placeholder ``New chat`` when no active session; updated via ``RightSidebar.set_ai_session_title`` |
| `aiChatSessionTitlePencil` | `QLabel` | Muted ``pencil-simple`` icon shown on hover immediately after the title text when rename is enabled |
| `aiChatSessionTitleEdit` | `QLineEdit` | Inline rename editor; Enter, Escape, or click-away saves via ``RightSidebar.ai_session_title_renamed`` |
| `aiChatPanel` | `QWidget` | Right-sidebar AI assistant chat (transcript + composer) |
| `aiChatScroll` | `QScrollArea` | Transcript scroll; horizontal scrollbar policy **AlwaysOff**; inner host is `_TranscriptMessages` (width is pinned exactly to the viewport with matching minimum/maximum width, and both `sizeHint()` and `minimumSizeHint()` are capped to the viewport so vertical scrollbar appearance cannot force horizontal overflow); `_messages_layout` uses horizontal `SetNoConstraint` plus vertical `SetMinAndMaxSize` for normal flow so wide code blocks cannot make Qt widen the scroll child. The leading spacer is inert, and only the final trailing stretch may expand to absorb non-scrollable viewport slack after all transcript rows. Viewport fill is the `QScrollArea`'s job (`widgetResizable=True`); scroll anchoring is handled only by scrollbar values plus `aiChatStreamingViewportSpacer`. During a locked stream, begin-stream and chunk-flush paths run as scroll-layout transactions: scrollbar signals are blocked while markdown/activity/spacer geometry changes, then `_stream_follow_target()` is committed before intermediate `rangeChanged` / `valueChanged` states can paint. `aiChatStreamingViewportSpacer` exists only when `turn_scroll_headroom > 0`; its target height is `max(0, viewport_h - content_min + turn_scroll_headroom)` where headroom is `anchor_y - 8` (+ 32px sticky scroll slack when anchor is below the top margin), and it is trimmed against `_max_transcript_min_height_px()` (viewport + headroom). If an active/completed short turn only exceeds the viewport by layout slack, `_reconcile_short_turn_transcript_height()` may temporarily set `_messages_layout` to horizontal `SetNoConstraint` plus vertical `SetFixedSize` and pin `_messages` to the viewport; transaction-safe 0ms/16ms finalizers catch late Qt range recalculation, and `_clear_streaming_viewport_spacer()` restores normal auto height before the next turn so fixed sizing cannot leak. Thinking-only streams follow the turn start unless the user scrolls to the bottom during the stream (`_stream_thinking_bottom_follow`), in which case follow stays at `bar.maximum()` until answer content starts; once the active turn genuinely exceeds the viewport, content-phase follow switches to the document bottom. Programmatic/streaming scroll uses instant `_set_bar_value` (cancels `SmoothScroller`); user upward movement detaches scroll lock; `aiChatScrollDown` stays hidden while locked. Session transcript restore keeps bottom-pin retries active for late user-row width reflow and lazy markdown range growth; persisted user rows that re-sync height while `_pending_transcript_bottom_scroll` is true schedule another bottom retry. `_turn_scroll_anchor` persists after stream end for completed short-turn positioning; pane resize coalesces markdown reflow (`_resize_active` + 75ms settle timer); `_sticky_turn_pairs` / `_sticky_turn_extents` cache turn geometry for the sticky overlay, and `_sync_sticky_turn_prompt()` applies the read-only clone only after layout/scroll transactions settle. |
| `aiChatStickyLabelHost` | `QWidget` | Transcript-style label host inside sticky user bubble (`aiChatUserMessageText` + `aiChatUserMessageFade`); used for collapsed preview and expanded fits without internal scroll |
| `aiChatStickyScroll` | `QScrollArea` | Internal scroll inside `StickyUserPromptOverlay` (`_StickyInnerScrollArea`); only shown when expanded and content exceeds label budget; hosts `aiChatStickyLabelHost` at full content height; scrollbar visually hidden (wheel scroll + boundary forward to `aiChatScroll`); `composer_bg` viewport |
| `aiChatStickyTurnPrompt` | `StickyUserPromptOverlay` | Viewport overlay for newest eligible user prompt; deterministic `measure_for_width()` + `apply_geometry()` (manual child layout, not `ChatMessageBubble` row layout); during inline edit (`_ChatPanelInlineEditMixin._sync_inline_edit_sticky_host`) hosts the live `AiChatComposer` via `overlay_edit_host.py` (`host_inline_composer` / `release_inline_composer` / `measure_edit_for_width` / `apply_edit_geometry`) when the edited user bubble scrolls off-screen; collapsed preview uses `aiChatStickyLabelHost` max-height clamp (like transcript `UserMessageSection`); expanded overflow uses `aiChatStickyScroll`; overlay owns expand/collapse independently of transcript rows; Show more/less triggers `_on_sticky_overlay_expanded_changed()` geometry resync only (does not mutate anchor); ≥3px viewport right inset; up to 4px further left than transcript anchor (falls back to assistant row when user bubble evicted); collapsed max height 35% viewport (`aiChatUserMessageFade` on preview), expanded 60%; turn selection uses `_MIN_STICKY_HEIGHT_ESTIMATE_PX` before final height fit; hidden when the **newest** turn's user bubble is visible near the viewport top (older on-screen user rows are skipped, not global blockers), when the selected anchor is visible near the top, when the assistant row does not intersect the viewport, or when the turn answer scrolled past; `_iter_orphan_sticky_turns()` supplies evicted-user metadata from `_evicted_turn_users`; each `_sync_sticky_turn_prompt()` rebuilds `_sticky_turn_extents` from live layout; `load_transcript` + `_finish_load_transcript_layout` rebuild turn-pair cache and hook all assistant `layout_height_changed` for sticky resync; `aiChatScrollDown` stays above |
| `aiChatUserMessageFade` | `QWidget` | Bottom gradient fade on height-clamped user bubbles (sticky overlay tall prompts) |
| `aiChatStreamingViewportSpacer` | `QWidget` | Dynamic-height transparent spacer inserted before the final trailing stretch only when the active turn needs non-zero scroll headroom (`max(0, viewport_h - content_min + turn_scroll_headroom)`; cleared when `turn_extent >= viewport_h`, `turn_scroll_headroom <= 0`, or target height ≤ 2px; recomputed inside locked stream layout transactions). Active locked streams update spacer height exactly (no min-delta threshold) and commit the scrollbar target before unblocking scrollbar signals so the user prompt does not step while small chunks arrive. `_trim_viewport_spacer_overflow()` shaves slack above `_max_transcript_min_height_px()` (viewport + headroom), zeroing the spacer first when overflow exceeds its height before recomputing. Retained after `end_assistant_stream` when the completed turn is shorter than one viewport and has headroom; cleared on long answers, transcript load/clear, and before the next user message when no stream is active |
| `aiChatScrollDown` | `QPushButton` | Floating scroll-to-bottom affordance on transcript viewport when user scrolls away; hidden while `_open_stream_generation > 0` and `_scroll_lock_enabled` (even when follow pins turn-start instead of bottom) |
| `aiChatMessageUser` | `QFrame` | Full-width user message bubble (`composer_bg`; `border-radius: 5px`; child of `ChatMessageBubble`); transcript user rows and their user frame use vertical `Fixed` size policy plus `sync_user_message_height_constraint()` so viewport slack cannot inflate the bubble or wrapped label. `AiChatPanel.add_message()` applies the constraint immediately and once more with a 0ms timer after Qt assigns the final row width. User-row `ChatMessageBubble.sizeHint()` / `minimumSizeHint()` use `_transcript_row_layout_width()` (parent width minus `_messages` horizontal margins) and `_user_frame_layout_margins()` for inner label width plus wrapped natural label height + chrome; `UserMessageSection.natural_label_height_for_width()` prefers the laid-out `aiChatUserMessageText` width when available |
| `aiChatUserMessageText` | `QLabel` | Word-wrapped user prompt inside the user bubble; wheel events forward to transcript `QScrollArea` |
| `aiChatUserMessageToggle` | `QPushButton` | Show more/less control for long user prompts (`UserMessageSection`); clickable on sticky overlay clone |
| `aiChatUserMessageFooter` | `QWidget` | Timestamp + action row under the user prompt; layout contentsMargins supply top/bottom inset (QSS padding on QWidget does not affect layout geometry) |
| `aiChatUserMessageConfig` | `QPushButton` | User message footer action: curved-arrow **message actions** (`footerMode="actions"`) opens `aiUserMessageActionsPopup`; while a run is in flight the active turn swaps to ``smallPrimaryButton`` styling with shared ``chat_stop_icon()`` (same as composer stop) and emits `AiChatPanel.stop_requested` |
| `aiChatUserMessageTime` | `QLabel` | Muted send-time label inside `aiChatUserMessageFooter` (left-aligned); set from `sent_at` on send or `created_at` on `load_transcript` |
| `aiUserMessageActionsPopup` | `QFrame` | Flyout for user message actions (Edit message display-only, Fork chat); follows transcript scroll |
| `aiUserMessageActionRow` | `QWidget` | One static action row inside `aiUserMessageActionsPopup` |
| `aiUserMessageActionLabel` | `QLabel` | Action label inside `aiUserMessageActionRow` |
| `aiChatAssistantRow` | `QWidget` | Assistant transcript row (`ChatMessageBubble`); thought collapse during scroll-locked streaming calls `_follow_streaming_turn_layout()` (viewport spacer + scroll re-anchor) instead of pinning a monotonic `_stream_row_floor_px`; `clear_stream_layout_floor()` on `end_assistant_stream` |
| `aiChatAssistantMessageFooter` | `QWidget` | Metadata row below completed assistant turns: model/cost left, ⋯ menu right |
| `aiChatAssistantUsageLabel` | `QLabel` | Model name + per-turn USD cost (when priced) inside `aiChatAssistantMessageFooter` |
| `aiChatAssistantMessageMenu` | `QPushButton` | Three-dot menu opening `aiAssistantMessageActionsPopup` |
| `aiAssistantMessageActionsPopup` | `QFrame` | Flyout for assistant actions (Copy message, Fork chat); follows transcript scroll |
| `aiAssistantMessageActionRow` | `QWidget` | One clickable action row inside `aiAssistantMessageActionsPopup` |
| `aiAssistantMessageActionLabel` | `QLabel` | Action label inside `aiAssistantMessageActionRow` |
| `aiChatAssistantText` | `QWidget` (`MarkdownContent`) | Assistant answer: static `QTextDocument` paint; dashed footer rule painted below content when turn complete; default I-beam cursor over prose, pointing hand over markdown links and fenced-code **Copy**; `postmark://request|collection|script|tab|history|environment|saved_response/<id>` deep-links (optional `?focus=test`, `body`, etc.) emit `workspace_target_requested` to open/focus centre tabs — malformed/non-numeric `postmark://` paths are swallowed (never `QDesktopServices`); `https://` links still open externally; mouse drag / double-click word / Ctrl+C selection with highlight; drag-select past the transcript viewport edge auto-scrolls the ancestor `QScrollArea` via a repeating timer that stops at scroll min/max when no movement is possible (plain `verticalScrollBar().setValue`, not panel `_set_bar_value`, so scroll-lock detaches during streaming); incremental `StreamingMarkdownCache` while streaming (pipe-table cells render inline markdown during streaming, including provisional trailing open spans like `**JavaScript` until the closing marker arrives; apply this to committed rows and the provisional tail row); full `render_chat_markdown_html` on finalize; re-renders on `ThemeManager.theme_changed`; width/height measure cache (`_cached_height_for_text_width`); defers expensive height sync during pane resize coalescing (`set_reflow_deferred` / `flush_deferred_reflow`); fenced-code **Copy** links (`postmark-code-copy:<index>`) use `copy_block_index_at_document_pos` (anchor + padded line-geometry hit); hover/**Copied** styling via `_sync_copy_link_appearance` (`QTextCharFormat` merge on the anchor — no `setHtml` on hover); when changing Copy/Copied text, mutate anchor spans in descending document-position order so changed label length cannot shift later spans and erase other fence headers; `WA_Hover` + mouse tracking, `enterEvent`, and transcript scroll hooks; click copies raw fence source and shows **Copied** ~2s; other link clicks via `anchorAt` when not selecting; context-menu **Copy** (selection) and **Copy message** (markdown source); wheel events forward to transcript `QScrollArea` |
| `aiChatThoughtBlock` | `QFrame` | Collapsible thinking section above assistant answer (collapsed by default after answer) |
| `aiChatThoughtToggle` | `QPushButton` | Thought header (`Thought for Ns`; click to expand/collapse); toggling emits `ThoughtSection.layout_height_changed` → `ChatMessageBubble.layout_height_changed`; panel compensates scroll so the answer below stays visually stable |
| `aiChatThoughtText` | `QLabel` | Muted thinking trace inside the thought block; wheel events forward to transcript `QScrollArea`. Uses `_WrappingLabel` height-for-width measurement with a large bounding-rect height; never measure wrapped text with a zero-height rectangle or streaming thought text clips after the first visual line. Before measuring streamed thought growth, `ThoughtSection` releases the prior `setFixedHeight()` clamp and activates its local layout so the next height-for-width query uses the current label width |
| `aiChatActivityRow` | `QWidget` | Spinner + status caption while waiting for the first stream token; hidden while subagent cards are active (cards are the loader) |
| `aiChatActivitySpinner` | `QLabel` | Braille spinner in the activity row (reuses `busyChipSpinner` QSS) |
| `aiChatActivityLabel` | `QLabel` | Muted activity caption (`Thinking…`, SDK status, long-wait escalation, subagent aggregate) |
| `aiChatSubagentGroup` | `QWidget` (`SubagentTaskGroup`) | Vertical stack of subagent summary cards between thought block(s) and assistant markdown |
| `aiChatSubagentCard` | `QFrame` (`SubagentTaskCard`) | Compact subagent row: sharp corners, accent border on hover (`cardHovered`); title, agent type, status; click opens detail dialog |
| `aiChatSubagentHeader` | `QWidget` | Title row container; minimum height follows wrapped `aiChatSubagentLabel` |
| `aiChatSubagentTitleIcon` | `QLabel` | Cpu icon left of the card title |
| `aiChatSubagentLabel` | `_WrappingLabel` | Bold wrapped task title in the card header |
| `aiChatSubagentOpenIcon` | `QLabel` | Open-in-window affordance on the card header |
| `aiChatSubagentStatusLabel` | `QLabel` | Muted status caption (`Starting` / `Running` / `Completed` / `Failed`) |
| `aiChatSubagentDetailDialog` | `QDialog` (`SubagentDetailDialog`) | Non-modal window: title + type chip + colored status pill; conditional Task callout (hidden when same as title); live Activity steps (lightbulb steps filtered — reasoning in Thought block only) with inline detail previews; collapsible Thought block; markdown reply; footer **Copy message** + Close; one `load_subagent_disk_snapshot` read per refresh when `disk_path` is set |
| `aiChatSubagentDetailTypeChip` | `QLabel` | Muted agent-type label in the detail dialog header |
| `aiChatSubagentDetailStatusPill` | `QWidget` | Status badge container; dynamic `status` property (`completed` / `error` / `running` / `warming`) |
| `aiChatSubagentDetailStatusIcon` | `QLabel` | Colored status icon inside the pill |
| `aiChatSubagentDetailStatusText` | `QLabel` | Status caption inside the pill; dynamic `status` property drives text color |
| `aiChatSubagentDetailCopy` | `QPushButton` | Footer control — copies reply markdown to clipboard |
| `aiChatSubagentDetailClose` | `QPushButton` | Footer Close control with ``x`` icon (outline styling) |
| `aiChatSubagentDetailTask` | `QLabel` | Read-only task callout (left-border quote style); hidden when redundant with title |
| `aiChatSubagentDetailActivity` | `QWidget` | Activity step list container between Task and Thought (hidden when empty) |
| `aiChatSubagentDetailThoughtScroll` | `QScrollArea` | Scroll cap for expanded subagent Thought body (`_THOUGHT_BODY_MAX_PX`) |
| `aiChatSubagentDetailThoughtScrollViewport` | `QWidget` | Thought scroll viewport; explicit no-border override |
| `aiChatSubagentDetailStepRow` | `QWidget` | One icon + summary (+ optional detail preview) row in the Activity list |
| `aiChatSubagentDetailStepIcon` | `QLabel` | Phosphor icon for an activity step |
| `aiChatSubagentDetailStepSummary` | `QLabel` | Wrapped activity summary; full `detail` also shown as tooltip |
| `aiChatSubagentDetailStepDetail` | `QLabel` | Muted one-line inline preview of step `detail` |
| `aiChatSubagentDetailScroll` | `QScrollArea` | Scroll container for subagent reply markdown; no right border (overrides `sidebarPanelArea QScrollArea`) |
| `aiChatSubagentDetailScrollViewport` | `QWidget` | Scroll viewport for subagent reply; explicit no-border override |
| `aiChatAssistantText` | `MarkdownContent` | Subagent reply body in the detail dialog (same renderer as assistant rows) |
| `aiChatTranscriptLoading` | `QWidget` (`ChatTranscriptLoadingOverlay`) | Viewport overlay with indeterminate line animation while a session transcript loads; hidden after `_finish_load_transcript_layout` |
| `aiChatOlderLoadingRow` | `QWidget` (`TranscriptOlderLoadingRow`) | In-transcript top row with spinner + **Fetching older messages…** while a silent older page loads; hidden after `apply_older_page` |
| `aiChatVirtualSpacer` | `QWidget` | Invisible fixed-height placeholder for evicted transcript rows (top/bottom virtual window); evicted user rows cache prompt metadata in `_evicted_turn_users` for sticky overlay |
| `aiChatTranscriptLoadingBar` | `QWidget` | Sliding accent segment on the session-load track |
| `aiChatTranscriptLoadingLabel` | `QLabel` | Muted caption under the session-load line (`Loading conversation…`) and on `aiChatOlderLoadingRow` |
| `aiChatComposer` | `QWidget` | AI chat bottom composer (attachments + input + controls); `WA_StyledBackground` + `composer_bg` (darker than transcript `bg`, lighter than `aiChatModeButton` `composer_pill_dark_bg`); input uses `input_bg`; shared by docked panel and inline edit (`AiChatComposer`) |
| `aiChatComposerInline` | `QWidget` | Embedded inline-edit composer inside `aiChatMessageUser` — transparent, no outer border |
| `aiChatInputInline` | `QPlainTextEdit` | Borderless prompt editor when embedded in a user bubble |
| `aiChatEditCancel` | `QPushButton` | Cancel control in inline edit mode (`AiChatComposer.set_edit_mode`) — pill with border |
| `aiChatInput` | `QPlainTextEdit` | AI chat prompt (`_ComposerInput`); auto-grows 3..15 lines then scrolls; Enter send, Shift+Enter newline |
| `aiChatModeButton` | `QFrame` | Agent / Ask / Plan pill; `WA_StyledBackground` + `composer_pill_dark_bg`; opens `aiAgentModePopup` |
| `aiChatModeButtonLabel` | `QLabel` | Mode label inside the mode pill |
| `aiAgentModePopup` | `QFrame` | Agent mode flyout (above mode pill; click-away + Escape) |
| `aiAgentModeOption` | `QWidget` | Selectable row in the mode flyout |
| `aiChatModelButton` | `QWidget` | `ModelPickerButton` — compact pill (`bg_alt`); opens model picker |
| `aiChatContextRing` | `QWidget` | `ContextUsageRingButton` — circular context fill; opens breakdown popup |
| `aiChatContextPopupMode` | `QPushButton` | Context / Spend mode pills inside the context flyout |
| `aiChatContextPopup` | `QFrame` | `AiChatContextUsagePopup` — context breakdown or session spend (Spend tab) |
| `aiChatBudgetBanner` | `QFrame` | `AiChatBudgetBanner` — soft/hard budget warning above composer; Settings link |
| `aiChatBudgetStatusCard` | `QFrame` | Spend flyout connection budget card (period spend vs soft/hard caps) |
| `aiProviderBudgetsTree` | `QTableWidget` | Settings → AI → Budgets provider rows; resizable columns (`ui/ai_budget_table_header/v4`) |
| `aiAgentsConcurrentRunsSpin` | `QSpinBox` | Settings → AI → Agents advisory concurrent-run threshold |
| `aiAgentsConcurrentRunsLabel` | `QLabel` | Settings → AI → Agents concurrent-run row label |
| `aiAgentsMaxParallelSubagentsSpin` | `QSpinBox` | Settings → AI → Agents hard cap for parallel `delegate` subagents per turn (QSettings `ai/max_parallel_subagents`) |
| `aiBudgetActionsButton` | `QPushButton` | Per-row gear — opens `aiBudgetConnectionDialog` |
| `aiBudgetConnectionDialog` | `QDialog` | Tabbed limits + spend editor; scoped QSS on schedule pickers + `aiBudgetLimitSpin` |
| `aiBudgetConnectionTabs` | `QTabWidget` | **Limits** + **Spend details**; box tabs (same QSS as `importTabs`) |
| `aiBudgetLimitsTab` | `QWidget` | Limits tab body |
| `aiBudgetSpendDetailsPanel` | `BudgetSpendDetailsPanel` | Spend tab body: intro, summary card, column headers, model rows |
| `aiBudgetSpendSummaryCard` | `QFrame` | This period / All time totals matching the Budgets table |
| `aiBudgetSpendDetailsHeader` | `QWidget` | Model / Tokens / Cost column labels |
| `aiBudgetSpendModelRow` | `QWidget` | One all-time model row with separator border |
| `aiBudgetSoftLimitEnable` | `QCheckBox` | Enable soft limit in connection dialog |
| `aiBudgetHardLimitEnable` | `QCheckBox` | Enable hard limit in connection dialog |
| `aiBudgetLimitSpin` | `QDoubleSpinBox` | USD limit amount in connection dialog |
| `aiBudgetPeriodCombo` | `QComboBox` | Reset period inside connection dialog |
| `aiBudgetResetTime` | `QTimeEdit` | Local reset time (hour/minute) |
| `aiBudgetResetWeekday` | `QComboBox` | Weekly reset weekday |
| `aiBudgetResetMonth` | `QComboBox` | Yearly reset month |
| `aiBudgetResetDay` | `QSpinBox` | Monthly/yearly reset day |
| `aiBudgetPeriodResetPanel` | `QWidget` | Period + reset schedule block in connection dialog |
| `aiBudgetResetSchedule` | `QWidget` | Reset schedule rows container |
| `aiBudgetStatusLabel` | `QLabel` | Budget validation error line |
| `aiBudgetEmptyLabel` | `QLabel` | Budgets page empty state |
| `aiChatSummarizedNotice` | `QWidget` | Muted one-line transcript notice after OpenHands compaction |
| `aiChatModelButtonPart` | `QLabel` | Model name and ``·`` separators inside `aiChatModelButton` |
| `aiModelPickerContext` | `QLabel` | Context tag inside model button and picker rows (muted 10px) |
| `aiModelPickerEffort` | `QLabel` | Reasoning tag inside model button and picker rows (muted 10px) |
| `aiModelPickerPopup` | `QFrame` | Frameless model picker popover (search row + list) |
| `aiModelPickerSearch` | `QLineEdit` | Model picker filter field |
| `aiModelPickerList` | `QListWidget` | Model picker model rows |
| `aiModelPickerName` | `QLabel` | Model label inside a picker row |
| `aiModelPickerEdit` | `QPushButton` | Hover Edit button opening the settings flyout |
| `aiModelPickerEditPanel` | `QFrame` | Cursor-style categorized flyout (context / thinking / reasoning) |
| `aiModelPickerEditSection` | `QLabel` | Section heading inside the edit flyout |
| `aiModelPickerEditOption` | `QWidget` | Selectable row in the edit flyout |
| `aiModelPickerEditOptionLabel` | `QLabel` | Option label inside an edit row |
| `aiModelPickerEditCheck` | `QLabel` | Trailing checkmark on the selected option |
| `aiModelPickerRow` | `QWidget` | Model row; `editing=true` while its edit flyout is open |
| `aiModelPickerPillSwitch` | `QWidget` | Painted pill toggle for thinking on/off |
| `aiModelPickerEditThinkingRow` | `QWidget` | Thinking section row container |
| `aiModelPickerProvider` | `QLabel` | *(unused)* — provider shown as bold ``QListWidget`` group headers instead |
| `aiChatAttachments` | `QWidget` | Attachment chips row (hidden when empty) |
| `aiChatAttachmentChip` | `QPushButton` | Removable file attachment chip |
| `aiSessionHistoryPopup` | `QFrame` | Session history popover (title-row clock button); width ``AI_SESSION_HISTORY_POPUP_WIDTH_EM`` × em; async ``SessionListLoader`` + debounced SQL search |
| `aiSessionSearch` | `QLineEdit` | Session history search field |
| `aiSessionHistoryList` | `QListView` | Virtualized session list (`SessionHistoryListModel` + `SessionHistoryRowDelegate`); hover ⋯ opens actions flyout; fixed 44px row height |
| `aiSessionHistoryActionsPopup` | `QFrame` | Per-row Rename / Delete flyout from ⋯ menu (sharp corners) |
| `aiSessionHistoryActionRow` | `QWidget` | One action row inside ``aiSessionHistoryActionsPopup`` |
| `aiSessionHistoryActionLabel` | `QLabel` | Action label inside ``aiSessionHistoryActionRow`` |
| `requestHistoryPanel` | `HistoryPanel` | Per-request History flyout (right rail) |
| `globalHistoryPanel` | `HistoryPanel` | Workspace History flyout (left rail, 3rd button; `set_global_mode`) |
| `globalHistoryHeader` | `QWidget` | Left global History title row (History label + refresh) |
| `requestHistoryOpenButton` | `QPushButton` | Hidden; global History opens on tree single-click |
| `requestHistorySearch` | `QLineEdit` | Filter History by URL substring or status code (e.g. `200`) |
| `requestHistoryList` | `QStackedWidget` | Bordered list area (tree or no-match empty state) |
| `requestHistoryTree` | `QTreeWidget` | History tree inside `requestHistoryList` (date groups → sends) |
| `requestHistoryReplayButton` | `QPushButton` | Replay selected send (detail header; snapshot-only HTTP, response pane only) |
| `responseReplayIndicator` | `QFrame` | Response viewer corner pill when the current response is from a history replay |
| `responseReplayPrefix` | `QLabel` | Muted "Replayed request" label inside `responseReplayIndicator` |
| `responseReplayLink` | `ClickableLabel` | Link to open History and select the source row |
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

### AI chat transcript layout invariant

Transcript rows must stay in document order with normal `QVBoxLayout` row
spacing. `ChatMessageBubble` rows and their thought/activity/text children use
vertical `Fixed` size policies so viewport slack cannot inflate a row and
vertically center its text. Any viewport fill or stream headroom belongs after
the active assistant row only: use `aiChatStreamingViewportSpacer` when scroll
anchoring needs real content height, and the final transcript layout stretch for
non-scrollable slack. Never insert an expanding spacer before or between a user
row, thought header/body, and assistant answer body.

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
