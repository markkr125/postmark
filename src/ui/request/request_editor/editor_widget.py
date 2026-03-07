"""Editable request editor pane with method, URL, body mode, and tabbed details.

Emits ``send_requested`` when the Send button is clicked,
``save_requested`` when the user triggers a save, and
``request_changed`` (debounced) when any field is modified.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from PySide6.QtCore import (QModelIndex, QPersistentModelIndex, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QColor, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QRadioButton, QSizePolicy,
                               QStyledItemDelegate, QStyleOptionViewItem,
                               QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from ui.request.request_editor.auth import _AuthMixin
from ui.request.request_editor.body_search import _BodySearchMixin
from ui.request.request_editor.graphql import _GraphQLMixin
from ui.styling.icons import phi
from ui.styling.theme import method_color
from ui.widgets.key_value_table import KeyValueTableWidget
from ui.widgets.variable_line_edit import VariableLineEdit

if TYPE_CHECKING:
    from services.collection_service import RequestLoadDict
    from services.environment_service import VariableDetail

# HTTP methods shown in the dropdown
_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

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


class RequestEditorWidget(_AuthMixin, _BodySearchMixin, _GraphQLMixin, QWidget):
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

        # -- Tabbed area: Params, Headers, Body, Auth, Description, Scripts --
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

        # Body tab
        self._body_tab = QWidget()
        body_layout = QVBoxLayout(self._body_tab)
        body_layout.setContentsMargins(0, 6, 0, 0)
        self._build_body_tab(body_layout)
        self._tabs.addTab(self._body_tab, "Body")

        # Auth tab
        self._auth_tab = QWidget()
        auth_layout = QVBoxLayout(self._auth_tab)
        auth_layout.setContentsMargins(0, 6, 0, 0)
        self._build_auth_tab(auth_layout)
        self._tabs.addTab(self._auth_tab, "Auth")

        self._description_edit = QTextEdit()
        self._description_edit.setPlaceholderText("Add a description for this request\u2026")
        self._description_edit.textChanged.connect(self._on_field_changed)
        self._tabs.addTab(self._description_edit, "Description")

        self._scripts_edit = QTextEdit()
        self._scripts_edit.setPlaceholderText("Scripts")
        self._scripts_edit.textChanged.connect(self._on_field_changed)
        self._tabs.addTab(self._scripts_edit, "Scripts")

        tab_header_h = self._tabs.tabBar().sizeHint().height()
        self._tabs.setMinimumHeight(tab_header_h + 4)
        self._tabs.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)

        root.addWidget(self._tabs, 1)

        # -- Empty state --
        self._empty_label = QLabel("Select a request to view its details.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("emptyStateLabel")
        root.addWidget(self._empty_label)

        self._set_content_visible(False)

        # Keyboard shortcuts scoped to this widget tree
        self._body_find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self._body_find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._body_find_shortcut.activated.connect(self._toggle_body_search)

        self._body_replace_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        self._body_replace_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._body_replace_shortcut.activated.connect(self._toggle_body_replace)

    # -- Init helpers (auth tab builder) --------------------------------

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
        self._loading = True
        try:
            self._url_input.set_variable_map(variables)
            self._bearer_token_input.set_variable_map(variables)
            self._basic_username_input.set_variable_map(variables)
            self._basic_password_input.set_variable_map(variables)
            self._apikey_key_input.set_variable_map(variables)
            self._apikey_value_input.set_variable_map(variables)
            self._params_table.set_variable_map(variables)
            self._headers_table.set_variable_map(variables)
            self._body_form_table.set_variable_map(variables)
            self._body_code_editor.set_variable_map(variables)
            self._gql_query_editor.set_variable_map(variables)
            self._gql_variables_editor.set_variable_map(variables)
        finally:
            self._loading = False

    def load_request(self, data: RequestLoadDict, *, request_id: int | None = None) -> None:
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

            self._load_body_content(data, body_mode)

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

            self._load_auth(data.get("auth") or {})
            self._description_edit.setPlainText(data.get("description") or "")
            self._set_dirty(False)
        finally:
            self._loading = False
        self._sync_tab_indicators()

    def _load_body_content(self, data: RequestLoadDict, body_mode: str) -> None:
        """Load body content into the correct widget for *body_mode*."""
        body = data.get("body") or ""
        if body_mode in ("form-data", "x-www-form-urlencoded"):
            self._load_key_value_data(self._body_form_table, body or None)
            self._body_code_editor.setPlainText("")
        elif body_mode == "binary":
            self._binary_file_label.setText(body if body else "No file selected.")
            self._body_code_editor.setPlainText("")
        elif body_mode == "graphql":
            query_text, variables_text = self._parse_graphql_body(body)
            self._gql_query_editor.setPlainText(query_text)
            self._gql_variables_editor.setPlainText(variables_text)
            self._body_code_editor.setPlainText("")
        else:
            self._body_code_editor.setPlainText(body)
            self._body_form_table.set_data([])

    @staticmethod
    def _parse_graphql_body(body: str) -> tuple[str, str]:
        """Parse stored GraphQL JSON into (query, variables) strings."""
        if not body:
            return "", ""
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
                    variables_text = ""
                return query_text, variables_text
            return body, ""
        except (json.JSONDecodeError, TypeError):
            return body, ""

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

        body_text = self._serialize_body(body_mode)

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

    def _serialize_body(self, body_mode: str) -> str:
        """Serialize the body content from the active widget."""
        if body_mode in ("form-data", "x-www-form-urlencoded"):
            form_data = self._body_form_table.get_data()
            return json.dumps(form_data) if form_data else ""
        if body_mode == "binary":
            label_text = self._binary_file_label.text()
            return "" if label_text == "No file selected." else label_text
        if body_mode == "graphql":
            query = self._gql_query_editor.toPlainText()
            variables_text = self._gql_variables_editor.toPlainText().strip()
            variables: dict | str
            if variables_text:
                try:
                    variables = json.loads(variables_text)
                except (json.JSONDecodeError, TypeError):
                    variables = variables_text
            else:
                variables = {}
            return json.dumps({"query": query, "variables": variables})
        return self._body_code_editor.toPlainText()

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
        if not hasattr(self, "_raw_format_combo"):
            return
        is_raw = self._body_mode_buttons.get("raw", QRadioButton()).isChecked()
        self._raw_format_combo.setVisible(is_raw)

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

    def _on_select_binary_file(self) -> None:
        """Open a file dialog and store the selected file path."""
        path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if path:
            self._binary_file_label.setText(path)
            self._on_field_changed()

    def _emit_request_changed(self) -> None:
        """Emit the debounced request_changed signal with current data."""
        self.request_changed.emit(self.get_request_data())

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
