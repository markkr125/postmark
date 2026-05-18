# Directory Structure

Complete annotated source and test tree.  Each entry describes the
file's purpose to help both human developers and AI agents navigate
the codebase quickly.

## Source Tree

```text
src/
+-- main.py                          Entry point -- QApplication + MainWindow bootstrap
+-- database/                        Engine, models, repository
|   +-- database.py                  init_db(), get_session(), forward-only migration
|   +-- models/
|       +-- base.py                  SQLAlchemy DeclarativeBase
|       +-- collections/
|       |   +-- collection_repository.py    CRUD: create/rename/delete/update collections + requests
|       |   +-- collection_query_repository.py  Read-only: tree fetch, breadcrumbs, auth chains, variables
|       |   +-- import_repository.py        Atomic bulk-import of parsed collection trees
|       |   +-- model/
|       |       +-- collection_model.py     CollectionModel -- folders in the collection tree
|       |       +-- request_model.py        RequestModel -- HTTP requests with body, headers, auth
|       |       +-- saved_response_model.py SavedResponseModel -- named response snapshots
|       +-- environments/
|           +-- environment_repository.py   CRUD: create/rename/delete/update environments
|           +-- model/
|               +-- environment_model.py    EnvironmentModel -- key-value variable sets
+-- services/                        Service layer (UI <-> DB bridge)
|   +-- collection_service.py        CollectionService (static methods) + RequestLoadDict, SavedResponseDict
|   +-- environment_service.py       EnvironmentService (variable substitution) + VariableDetail, LocalOverride
|   +-- import_service.py            ImportService (parse + persist via parsers + import_repository)
|   +-- http/                        HTTP request/response handling
|   |   +-- http_service.py          HttpService (httpx) + HttpResponseDict, TimingDict, NetworkDict
|   |   +-- graphql_schema_service.py  GraphQL introspection + schema parsing
|   |   +-- auth_handler.py          apply_auth() -- shared auth header injection (12 auth types)
|   |   +-- oauth2_service.py        OAuth2Service -- token exchange (4 grant types)
|   |   +-- header_utils.py          parse_header_dict() shared utility
|   |   +-- snippet_generator/       Code snippet generation sub-package
|   |       +-- generator.py         SnippetGenerator, SnippetOptions, LanguageEntry, registry
|   |       +-- shell_snippets.py    cURL, HTTP raw, wget, HTTPie, PowerShell
|   |       +-- dynamic_snippets.py  Python, JavaScript, Node.js, Ruby, PHP, Dart
|   |       +-- compiled_snippets.py Go, Rust, C, Swift, Java, Kotlin, C#
|   +-- import_parser/               Parser sub-package
|       +-- models.py                TypedDict schemas (ParsedCollection, ParsedRequest, ImportResult, etc.)
|       +-- postman_parser.py        Postman collection/environment/archive parser
|       +-- curl_parser.py           cURL command parser
|       +-- url_parser.py            URL/raw-text auto-detect parser
+-- ui/                              PySide6 widgets
    +-- loading_screen.py            Loading screen overlay
    +-- main_window/                 Top-level MainWindow sub-package
    |   +-- window.py                MainWindow widget + signal wiring
    |   +-- send_pipeline.py         _SendPipelineMixin -- HTTP send/response flow
    |   +-- draft_controller.py      _DraftControllerMixin -- draft tab open/save
    |   +-- tab_controller.py        _TabControllerMixin -- tab open/close/switch
    |   +-- variable_controller.py   _VariableControllerMixin -- env variable + sidebar management
    +-- sidebar/                     Sidebar rails + flyout panels
    |   +-- sidebar_widget.py        RightSidebar (icon rail) + _FlyoutPanel
    |   +-- left_sidebar.py          LeftSidebar — activity rail + collapsible nav flyout
    |   +-- variables_panel.py       VariablesPanel -- read-only variable display
    |   +-- snippet_panel.py         SnippetPanel -- inline code snippet generator
    |   +-- saved_responses/         Saved responses sub-package
    |       +-- panel.py             SavedResponsesPanel -- saved example list/detail flyout
    |       +-- search_filter.py     _PanelSearchFilterMixin -- body search/filter
    |       +-- helpers.py           Formatting helpers (body size, language detect)
    |       +-- delegate.py          Custom delegate for saved response list items
    +-- styling/                     Visual theming and icons
    |   +-- theme.py                 Palettes, colours, status bar / left-rail chrome, badge/tree geometry, left-nav panel margins, method_color(), status_color()
    |   +-- theme_manager.py         ThemeManager -- QPalette + QSettings
    |   +-- tab_settings_manager.py  TabSettingsManager -- request-tab QSettings bridge
    |   +-- global_qss.py           build_global_qss() -- global stylesheet builder
    |   +-- icons.py                 Phosphor font-glyph icon provider (phi())
    +-- widgets/                     Reusable shared components
    |   +-- code_editor/             CodeEditorWidget sub-package
    |   |   +-- editor_widget.py     CodeEditorWidget -- main editor class
    |   |   +-- highlighter.py       Syntax highlighting engine
    |   |   +-- folding.py           Code folding logic
    |   |   +-- gutter.py            Line-number gutter + minimap (_MinimapArea)
    |   |   +-- painting.py          Custom painting helpers
    |   |   +-- completion/          Autocomplete sub-package
    |   |       +-- schema/          Schema sub-package
    |   |       |   +-- core.py      SchemaNode TypedDict, expectation chain, shared helpers
    |   |       |   +-- js.py        JS_SCHEMA (pm, console, CryptoJS, postman) + JS_GLOBALS
    |   |       |   +-- py.py        PY_SCHEMA + PY_GLOBALS (Python variant)
    |   |       +-- engine.py        CompletionEngine -- dot-path/variable resolver + resolve_call_signature + resolve_nearest_call_signature + resolve_symbol/find_definition_pos/is_linkable_symbol (Ctrl+hover/Ctrl+click)
    |   |       +-- mixin.py         _CompletionMixin -- completion + parameter hint triggers + Ctrl+hover/click symbol-link handling
    |   |       +-- parameter_hint.py  ParameterHintPopup -- call signature tooltip
    |   |       +-- popup.py         CompletionPopup -- floating autocomplete widget
    |   |       +-- symbol_doc_popup.py  SymbolDocPopup -- Ctrl+hover/Ctrl+Q quick-doc tooltip
    |   +-- info_popup.py            InfoPopup (QFrame) base + ClickableLabel
    |   +-- key_value_column_widths.py  QSettings persistence for Key/Value column widths
    |   +-- key_value_bulk.py          Postman-style bulk text serialize/parse for key-value tables
    |   +-- key_value_table.py       Reusable key-value editor widget
    |   +-- key_value_table_delegate.py  Variable {{…}} highlight delegate
    |   +-- search_replace_bar.py    SearchReplaceBar -- find/replace + go-to-line for CodeEditorWidget
    |   +-- variable_line_edit.py    VariableLineEdit -- QLineEdit with {{var}} highlighting + popup
    |   +-- variable_popup.py        VariablePopup -- singleton hover popup for variable details
    +-- collections/                 Collection sidebar
    |   +-- collection_header.py     Header with new/import buttons + search
    |   +-- collection_widget.py     CollectionWidget -- main widget + background loading
    |   +-- new_item_popup.py        NewItemPopup -- Postman-style icon grid popup
    |   +-- tree/                    Tree widget sub-package
    |       +-- constants.py         Data role constants (ROLE_ITEM_ID, ROLE_ITEM_TYPE, etc.)
    |       +-- draggable_tree_widget.py  QTreeWidget subclass with drag-and-drop
    |       +-- collection_tree.py   CollectionTree widget
    |       +-- tree_actions.py      _TreeActionsMixin -- context menus, rename, delete
    |       +-- collection_tree_delegate.py  Custom delegate for method badges
    +-- dialogs/                     Modal dialogs
    |   +-- collection_runner/       Shared runner widgets + RunnerWorker (no modal shell)
    |   |   +-- __init__.py          Re-exports RunnerConfigView, RunnerResultsView, RunnerWorker
    |   |   +-- config.py            RunnerConfigView (env selector, request checklist, data file, iterations, delay)
    |   |   +-- results.py           RunnerResultsView (summary + results table + detail panel + export)
    |   |   +-- worker.py            RunnerWorker (QThread), parse_data_file, env var substitution
    |   +-- import_dialog.py         ImportDialog -- select format + import
    |   +-- save_request_dialog.py   SaveRequestDialog -- save draft to collection
    |   +-- settings_dialog.py       SettingsDialog -- theme + request-tab behaviour
    +-- environments/                Environment management widgets
    |   +-- environment_editor.py    EnvironmentEditorWidget + EnvironmentEditorDialog wrapper
    |   +-- environment_selector.py  EnvironmentSelector dropdown (dialogs / legacy)
    |   +-- environment_sidebar_panel.py  EnvironmentSidebarPanel — left column global env picker
    +-- panels/                      Bottom panels
    |   +-- console_panel.py         Console output panel
    |   +-- history_panel.py         Request history panel
    +-- request/                     Request/response editing
        +-- folder_editor/              Folder/collection detail editor sub-package
        |   +-- editor_widget.py        FolderEditorWidget -- main editor class
        |   +-- runner_panel.py         _RunnerPanel -- inline collection runner (Runs -> New run)
        |   +-- runs.py                 _RunsMixin + _build_runs_table (run history table)
        +-- http_worker.py           HttpSendWorker + SchemaFetchWorker (QThread)
        +-- auth/                    Shared auth sub-package (12 auth types)
        |   +-- auth_field_specs.py  Per-type FieldSpec definitions (AUTH_FIELD_SPECS dict)
        |   +-- auth_mixin.py        _AuthMixin -- shared by both editors
        |   +-- auth_pages.py        FieldSpec dataclass, page builders, auth constants
        |   +-- auth_serializer.py   Generic load/save for all auth types
        |   +-- oauth2_page.py       OAuth 2.0 custom page (grant-type switching)
        +-- request_editor/          RequestEditor sub-package
        |   +-- editor_widget.py     RequestEditor -- main request editing widget
        |   +-- auth.py              Re-export of _AuthMixin from auth sub-package
        |   +-- body_search.py       _BodySearchMixin -- search/replace in body
        |   +-- graphql.py           _GraphQLMixin -- GraphQL mode + schema
        +-- response_viewer/         ResponseViewer sub-package
        |   +-- viewer_widget.py     ResponseViewer -- response display widget
        |   +-- search_filter.py     _SearchFilterMixin -- response search/filter
        |   +-- test_results_mixin.py _TestResultsMixin -- test results tab
        |   +-- pre_request_mixin.py _PreRequestMixin -- pre-request script output tab
        +-- navigation/              Tab switching and path navigation
        |   +-- breadcrumb_bar.py    BreadcrumbBar widget
        |   +-- request_tab_bar.py   Compatibility wrapper re-exporting wrapped deck
        |   +-- tab_manager.py       TabManager + TabContext (local_overrides, draft_name)
        |   +-- request_tabs/        Wrapped multi-row request tab deck sub-package
        |       +-- bar.py           RequestTabBar custom wrapped-row deck
        |       +-- labels.py        TabLabel / FolderTabLabel chip content widgets
        |       +-- tab_button.py    TabButton chip with close + reorder interactions
        +-- popups/                  Response metadata popups
            +-- status_popup.py      HTTP status code explanation
            +-- timing_popup.py      Request timing breakdown
            +-- size_popup.py        Response/request size breakdown
            +-- network_popup.py     Network/TLS connection details
```

