# UI Layer

The UI layer is built with PySide6 (Qt 6 for Python).  All widgets live
under `src/ui/`.  The layer communicates with services via direct method
calls and with other widgets via Qt signals.

## MainWindow and Mixin Stack

`MainWindow` is assembled from four controller mixins that split
responsibilities:

```text
MainWindow
  inherits from:
    _SendPipelineMixin        HTTP send/response flow
    _VariableControllerMixin  Environment variable + sidebar management
    _DraftControllerMixin     Draft tab open/save lifecycle
    _TabControllerMixin       Tab open/close/switch/session
    QMainWindow               Qt base class
```

**MRO (Method Resolution Order):** Python resolves methods left-to-right
in the inheritance list.  The mixins are ordered so that specialised
behaviour (send pipeline) takes precedence.

**Signal wiring:** Inter-widget connections are made in
`MainWindow._build_full_ui()` (scheduled from `__init__`).  Widgets never
reference each other directly — they emit signals that MainWindow connects.

See [MainWindow Reference](../ui-reference/main-window.md) for the full
wiring map.

## Widget Hierarchy

```text
MainWindow (QMainWindow)
  +-- QAction (back / forward shortcuts only; no visible toolbar strip)
  +-- QSplitter (horizontal, main — left rail + nav flyout + centre content)
        +-- LeftSidebar (left activity rail)
        +-- QWidget (left flyout — vertical splitter only; no duplicate title row)
        |     +-- QSplitter (vertical, collections + environments)
        |           +-- CollectionWidget
        |           |     +-- CollectionHeader (search + new/import buttons)
        |           |     +-- CollectionTree (QTreeWidget subclass)
        |           |           +-- CollectionTreeDelegate (method badge renderer)
        |           +-- EnvironmentSidebarPanel (global env list + **Set active** / **Clear** per row)
        +-- QSplitter (horizontal — centre column + right flyout + right rail)
              +-- QSplitter (vertical — request + response + bottom)
              |     +-- RequestTabBar (wrapped multi-row tab deck)
              |     +-- BreadcrumbBar (path navigation)
              |     +-- QStackedWidget
              |           +-- RequestEditor (per-tab, stacked)
              |           +-- FolderEditorWidget (per-tab, stacked)
              |     +-- QStackedWidget
              |           +-- ResponseViewer (per-tab, stacked)
              +-- QWidget (_FlyoutPanel — right sidebar flyout)
              |     +-- VariablesPanel (read-only variable display)
              |     +-- SnippetPanel (code snippet generator)
              |     +-- SavedResponsesPanel (saved examples)
              +-- RightSidebar (right activity rail)
  +-- QTabWidget (bottom panels)
        +-- ConsolePanel (HTTP traffic log)
        +-- HistoryPanel (request history)
```

## Background Workers

Long-running operations use the QThread + moveToThread pattern to keep
the UI responsive:

```text
1. Create worker (QObject subclass with run() slot)
2. Create QThread
3. worker.moveToThread(thread)
4. Connect thread.started --> worker.run
5. Connect worker.finished --> cleanup + result handling
6. thread.start()
```

Workers in the codebase:

| Worker | Module | Purpose |
|--------|--------|---------|
| `HttpSendWorker` | `request/http_worker.py` | Execute HTTP request in background |
| `SchemaFetchWorker` | `request/http_worker.py` | Fetch GraphQL schema in background |
| `CollectionLoader` | `collections/collection_widget.py` | Load collection tree from DB |
| `ImportWorker` | `dialogs/import_dialog.py` | Run import pipeline in background |
| `RunnerWorker` | `dialogs/collection_runner/worker.py` | Run collection requests sequentially (used by folder inline runner) |

## Theming System

The theme system has four components:

1. **`theme.py`** — Defines `LIGHT_PALETTE` and `DARK_PALETTE` as
   `ThemePalette` TypedDicts.  Exports mutable module-level colour
   aliases (`COLOR_TEXT`, `COLOR_BORDER`, etc.) that are updated at
   runtime.  Also provides `method_color()`, `status_color()`, and
   badge geometry constants.

2. **`ThemeManager`** — Manages the active theme via QSettings.  Emits
   `theme_changed` signal.  `apply()` updates the module-level colour
   aliases in `theme.py` and rebuilds the global stylesheet.

3. **`global_qss.py`** — `build_global_qss()` generates a stylesheet
   string using current theme colours.  Widgets are targeted via
   `objectName` values.

4. **`icons.py`** — `phi(name, size, color)` renders Phosphor font
   glyphs as QIcons.  Uses the bundled Phosphor font from `data/fonts/`.

## Tab System

Tabs are managed by `TabManager` with per-tab state in `TabContext`:

```text
TabManager
  +-- _tabs: dict[int, TabContext]      Per-tab state
  +-- _deferred_tabs: dict[int, dict]   Lazy-loaded tabs from session restore

TabContext
  +-- tab_type: "request" | "folder" | "environments"
  +-- request_id: int | None
  +-- collection_id: int | None
  +-- editor: RequestEditor | None
  +-- folder_editor: FolderEditorWidget | None
  +-- environment_editor: EnvironmentEditorWidget | None
  +-- response_viewer: ResponseViewer | None
  +-- is_dirty: bool
  +-- is_sending: bool
  +-- is_preview: bool
  +-- draft_name: str | None
  +-- local_overrides: dict[str, LocalOverride]
  +-- opened_order: int
  +-- last_activated_order: int
```

## Settings System

`TabSettingsManager` persists request-tab behaviour preferences via
QSettings:

- Preview mode (single click opens preview, double click opens permanent)
- Tab limits (maximum open tabs)
- Activate-on-close policy (most recently used vs adjacent)
- Code editor wrap mode

Emits `settings_changed` signal when any setting changes.

## Signal Communication

Widgets communicate exclusively through signals.  Key patterns:

- **Widget emits, MainWindow receives** — e.g. `CollectionTree.item_action_triggered` →
  `MainWindow._on_item_action()`
- **Widget emits, sibling receives** (wired in MainWindow) — e.g.
  `RequestEditor.save_requested` → `MainWindow._on_save()`
- **Worker emits, MainWindow receives** — e.g. `HttpSendWorker.finished` →
  `MainWindow._on_response_received()`

See [Signal Reference](../api-reference/signals.md) for the complete
catalogue.
