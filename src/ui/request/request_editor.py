"""Editable request editor pane with method, URL, body mode, and tabbed details.

Emits ``send_requested`` when the Send button is clicked,
``save_requested`` when the user triggers a save, and
``request_changed`` (debounced) when any field is modified.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPalette, QShortcut, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.code_editor import CodeEditorWidget
from ui.icons import phi
from ui.key_value_table import KeyValueTableWidget
from ui.request.http_worker import SchemaFetchWorker
from ui.theme import COLOR_WARNING, method_color
from ui.variable_line_edit import VariableLineEdit

if TYPE_CHECKING:
    from services.environment_service import VariableDetail

# HTTP methods shown in the dropdown
_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

# Body mode identifiers
_BODY_MODES = ("none", "raw", "form-data", "x-www-form-urlencoded", "graphql", "binary")

# Raw body format sub-options
_RAW_FORMATS = ("Text", "JSON", "XML", "HTML")

# Authorization type identifiers
_AUTH_TYPES = ("No Auth", "Bearer Token", "Basic Auth", "API Key")

# Debounce delay (ms) for the request_changed signal
_DEBOUNCE_MS = 500

# Base names for the request editor section tabs (index-matched)
_TAB_NAMES = ("Params", "Headers", "Body", "Auth", "Description", "Scripts")

# Dot appended to tab label when the section has content
_CONTENT_DOT = " \u2022"


class _MethodColorDelegate(QStyledItemDelegate):
    """Paint each combo-box item in its HTTP method colour.

    Global QSS sets a fixed ``color`` on ``QComboBox`` which overrides
    ``ForegroundRole`` data.  This delegate injects the correct palette
    colour in :meth:`initStyleOption` so each row renders individually.
    """

    def initStyleOption(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        """Override text colour and font for each dropdown item."""
        super().initStyleOption(option, index)
        method = index.data(Qt.ItemDataRole.DisplayRole)
        if method:
            color = QColor(method_color(method))
            option.palette.setColor(QPalette.ColorRole.Text, color)
            option.palette.setColor(QPalette.ColorRole.HighlightedText, color)
            option.font.setBold(True)


class RequestEditorWidget(QWidget):
    """Editable request editor with method, URL bar, and tabbed sections.

    Call :meth:`load_request` to populate the pane from a request dict.
    Emits ``send_requested`` when the Send button is clicked.
    Emits ``save_requested`` when Ctrl+S is pressed.
    Emits ``request_changed`` (debounced) when any field is modified.
    """

    send_requested = Signal()
    save_requested = Signal()
    dirty_changed = Signal(bool)
    request_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the request editor layout."""
        super().__init__(parent)

        self._request_id: int | None = None
        self._is_dirty: bool = False
        self._loading: bool = False  # suppress signals during load_request
        self._schema_thread: QThread | None = None
        self._schema_worker: SchemaFetchWorker | None = None
        self._gql_schema: dict | None = None  # SchemaResultDict when fetched

        # Debounce timer for request_changed
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(_DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._emit_request_changed)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 0)
        root.setSpacing(10)

        # -- Top bar: method dropdown + URL + Send --
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        top_bar.setContentsMargins(0, 4, 0, 8)

        self._method_combo = QComboBox()
        self._method_combo.addItems(list(_HTTP_METHODS))
        self._method_combo.setItemDelegate(_MethodColorDelegate(self._method_combo))
        self._method_combo.setFixedWidth(100)
        self._method_combo.currentTextChanged.connect(self._on_field_changed)
        self._method_combo.currentTextChanged.connect(self._update_method_color)
        top_bar.addWidget(self._method_combo)
        self._update_method_color(self._method_combo.currentText())

        self._url_input = VariableLineEdit()
        self._url_input.setPlaceholderText("Enter request URL")
        self._url_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._url_input.textChanged.connect(self._on_field_changed)
        top_bar.addWidget(self._url_input)

        self._send_btn = QPushButton("Send")
        self._send_btn.setIcon(phi("paper-plane-right", color="#ffffff"))
        self._send_btn.setObjectName("primaryButton")
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setFixedWidth(90)
        self._send_btn.clicked.connect(self.send_requested.emit)
        top_bar.addWidget(self._send_btn)

        root.addLayout(top_bar)

        # -- Tabbed area: Params, Headers, Body, Scripts --
        self._tabs = QTabWidget()

        self._params_table = KeyValueTableWidget(
            placeholder_key="Parameter", placeholder_value="Value"
        )
        self._params_table.data_changed.connect(self._on_field_changed)
        self._tabs.addTab(self._params_table, "Params")

        self._headers_table = KeyValueTableWidget(
            placeholder_key="Header", placeholder_value="Value"
        )
        self._headers_table.data_changed.connect(self._on_field_changed)
        self._tabs.addTab(self._headers_table, "Headers")

        # Body tab with mode selector
        self._body_tab = QWidget()
        body_layout = QVBoxLayout(self._body_tab)
        body_layout.setContentsMargins(0, 6, 0, 0)

        # Body mode radio buttons
        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        self._body_mode_group = QButtonGroup(self)
        self._body_mode_buttons: dict[str, QRadioButton] = {}
        for mode in _BODY_MODES:
            rb = QRadioButton(mode)
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            self._body_mode_buttons[mode] = rb
            self._body_mode_group.addButton(rb)
            mode_row.addWidget(rb)
            rb.toggled.connect(self._on_body_mode_changed)
        self._body_mode_buttons["none"].setChecked(True)
        mode_row.addStretch()

        body_layout.addLayout(mode_row)

        # -- Body find/replace bar (Ctrl+F / Ctrl+H) -------------------
        self._body_search_bar = QWidget()
        bsearch_outer = QVBoxLayout(self._body_search_bar)
        bsearch_outer.setContentsMargins(0, 4, 0, 0)
        bsearch_outer.setSpacing(2)

        # Row 1: Find
        find_row = QHBoxLayout()
        find_row.setSpacing(4)

        self._replace_toggle_btn = QPushButton()
        self._replace_toggle_btn.setIcon(phi("caret-right"))
        self._replace_toggle_btn.setFixedSize(24, 24)
        self._replace_toggle_btn.setToolTip("Toggle Replace")
        self._replace_toggle_btn.setObjectName("iconButton")
        self._replace_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._replace_toggle_btn.setCheckable(True)
        self._replace_toggle_btn.clicked.connect(self._toggle_replace_row)
        find_row.addWidget(self._replace_toggle_btn)

        self._body_search_input = QLineEdit()
        self._body_search_input.setPlaceholderText("Find in body\u2026")
        self._body_search_input.textChanged.connect(self._on_body_search_text_changed)
        find_row.addWidget(self._body_search_input, 1)

        self._body_search_count_label = QLabel("")
        self._body_search_count_label.setObjectName("mutedLabel")
        find_row.addWidget(self._body_search_count_label)

        bsearch_prev = QPushButton()
        bsearch_prev.setIcon(phi("caret-up"))
        bsearch_prev.setFixedSize(24, 24)
        bsearch_prev.setToolTip("Previous match")
        bsearch_prev.setObjectName("iconButton")
        bsearch_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        bsearch_prev.clicked.connect(self._body_search_prev)
        find_row.addWidget(bsearch_prev)

        bsearch_next = QPushButton()
        bsearch_next.setIcon(phi("caret-down"))
        bsearch_next.setFixedSize(24, 24)
        bsearch_next.setToolTip("Next match")
        bsearch_next.setObjectName("iconButton")
        bsearch_next.setCursor(Qt.CursorShape.PointingHandCursor)
        bsearch_next.clicked.connect(self._body_search_next)
        find_row.addWidget(bsearch_next)

        bsearch_close = QPushButton()
        bsearch_close.setIcon(phi("x"))
        bsearch_close.setFixedSize(24, 24)
        bsearch_close.setToolTip("Close search")
        bsearch_close.setObjectName("iconButton")
        bsearch_close.setCursor(Qt.CursorShape.PointingHandCursor)
        bsearch_close.clicked.connect(self._close_body_search)
        find_row.addWidget(bsearch_close)

        bsearch_outer.addLayout(find_row)

        # Row 2: Replace (hidden until toggled)
        self._replace_row = QWidget()
        replace_layout = QHBoxLayout(self._replace_row)
        replace_layout.setContentsMargins(28, 0, 0, 0)  # indent past chevron
        replace_layout.setSpacing(4)

        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText("Replace with\u2026")
        replace_layout.addWidget(self._replace_input, 1)

        self._replace_one_btn = QPushButton()
        self._replace_one_btn.setIcon(phi("swap"))
        self._replace_one_btn.setFixedSize(24, 24)
        self._replace_one_btn.setToolTip("Replace current match")
        self._replace_one_btn.setObjectName("iconButton")
        self._replace_one_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._replace_one_btn.clicked.connect(self._replace_one)
        replace_layout.addWidget(self._replace_one_btn)

        self._replace_all_btn = QPushButton()
        self._replace_all_btn.setIcon(phi("checks"))
        self._replace_all_btn.setFixedSize(24, 24)
        self._replace_all_btn.setToolTip("Replace all matches")
        self._replace_all_btn.setObjectName("iconButton")
        self._replace_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._replace_all_btn.clicked.connect(self._replace_all)
        replace_layout.addWidget(self._replace_all_btn)

        self._replace_row.hide()
        bsearch_outer.addWidget(self._replace_row)

        self._body_search_bar.hide()
        body_layout.addWidget(self._body_search_bar)

        self._body_search_matches: list[int] = []
        self._body_search_index: int = -1
        self._body_search_editor: CodeEditorWidget | None = None

        # Body content stack (switches per mode)
        self._body_stack = QStackedWidget()

        # Page 0: None mode — empty state label
        none_page = QLabel("This request has no body.")
        none_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        none_page.setObjectName("emptyStateLabel")
        self._body_stack.addWidget(none_page)

        # Page 1: Raw / GraphQL — code editor with toolbar
        raw_page = QWidget()
        raw_layout = QVBoxLayout(raw_page)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.setSpacing(4)

        raw_toolbar = QHBoxLayout()
        raw_toolbar.setSpacing(6)
        self._prettify_btn = QPushButton("Pretty")
        self._prettify_btn.setIcon(phi("magic-wand", color="#ffffff"))
        self._prettify_btn.setObjectName("smallPrimaryButton")
        self._prettify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prettify_btn.clicked.connect(self._on_prettify)
        raw_toolbar.addWidget(self._prettify_btn)

        self._wrap_btn = QPushButton("Wrap")
        self._wrap_btn.setIcon(phi("text-align-left"))
        self._wrap_btn.setObjectName("outlineButton")
        self._wrap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wrap_btn.setCheckable(True)
        self._wrap_btn.setChecked(True)
        self._wrap_btn.clicked.connect(self._on_wrap_toggle)
        raw_toolbar.addWidget(self._wrap_btn)

        # Raw format dropdown (visible only when mode is "raw")
        self._raw_format_combo = QComboBox()
        self._raw_format_combo.addItems(list(_RAW_FORMATS))
        self._raw_format_combo.setFixedWidth(80)
        self._raw_format_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._raw_format_combo.currentTextChanged.connect(self._on_field_changed)
        self._raw_format_combo.currentTextChanged.connect(self._update_body_language)
        self._raw_format_combo.hide()
        raw_toolbar.addWidget(self._raw_format_combo)

        self._body_error_label = QLabel()
        self._body_error_label.setObjectName("mutedLabel")
        self._body_error_label.hide()
        raw_toolbar.addWidget(self._body_error_label)

        raw_toolbar.addStretch()

        raw_layout.addLayout(raw_toolbar)

        self._body_code_editor = CodeEditorWidget()
        self._body_code_editor.textChanged.connect(self._on_field_changed)
        self._body_code_editor.validation_changed.connect(self._on_body_validation)
        raw_layout.addWidget(self._body_code_editor, 1)
        self._body_stack.addWidget(raw_page)

        # Page 2: form-data / x-www-form-urlencoded — key-value table
        self._body_form_table = KeyValueTableWidget(
            placeholder_key="Key", placeholder_value="Value"
        )
        self._body_form_table.data_changed.connect(self._on_field_changed)
        self._body_stack.addWidget(self._body_form_table)

        # Page 3: Binary — file picker
        binary_page = QWidget()
        binary_layout = QVBoxLayout(binary_page)
        binary_layout.setContentsMargins(0, 8, 0, 0)
        self._binary_file_btn = QPushButton("Select File")
        self._binary_file_btn.setIcon(phi("file"))
        self._binary_file_btn.setObjectName("outlineButton")
        self._binary_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._binary_file_btn.setFixedWidth(120)
        self._binary_file_btn.clicked.connect(self._on_select_binary_file)
        binary_layout.addWidget(self._binary_file_btn)
        self._binary_file_label = QLabel("No file selected.")
        self._binary_file_label.setObjectName("mutedLabel")
        binary_layout.addWidget(self._binary_file_label)
        binary_layout.addStretch()
        self._body_stack.addWidget(binary_page)

        # Page 4: GraphQL — split-pane query + variables editors
        gql_page = QWidget()
        gql_layout = QVBoxLayout(gql_page)
        gql_layout.setContentsMargins(0, 0, 0, 0)
        gql_layout.setSpacing(4)

        # GraphQL toolbar (Pretty / Wrap)
        gql_toolbar = QHBoxLayout()
        gql_toolbar.setSpacing(6)
        self._gql_prettify_btn = QPushButton("Pretty")
        self._gql_prettify_btn.setIcon(phi("magic-wand", color="#ffffff"))
        self._gql_prettify_btn.setObjectName("smallPrimaryButton")
        self._gql_prettify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gql_prettify_btn.clicked.connect(self._on_gql_prettify)
        gql_toolbar.addWidget(self._gql_prettify_btn)

        self._gql_wrap_btn = QPushButton("Wrap")
        self._gql_wrap_btn.setIcon(phi("text-align-left"))
        self._gql_wrap_btn.setObjectName("outlineButton")
        self._gql_wrap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gql_wrap_btn.setCheckable(True)
        self._gql_wrap_btn.setChecked(True)
        self._gql_wrap_btn.clicked.connect(self._on_gql_wrap_toggle)
        gql_toolbar.addWidget(self._gql_wrap_btn)

        self._gql_error_label = QLabel()
        self._gql_error_label.setObjectName("mutedLabel")
        self._gql_error_label.hide()
        gql_toolbar.addWidget(self._gql_error_label)

        gql_toolbar.addStretch()

        self._gql_schema_label = QPushButton("No schema")
        self._gql_schema_label.setObjectName("outlineButton")
        self._gql_schema_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gql_schema_label.setFlat(True)
        self._gql_schema_label.clicked.connect(self._on_schema_label_clicked)
        gql_toolbar.addWidget(self._gql_schema_label)

        self._gql_fetch_schema_btn = QPushButton()
        self._gql_fetch_schema_btn.setIcon(phi("arrow-clockwise"))
        self._gql_fetch_schema_btn.setObjectName("outlineButton")
        self._gql_fetch_schema_btn.setToolTip("Fetch schema via introspection")
        self._gql_fetch_schema_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gql_fetch_schema_btn.setFixedWidth(30)
        self._gql_fetch_schema_btn.clicked.connect(self._on_fetch_schema)
        gql_toolbar.addWidget(self._gql_fetch_schema_btn)

        gql_layout.addLayout(gql_toolbar)

        gql_splitter = QSplitter(Qt.Orientation.Horizontal)
        gql_splitter.setObjectName("gqlSplitter")
        gql_splitter.setHandleWidth(8)

        # Left pane: QUERY
        gql_query_pane = QWidget()
        gql_query_layout = QVBoxLayout(gql_query_pane)
        gql_query_layout.setContentsMargins(0, 0, 0, 0)
        gql_query_layout.setSpacing(2)
        gql_query_label = QLabel("QUERY")
        gql_query_label.setObjectName("sectionLabel")
        gql_query_layout.addWidget(gql_query_label)
        self._gql_query_editor = CodeEditorWidget()
        self._gql_query_editor.set_language("graphql")
        self._gql_query_editor.textChanged.connect(self._on_field_changed)
        self._gql_query_editor.validation_changed.connect(self._on_gql_validation)
        gql_query_layout.addWidget(self._gql_query_editor, 1)
        gql_splitter.addWidget(gql_query_pane)

        # Right pane: GRAPHQL VARIABLES
        gql_vars_pane = QWidget()
        gql_vars_layout = QVBoxLayout(gql_vars_pane)
        gql_vars_layout.setContentsMargins(0, 0, 0, 0)
        gql_vars_layout.setSpacing(2)
        gql_vars_label = QLabel("GRAPHQL VARIABLES")
        gql_vars_label.setObjectName("sectionLabel")
        gql_vars_layout.addWidget(gql_vars_label)
        self._gql_variables_editor = CodeEditorWidget()
        self._gql_variables_editor.set_language("json")
        self._gql_variables_editor.textChanged.connect(self._on_field_changed)
        gql_vars_layout.addWidget(self._gql_variables_editor, 1)
        gql_splitter.addWidget(gql_vars_pane)

        # Default 60/40 split ratio
        gql_splitter.setStretchFactor(0, 3)
        gql_splitter.setStretchFactor(1, 2)

        gql_layout.addWidget(gql_splitter, 1)
        self._body_stack.addWidget(gql_page)

        body_layout.addWidget(self._body_stack, 1)

        self._tabs.addTab(self._body_tab, "Body")

        # Auth tab with type selector
        self._auth_tab = QWidget()
        auth_layout = QVBoxLayout(self._auth_tab)
        auth_layout.setContentsMargins(0, 6, 0, 0)

        auth_type_row = QHBoxLayout()
        auth_type_row.setSpacing(8)
        auth_type_label = QLabel("Type:")
        auth_type_label.setObjectName("sectionLabel")
        auth_type_row.addWidget(auth_type_label)

        self._auth_type_combo = QComboBox()
        self._auth_type_combo.addItems(list(_AUTH_TYPES))
        self._auth_type_combo.setFixedWidth(140)
        self._auth_type_combo.currentTextChanged.connect(self._on_auth_type_changed)
        auth_type_row.addWidget(self._auth_type_combo)
        auth_type_row.addStretch()
        auth_layout.addLayout(auth_type_row)

        # Auth fields stack
        self._auth_fields_stack = QStackedWidget()

        # No Auth page (empty)
        no_auth_page = QLabel("This request does not use any authorization.")
        no_auth_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        no_auth_page.setObjectName("emptyStateLabel")
        self._auth_fields_stack.addWidget(no_auth_page)

        # Bearer Token page
        bearer_page = QWidget()
        bearer_layout = QVBoxLayout(bearer_page)
        bearer_layout.setContentsMargins(0, 8, 0, 0)
        token_label = QLabel("Token")
        token_label.setObjectName("sectionLabel")
        bearer_layout.addWidget(token_label)
        self._bearer_token_input = VariableLineEdit()
        self._bearer_token_input.setPlaceholderText("Enter bearer token")
        self._bearer_token_input.textChanged.connect(self._on_field_changed)
        bearer_layout.addWidget(self._bearer_token_input)
        bearer_layout.addStretch()
        self._auth_fields_stack.addWidget(bearer_page)

        # Basic Auth page
        basic_page = QWidget()
        basic_layout = QVBoxLayout(basic_page)
        basic_layout.setContentsMargins(0, 8, 0, 0)
        username_label = QLabel("Username")
        username_label.setObjectName("sectionLabel")
        basic_layout.addWidget(username_label)
        self._basic_username_input = VariableLineEdit()
        self._basic_username_input.setPlaceholderText("Username")
        self._basic_username_input.textChanged.connect(self._on_field_changed)
        basic_layout.addWidget(self._basic_username_input)
        password_label = QLabel("Password")
        password_label.setObjectName("sectionLabel")
        basic_layout.addWidget(password_label)
        self._basic_password_input = VariableLineEdit()
        self._basic_password_input.setPlaceholderText("Password")
        self._basic_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._basic_password_input.textChanged.connect(self._on_field_changed)
        basic_layout.addWidget(self._basic_password_input)
        basic_layout.addStretch()
        self._auth_fields_stack.addWidget(basic_page)

        # API Key page
        apikey_page = QWidget()
        apikey_layout = QVBoxLayout(apikey_page)
        apikey_layout.setContentsMargins(0, 8, 0, 0)
        key_label = QLabel("Key")
        key_label.setObjectName("sectionLabel")
        apikey_layout.addWidget(key_label)
        self._apikey_key_input = VariableLineEdit()
        self._apikey_key_input.setPlaceholderText("Header or query parameter name")
        self._apikey_key_input.textChanged.connect(self._on_field_changed)
        apikey_layout.addWidget(self._apikey_key_input)
        value_label = QLabel("Value")
        value_label.setObjectName("sectionLabel")
        apikey_layout.addWidget(value_label)
        self._apikey_value_input = VariableLineEdit()
        self._apikey_value_input.setPlaceholderText("API key value")
        self._apikey_value_input.textChanged.connect(self._on_field_changed)
        apikey_layout.addWidget(self._apikey_value_input)

        add_to_label = QLabel("Add to")
        add_to_label.setObjectName("sectionLabel")
        apikey_layout.addWidget(add_to_label)
        self._apikey_add_to_combo = QComboBox()
        self._apikey_add_to_combo.addItems(["Header", "Query Params"])
        self._apikey_add_to_combo.setFixedWidth(140)
        self._apikey_add_to_combo.currentTextChanged.connect(self._on_field_changed)
        apikey_layout.addWidget(self._apikey_add_to_combo)
        apikey_layout.addStretch()
        self._auth_fields_stack.addWidget(apikey_page)

        auth_layout.addWidget(self._auth_fields_stack, 1)
        self._tabs.addTab(self._auth_tab, "Auth")

        self._description_edit = QTextEdit()
        self._description_edit.setPlaceholderText("Add a description for this request\u2026")
        self._description_edit.textChanged.connect(self._on_field_changed)
        self._tabs.addTab(self._description_edit, "Description")

        self._scripts_edit = QTextEdit()
        self._scripts_edit.setPlaceholderText("Scripts")
        self._scripts_edit.textChanged.connect(self._on_field_changed)
        self._tabs.addTab(self._scripts_edit, "Scripts")

        # Let the tab content area shrink to just the tab header row so the
        # user can maximise the response viewer via the splitter.
        tab_header_h = self._tabs.tabBar().sizeHint().height()
        self._tabs.setMinimumHeight(tab_header_h + 4)
        self._tabs.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)

        root.addWidget(self._tabs, 1)

        # -- Empty state --
        self._empty_label = QLabel("Select a request to view its details.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("emptyStateLabel")
        root.addWidget(self._empty_label)

        # Start in empty state
        self._set_content_visible(False)

        # Platform-native Find shortcut (Cmd+F on macOS, Ctrl+F elsewhere).
        # Scoped to this widget tree so the response viewer's search bar
        # does not compete.
        self._body_find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self._body_find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._body_find_shortcut.activated.connect(self._toggle_body_search)

        # Ctrl+R / Cmd+R to open find-and-replace.
        self._body_replace_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        self._body_replace_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._body_replace_shortcut.activated.connect(self._toggle_body_replace)

    # -- Visibility helpers -------------------------------------------

    def _set_content_visible(self, visible: bool) -> None:
        """Toggle between the editor content and the empty-state label."""
        self._method_combo.setVisible(visible)
        self._url_input.setVisible(visible)
        self._send_btn.setVisible(visible)
        self._tabs.setVisible(visible)
        self._empty_label.setVisible(not visible)

    # -- Load / save / clear ------------------------------------------

    @property
    def request_id(self) -> int | None:
        """Return the database PK of the loaded request, or ``None``."""
        return self._request_id

    @property
    def is_dirty(self) -> bool:
        """Return whether the editor has unsaved changes."""
        return self._is_dirty

    def set_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Distribute the resolved variable map to all child widgets.

        This enables ``{{variable}}`` highlighting and resolved-value
        tooltips across the URL bar, auth fields, body editors, and
        key-value tables.
        """
        # Suppress dirty tracking — rehighlight can emit textChanged
        self._loading = True
        try:
            # URL bar
            self._url_input.set_variable_map(variables)
            # Auth fields
            self._bearer_token_input.set_variable_map(variables)
            self._basic_username_input.set_variable_map(variables)
            self._basic_password_input.set_variable_map(variables)
            self._apikey_key_input.set_variable_map(variables)
            self._apikey_value_input.set_variable_map(variables)
            # Key-value tables
            self._params_table.set_variable_map(variables)
            self._headers_table.set_variable_map(variables)
            self._body_form_table.set_variable_map(variables)
            # Code editors
            self._body_code_editor.set_variable_map(variables)
            self._gql_query_editor.set_variable_map(variables)
            self._gql_variables_editor.set_variable_map(variables)
        finally:
            self._loading = False

    def load_request(self, data: dict, *, request_id: int | None = None) -> None:
        """Populate the editor from a request data dict.

        Expected keys: ``name``, ``method``, ``url``, and optionally
        ``body``, ``request_parameters``, ``headers``, ``scripts``,
        ``body_mode``, ``body_options``.
        """
        self._loading = True
        try:
            self._request_id = request_id
            self._set_content_visible(True)

            method = data.get("method", "GET").upper()
            idx = self._method_combo.findText(method)
            if idx >= 0:
                self._method_combo.setCurrentIndex(idx)

            self._url_input.setText(data.get("url", ""))

            self._load_key_value_data(self._params_table, data.get("request_parameters"))
            self._load_key_value_data(self._headers_table, data.get("headers"))

            # Body mode
            body_mode = data.get("body_mode") or "none"
            btn = self._body_mode_buttons.get(body_mode)
            if btn:
                btn.setChecked(True)

            # Load body content into the correct widget
            body = data.get("body") or ""
            if body_mode in ("form-data", "x-www-form-urlencoded"):
                self._load_key_value_data(self._body_form_table, body or None)
                self._body_code_editor.setPlainText("")
            elif body_mode == "binary":
                self._binary_file_label.setText(body if body else "No file selected.")
                self._body_code_editor.setPlainText("")
            elif body_mode == "graphql":
                # Parse stored JSON: {"query": "...", "variables": ...}
                query_text = ""
                variables_text = ""
                if body:
                    try:
                        parsed = json.loads(body)
                        if isinstance(parsed, dict):
                            query_text = parsed.get("query", "")
                            raw_vars = parsed.get("variables", "")
                            if isinstance(raw_vars, dict):
                                variables_text = json.dumps(raw_vars, indent=4) if raw_vars else ""
                            elif isinstance(raw_vars, str):
                                variables_text = raw_vars
                        else:
                            # Not a dict — treat entire body as query text
                            query_text = body
                    except (json.JSONDecodeError, TypeError):
                        # Legacy plain-text GraphQL body
                        query_text = body
                self._gql_query_editor.setPlainText(query_text)
                self._gql_variables_editor.setPlainText(variables_text)
                self._body_code_editor.setPlainText("")
            else:
                self._body_code_editor.setPlainText(body)
                self._body_form_table.set_data([])

            # Raw format sub-option
            body_options = data.get("body_options") or {}
            raw_lang = (body_options.get("raw", {}) or {}).get("language", "text")
            lang_map = {"json": "JSON", "xml": "XML", "html": "HTML", "text": "Text"}
            self._raw_format_combo.setCurrentText(lang_map.get(raw_lang, "Text"))

            scripts = data.get("scripts")
            if isinstance(scripts, dict):
                self._scripts_edit.setPlainText(json.dumps(scripts, indent=4))
            elif scripts:
                self._scripts_edit.setPlainText(str(scripts))
            else:
                self._scripts_edit.setPlainText("")

            # Auth configuration
            auth = data.get("auth") or {}
            auth_type = auth.get("type", "noauth")
            auth_type_map = {
                "noauth": "No Auth",
                "bearer": "Bearer Token",
                "basic": "Basic Auth",
                "apikey": "API Key",
            }
            self._auth_type_combo.setCurrentText(auth_type_map.get(auth_type, "No Auth"))
            if auth_type == "bearer":
                bearer_list = auth.get("bearer", [])
                token = ""
                for entry in bearer_list:
                    if entry.get("key") == "token":
                        token = entry.get("value", "")
                self._bearer_token_input.setText(token)
            elif auth_type == "basic":
                basic_list = auth.get("basic", [])
                username = password = ""
                for entry in basic_list:
                    if entry.get("key") == "username":
                        username = entry.get("value", "")
                    elif entry.get("key") == "password":
                        password = entry.get("value", "")
                self._basic_username_input.setText(username)
                self._basic_password_input.setText(password)
            elif auth_type == "apikey":
                apikey_list = auth.get("apikey", [])
                key = value = ""
                add_to = "header"
                for entry in apikey_list:
                    if entry.get("key") == "key":
                        key = entry.get("value", "")
                    elif entry.get("key") == "value":
                        value = entry.get("value", "")
                    elif entry.get("key") == "in":
                        add_to = entry.get("value", "header")
                self._apikey_key_input.setText(key)
                self._apikey_value_input.setText(value)
                add_to_map = {"header": "Header", "query": "Query Params"}
                self._apikey_add_to_combo.setCurrentText(add_to_map.get(add_to, "Header"))

            # Description
            self._description_edit.setPlainText(data.get("description") or "")

            self._set_dirty(False)
        finally:
            self._loading = False
        self._sync_tab_indicators()

    def get_request_data(self) -> dict:
        """Return the current editor state as a dict suitable for saving."""
        body_mode = "none"
        for mode, btn in self._body_mode_buttons.items():
            if btn.isChecked():
                body_mode = mode
                break

        body_options: dict | None = None
        if body_mode == "raw":
            raw_format = self._raw_format_combo.currentText().lower()
            body_options = {"raw": {"language": raw_format}}

        # Read body from the active widget
        if body_mode in ("form-data", "x-www-form-urlencoded"):
            form_data = self._body_form_table.get_data()
            body_text = json.dumps(form_data) if form_data else ""
        elif body_mode == "binary":
            label_text = self._binary_file_label.text()
            body_text = "" if label_text == "No file selected." else label_text
        elif body_mode == "graphql":
            query = self._gql_query_editor.toPlainText()
            variables_text = self._gql_variables_editor.toPlainText().strip()
            # Parse variables as JSON object; fall back to empty dict
            variables: dict | str
            if variables_text:
                try:
                    variables = json.loads(variables_text)
                except (json.JSONDecodeError, TypeError):
                    variables = variables_text
            else:
                variables = {}
            body_text = json.dumps({"query": query, "variables": variables})
        else:
            body_text = self._body_code_editor.toPlainText()

        return {
            "method": self._method_combo.currentText(),
            "url": self._url_input.text(),
            "body": body_text,
            "request_parameters": self._params_table.get_data() or None,
            "headers": self._headers_table.get_data() or None,
            "body_mode": body_mode,
            "body_options": body_options,
            "description": self._description_edit.toPlainText() or None,
            "scripts": self._scripts_edit.toPlainText(),
            "auth": self._get_auth_data(),
        }

    def clear_request(self) -> None:
        """Reset the editor to the empty state."""
        self._loading = True
        try:
            self._request_id = None
            self._set_content_visible(False)
            self._method_combo.setCurrentIndex(0)
            self._url_input.clear()
            self._params_table.set_data([])
            self._headers_table.set_data([])
            self._body_code_editor.setPlainText("")
            self._body_form_table.set_data([])
            self._binary_file_label.setText("No file selected.")
            self._gql_query_editor.setPlainText("")
            self._gql_variables_editor.setPlainText("")
            self._gql_schema = None
            self._gql_schema_label.setText("No schema")
            self._gql_schema_label.setToolTip("")
            self._description_edit.clear()
            self._scripts_edit.clear()
            self._body_mode_buttons["none"].setChecked(True)
            self._raw_format_combo.setCurrentText("Text")
            self._auth_type_combo.setCurrentText("No Auth")
            self._bearer_token_input.clear()
            self._basic_username_input.clear()
            self._basic_password_input.clear()
            self._apikey_key_input.clear()
            self._apikey_value_input.clear()
            self._apikey_add_to_combo.setCurrentIndex(0)
            self._close_body_search()
            self._set_dirty(False)
        finally:
            self._loading = False

    # -- Dirty tracking -----------------------------------------------

    def _set_dirty(self, dirty: bool) -> None:
        """Update the dirty flag and emit dirty_changed."""
        if dirty == self._is_dirty:
            return
        self._is_dirty = dirty
        self.dirty_changed.emit(dirty)

    def _on_field_changed(self) -> None:
        """Handle any field modification -- mark dirty and start debounce."""
        if self._loading:
            return
        self._set_dirty(True)
        self._debounce_timer.start()
        self._sync_tab_indicators()

    def _sync_tab_indicators(self) -> None:
        """Append a dot indicator to section tabs that contain data."""
        has_content = [
            bool(self._params_table.get_data()),
            bool(self._headers_table.get_data()),
            not self._body_mode_buttons.get("none", QRadioButton()).isChecked(),
            self._auth_type_combo.currentText() != "No Auth",
            bool(self._description_edit.toPlainText().strip()),
            bool(self._scripts_edit.toPlainText().strip()),
        ]
        for i, (name, active) in enumerate(zip(_TAB_NAMES, has_content, strict=True)):
            self._tabs.setTabText(i, name + _CONTENT_DOT if active else name)

    def _update_method_color(self, method: str) -> None:
        """Tint the method combo box text to match the HTTP method colour."""
        color = method_color(method)
        self._method_combo.setStyleSheet(f"QComboBox {{ color: {color}; font-weight: bold; }}")

    def _on_body_mode_changed(self, checked: bool) -> None:
        """Switch body stack page and toggle raw format combo visibility."""
        if not checked:
            return
        # Guard: widgets may not exist yet during __init__ construction
        if not hasattr(self, "_raw_format_combo"):
            return
        # Show raw format dropdown only when "raw" mode is selected
        is_raw = self._body_mode_buttons.get("raw", QRadioButton()).isChecked()
        self._raw_format_combo.setVisible(is_raw)

        # Switch body stack page
        if self._body_mode_buttons.get("none", QRadioButton()).isChecked():
            self._body_stack.setCurrentIndex(0)
        elif is_raw:
            self._body_stack.setCurrentIndex(1)
            self._update_body_language()
        elif self._body_mode_buttons.get("graphql", QRadioButton()).isChecked():
            self._body_stack.setCurrentIndex(4)
        elif (
            self._body_mode_buttons.get("form-data", QRadioButton()).isChecked()
            or self._body_mode_buttons.get("x-www-form-urlencoded", QRadioButton()).isChecked()
        ):
            self._body_stack.setCurrentIndex(2)
        elif self._body_mode_buttons.get("binary", QRadioButton()).isChecked():
            self._body_stack.setCurrentIndex(3)

        if not self._loading:
            self._set_dirty(True)
            self._debounce_timer.start()
            self._sync_tab_indicators()

    # -- Body helpers -------------------------------------------------

    def _update_body_language(self) -> None:
        """Set the code editor language from the raw format dropdown."""
        fmt = self._raw_format_combo.currentText().lower()
        self._body_code_editor.set_language(fmt)

    def _on_prettify(self) -> None:
        """Prettify the body content via the code editor."""
        self._body_code_editor.prettify()

    def _on_wrap_toggle(self) -> None:
        """Toggle word-wrap in the body code editor."""
        self._body_code_editor.set_word_wrap(self._wrap_btn.isChecked())

    # -- Body search handlers ------------------------------------------

    def _active_code_editor(self) -> CodeEditorWidget | None:
        """Return the code editor that currently has focus, or ``None``.

        Checks the raw body editor, GQL query editor, and GQL variables
        editor.  Falls back to the raw body editor when the body tab is
        visible.
        """
        for editor in (
            self._body_code_editor,
            self._gql_query_editor,
            self._gql_variables_editor,
        ):
            if editor.hasFocus():
                return editor
        # Default: if the body tab is active, use the visible code editor
        idx = self._body_stack.currentIndex()
        if idx == 1:  # raw page
            return self._body_code_editor
        if idx == 4:  # graphql page
            return self._gql_query_editor
        return None

    def _toggle_body_search(self) -> None:
        """Show or hide the body search bar."""
        if not self._body_search_bar.isHidden():
            self._close_body_search()
        else:
            editor = self._active_code_editor()
            if editor is None:
                return
            self._body_search_editor = editor
            self._body_search_bar.show()
            self._body_search_input.setFocus()
            self._body_search_input.selectAll()

    def _close_body_search(self) -> None:
        """Hide the body search bar and clear highlights."""
        self._body_search_bar.hide()
        self._replace_row.hide()
        self._replace_toggle_btn.setChecked(False)
        self._replace_toggle_btn.setIcon(phi("caret-right"))
        self._body_search_input.clear()
        self._replace_input.clear()
        self._body_search_count_label.setText("")
        self._clear_body_search_highlights()
        self._body_search_matches = []
        self._body_search_index = -1
        self._body_search_editor = None

    def _on_body_search_text_changed(self, text: str) -> None:
        """Highlight all occurrences of *text* in the active code editor."""
        self._clear_body_search_highlights()
        self._body_search_matches = []
        self._body_search_index = -1

        editor = self._body_search_editor
        if editor is None or not text:
            self._body_search_count_label.setText("")
            return

        body_text = editor.toPlainText()
        start = 0
        while True:
            idx = body_text.find(text, start)
            if idx == -1:
                break
            self._body_search_matches.append(idx)
            start = idx + 1

        if not self._body_search_matches:
            self._body_search_count_label.setText("No results")
            return

        fmt = QTextCharFormat()
        fmt.setBackground(QColor(COLOR_WARNING))
        selections: list[QTextEdit.ExtraSelection] = []
        for pos in self._body_search_matches:
            sel = QTextEdit.ExtraSelection()
            cur = QTextCursor(editor.document())
            cur.setPosition(pos)
            cur.setPosition(pos + len(text), QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = cur
            sel.format = fmt
            selections.append(sel)
        editor.set_search_selections(selections)

        self._body_search_index = 0
        self._goto_body_search_match()

    def _body_search_next(self) -> None:
        """Move to the next search match."""
        if not self._body_search_matches:
            return
        self._body_search_index = (self._body_search_index + 1) % len(self._body_search_matches)
        self._goto_body_search_match()

    def _body_search_prev(self) -> None:
        """Move to the previous search match."""
        if not self._body_search_matches:
            return
        self._body_search_index = (self._body_search_index - 1) % len(self._body_search_matches)
        self._goto_body_search_match()

    def _goto_body_search_match(self) -> None:
        """Scroll to the current search match and update the counter."""
        editor = self._body_search_editor
        if (
            editor is None
            or self._body_search_index < 0
            or self._body_search_index >= len(self._body_search_matches)
        ):
            return
        pos = self._body_search_matches[self._body_search_index]
        text = self._body_search_input.text()
        cursor = editor.textCursor()
        cursor.setPosition(pos)
        cursor.setPosition(pos + len(text), QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()
        total = len(self._body_search_matches)
        self._body_search_count_label.setText(f"{self._body_search_index + 1} of {total}")

    def _clear_body_search_highlights(self) -> None:
        """Remove all search highlight formatting from the active editor."""
        if self._body_search_editor is not None:
            self._body_search_editor.set_search_selections([])

    # -- Replace handlers -----------------------------------------------

    def _toggle_replace_row(self) -> None:
        """Show or hide the replace row within the search bar."""
        if self._replace_row.isHidden():
            self._replace_row.show()
            self._replace_toggle_btn.setIcon(phi("caret-down"))
            self._replace_toggle_btn.setChecked(True)
            self._replace_input.setFocus()
        else:
            self._replace_row.hide()
            self._replace_toggle_btn.setIcon(phi("caret-right"))
            self._replace_toggle_btn.setChecked(False)

    def _toggle_body_replace(self) -> None:
        """Open the search bar with the replace row visible."""
        editor = self._active_code_editor()
        if editor is None:
            return
        if self._body_search_bar.isHidden():
            self._body_search_editor = editor
            self._body_search_bar.show()
        if self._replace_row.isHidden():
            self._replace_row.show()
            self._replace_toggle_btn.setIcon(phi("caret-down"))
            self._replace_toggle_btn.setChecked(True)
        self._replace_input.setFocus()

    def _replace_one(self) -> None:
        """Replace the current search match and advance to the next."""
        editor = self._body_search_editor
        if editor is None or not self._body_search_matches or self._body_search_index < 0:
            return

        search_text = self._body_search_input.text()
        replace_text = self._replace_input.text()
        pos = self._body_search_matches[self._body_search_index]

        cursor = editor.textCursor()
        cursor.setPosition(pos)
        cursor.setPosition(pos + len(search_text), QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(replace_text)

        # Re-run the search to refresh match positions
        self._on_body_search_text_changed(search_text)

    def _replace_all(self) -> None:
        """Replace all search matches at once."""
        editor = self._body_search_editor
        if editor is None or not self._body_search_matches:
            return

        search_text = self._body_search_input.text()
        replace_text = self._replace_input.text()
        if not search_text:
            return

        # Replace backwards to preserve earlier positions
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        for pos in reversed(self._body_search_matches):
            cursor.setPosition(pos)
            cursor.setPosition(pos + len(search_text), QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(replace_text)
        cursor.endEditBlock()

        # Re-run the search (should find zero matches now)
        self._on_body_search_text_changed(search_text)

    def _on_body_validation(self, errors: list) -> None:
        """Update the body error label when validation results change."""
        if errors:
            err = errors[0]
            lang = self._body_code_editor.language.upper()
            msg = f"\u26a0 {lang} error on line {err.line}: {err.message}"
            self._body_error_label.setText(msg)
            self._body_error_label.show()
        else:
            self._body_error_label.setText("")
            self._body_error_label.hide()

    # -- GraphQL body helpers -----------------------------------------

    def _on_gql_prettify(self) -> None:
        """Prettify both the GraphQL query and variables editors."""
        self._gql_query_editor.prettify()
        self._gql_variables_editor.prettify()

    def _on_gql_wrap_toggle(self) -> None:
        """Toggle word-wrap in both GraphQL editors."""
        wrap = self._gql_wrap_btn.isChecked()
        self._gql_query_editor.set_word_wrap(wrap)
        self._gql_variables_editor.set_word_wrap(wrap)

    def _on_gql_validation(self, errors: list) -> None:
        """Update the GraphQL error label when validation results change."""
        if errors:
            err = errors[0]
            msg = f"\u26a0 GraphQL error on line {err.line}: {err.message}"
            self._gql_error_label.setText(msg)
            self._gql_error_label.show()
        else:
            self._gql_error_label.setText("")
            self._gql_error_label.hide()

    # -- GraphQL schema introspection ----------------------------------

    def _on_fetch_schema(self) -> None:
        """Start a background introspection query to fetch the schema."""
        url = self._url_input.text().strip()
        if not url:
            self._gql_schema_label.setText("No URL")
            self._gql_schema_label.setToolTip("")
            return

        # Abort any in-flight schema fetch.
        if self._schema_thread is not None and self._schema_thread.isRunning():
            self._schema_thread.quit()
            self._schema_thread.wait()

        # Build headers dict from the headers table.
        headers: dict[str, str] = {}
        for row in self._headers_table.get_data() or []:
            key = row.get("key", "").strip()
            value = row.get("value", "")
            enabled = row.get("enabled", True)
            if key and enabled:
                headers[key] = value

        worker = SchemaFetchWorker()
        worker.set_endpoint(url=url, headers=headers or None)

        thread = QThread()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_schema_fetched)
        worker.error.connect(self._on_schema_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)

        self._schema_thread = thread
        self._schema_worker = worker

        self._gql_schema_label.setText("Fetching\u2026")
        self._gql_schema_label.setToolTip("")
        self._gql_fetch_schema_btn.setEnabled(False)

        thread.start()

    def _on_schema_fetched(self, result: dict) -> None:
        """Handle a successful schema introspection response."""
        self._gql_fetch_schema_btn.setEnabled(True)
        self._gql_schema = result

        types = result.get("types", [])
        count = len(types)
        self._gql_schema_label.setText(f"Schema ({count} types)")

        # Build tooltip from the schema summary.
        from services.graphql_schema_service import GraphQLSchemaService

        summary = GraphQLSchemaService.format_schema_summary(result)  # type: ignore[arg-type]
        self._gql_schema_label.setToolTip(summary)

    def _on_schema_error(self, message: str) -> None:
        """Handle a schema introspection failure."""
        self._gql_fetch_schema_btn.setEnabled(True)
        self._gql_schema = None
        self._gql_schema_label.setText("Schema error")
        self._gql_schema_label.setToolTip(message)

    def _on_schema_label_clicked(self) -> None:
        """Show schema details when the label is clicked.

        If no schema has been fetched, trigger a fetch instead.
        """
        if self._gql_schema is None:
            self._on_fetch_schema()
            return

        from services.graphql_schema_service import GraphQLSchemaService

        summary = GraphQLSchemaService.format_schema_summary(self._gql_schema)  # type: ignore[arg-type]
        self._show_schema_dialog(summary)

    def _show_schema_dialog(self, summary: str) -> None:
        """Display a modal dialog with the fetched schema summary."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("GraphQL Schema")
        dialog.resize(520, 480)
        layout = QVBoxLayout(dialog)

        viewer = CodeEditorWidget()
        viewer.set_language("text")
        viewer.setPlainText(summary)
        viewer.setReadOnly(True)
        layout.addWidget(viewer, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        dialog.exec()

    def _on_select_binary_file(self) -> None:
        """Open a file dialog and store the selected file path."""
        path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if path:
            self._binary_file_label.setText(path)
            self._on_field_changed()

    def _emit_request_changed(self) -> None:
        """Emit the debounced request_changed signal with current data."""
        self.request_changed.emit(self.get_request_data())

    def _on_auth_type_changed(self, auth_type: str) -> None:
        """Switch the auth fields stack page based on the selected type."""
        page_map = {
            "No Auth": 0,
            "Bearer Token": 1,
            "Basic Auth": 2,
            "API Key": 3,
        }
        self._auth_fields_stack.setCurrentIndex(page_map.get(auth_type, 0))
        if not self._loading:
            self._set_dirty(True)
            self._debounce_timer.start()
            self._sync_tab_indicators()

    def _get_auth_data(self) -> dict | None:
        """Build the auth configuration dict from the current UI state."""
        auth_type = self._auth_type_combo.currentText()
        if auth_type == "No Auth":
            return {"type": "noauth"}
        if auth_type == "Bearer Token":
            return {
                "type": "bearer",
                "bearer": [
                    {"key": "token", "value": self._bearer_token_input.text(), "type": "string"},
                ],
            }
        if auth_type == "Basic Auth":
            return {
                "type": "basic",
                "basic": [
                    {
                        "key": "username",
                        "value": self._basic_username_input.text(),
                        "type": "string",
                    },
                    {
                        "key": "password",
                        "value": self._basic_password_input.text(),
                        "type": "string",
                    },
                ],
            }
        if auth_type == "API Key":
            add_to = "header" if self._apikey_add_to_combo.currentText() == "Header" else "query"
            return {
                "type": "apikey",
                "apikey": [
                    {"key": "key", "value": self._apikey_key_input.text(), "type": "string"},
                    {"key": "value", "value": self._apikey_value_input.text(), "type": "string"},
                    {"key": "in", "value": add_to, "type": "string"},
                ],
            }
        return None

    # -- Key-value table helpers ---------------------------------------

    @staticmethod
    def _load_key_value_data(table: KeyValueTableWidget, raw: str | list | None) -> None:
        """Parse stored data into a ``KeyValueTableWidget``.

        Accepts a list of dicts (JSON column), a JSON array string
        (legacy), or plain ``key: value`` / ``key=value`` text lines.
        """
        if not raw:
            table.set_data([])
            return

        # 1. Already a list (JSON column returns Python list directly)
        if isinstance(raw, list):
            rows = [
                {
                    "key": item.get("key", ""),
                    "value": item.get("value", ""),
                    "description": item.get("description", ""),
                    "enabled": not item.get("disabled", False),
                }
                for item in raw
                if isinstance(item, dict)
            ]
            table.set_data(rows)
            return

        # 2. Try JSON array string (legacy String column or Postman format)
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                rows = [
                    {
                        "key": item.get("key", ""),
                        "value": item.get("value", ""),
                        "description": item.get("description", ""),
                        "enabled": not item.get("disabled", False),
                    }
                    for item in parsed
                    if isinstance(item, dict)
                ]
                table.set_data(rows)
                return
        except (json.JSONDecodeError, TypeError):
            pass

        # 3. Fall back to plain text parsing
        table.from_text(raw)

    def get_headers_text(self) -> str | None:
        """Return enabled headers as newline-separated ``Key: Value`` text.

        Returns ``None`` when there are no headers.
        """
        text = self._headers_table.to_text()
        return text if text else None

    def get_params_text(self) -> str | None:
        """Return enabled params as newline-separated ``Key: Value`` text.

        Returns ``None`` when there are no parameters.
        """
        text = self._params_table.to_text()
        return text if text else None