## Test Tree

```text
tests/
+-- conftest.py                      Autouse fresh-DB fixture + qapp fixture + tab-settings reset
+-- unit/                            Repository and service layer tests
|   +-- database/
|   |   +-- test_repository.py       Collection + request CRUD tests
|   |   +-- test_environment_repository.py  Environment CRUD tests
|   +-- services/
|       +-- test_service.py          CollectionService tests
|       +-- test_environment_service.py  EnvironmentService tests
|       +-- test_import_parser.py    Parser unit tests
|       +-- test_import_service.py   ImportService integration tests
|       +-- http/
|           +-- test_http_service.py          HttpService tests
|           +-- test_graphql_schema_service.py GraphQLSchemaService tests
|           +-- test_snippet_generator.py     SnippetGenerator tests
|           +-- test_snippet_shell.py         Shell snippet tests
|           +-- test_snippet_dynamic.py       Dynamic language snippet tests
|           +-- test_snippet_compiled.py      Compiled language snippet tests
|           +-- test_auth_handler.py          apply_auth() tests
|           +-- test_oauth2_service.py        OAuth2Service tests
+-- ui/                              End-to-end PySide6 widget tests
    +-- conftest.py                  _no_fetch (autouse) + helpers
    +-- test_main_window.py          MainWindow integration tests
    +-- test_main_window_tabs_navigation.py  Tab deck shortcuts + search
    +-- test_main_window_save.py     Save button + request save end-to-end
    +-- test_main_window_draft.py    Draft tab open/save lifecycle
    +-- test_main_window_session.py  Tab session persistence (save/restore)
    +-- styling/
    |   +-- test_theme_manager.py    ThemeManager tests
    |   +-- test_icons.py           Icon system tests
    +-- sidebar/
    |   +-- test_sidebar.py          RightSidebar tests
    |   +-- test_left_sidebar.py     LeftSidebar tests
    |   +-- test_variables_panel.py  VariablesPanel tests
    |   +-- test_snippet_panel.py    SnippetPanel tests
    |   +-- test_saved_responses_panel.py  SavedResponsesPanel tests
    +-- widgets/
    |   +-- test_code_editor.py      CodeEditorWidget tests
    |   +-- test_code_editor_folding.py  Folding tests
    |   +-- test_code_editor_painting.py Painting tests
    |   +-- test_code_editor_memory.py   Memory/performance tests
    |   +-- test_code_editor_minimap.py   Minimap tests
    |   +-- test_completion_engine.py    CompletionEngine tests
    |   +-- test_completion_popup.py     CompletionPopup tests
    |   +-- test_info_popup.py       InfoPopup tests
    |   +-- test_key_value_table.py  KeyValueTable tests
    |   +-- test_variable_line_edit.py  VariableLineEdit tests
    |   +-- test_variable_popup.py   VariablePopup tests
    |   +-- test_variable_popup_local.py  VariablePopup local override tests
    |   +-- test_search_replace_bar.py   SearchReplaceBar tests
    +-- collections/
    |   +-- test_collection_header.py    CollectionHeader tests
    |   +-- test_collection_tree.py      CollectionTree tests
    |   +-- test_collection_tree_actions.py  Tree context menu tests
    |   +-- test_collection_tree_delegate.py Delegate rendering tests
    |   +-- test_collection_widget.py    CollectionWidget tests
    |   +-- test_new_item_popup.py       NewItemPopup tests
    +-- dialogs/
    |   +-- test_import_dialog.py        ImportDialog tests
    |   +-- test_save_request_dialog.py  SaveRequestDialog tests
    |   +-- test_settings_dialog.py      SettingsDialog tests
    +-- environments/
    |   +-- test_environment_editor.py   EnvironmentEditor tests
    |   +-- test_environment_selector.py EnvironmentSelector tests
    |   +-- test_environment_sidebar_panel.py EnvironmentSidebarPanel tests
    +-- panels/
    |   +-- test_console_panel.py        ConsolePanel tests
    |   +-- test_history_panel.py        HistoryPanel tests
    +-- request/
        +-- conftest.py                  make_request_dict fixture factory
        +-- test_folder_editor.py        FolderEditorWidget tests
        +-- test_folder_editor_scripts.py Script editor, history, search tests
        +-- test_http_worker.py          HttpSendWorker tests
        +-- test_request_editor.py       RequestEditor tests
        +-- test_request_editor_auth.py  Auth tab tests
        +-- test_request_editor_binary.py Binary body tests
        +-- test_request_editor_graphql.py GraphQL mode tests
        +-- test_request_editor_search.py  Body search tests
        +-- test_response_viewer.py      ResponseViewer tests
        +-- test_response_viewer_search.py Response search tests
        +-- test_response_viewer_tests.py Test results tab tests
        +-- test_version_history.py       VersionHistoryDialog tests
        +-- navigation/
        |   +-- test_breadcrumb_bar.py   BreadcrumbBar tests
        |   +-- test_request_tab_bar.py  RequestTabBar tests
        |   +-- test_tab_manager.py      TabManager tests
        +-- popups/
            +-- test_status_popup.py     StatusPopup tests
            +-- test_timing_popup.py     TimingPopup tests
            +-- test_size_popup.py       SizePopup tests
            +-- test_network_popup.py    NetworkPopup tests
```
