"""Editable request editor pane with method, URL, body mode, and tabbed details.

Emits ``send_requested`` when the Send button is clicked,
``save_requested`` when the user triggers a save, and
``request_changed`` (debounced) when any field is modified.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.key_value_table import KeyValueTableWidget
from ui.theme import COLOR_ACCENT, COLOR_BORDER, COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_WHITE

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


class RequestEditorWidget(QWidget):
    """Editable request editor with method, URL bar, and tabbed sections.

    Call :meth:`load_request` to populate the pane from a request dict.
    Emits ``send_requested`` when the Send button is clicked.
    Emits ``save_requested`` when Ctrl+S is pressed.
    Emits ``request_changed`` (debounced) when any field is modified.
    """

    send_requested = Signal()
    save_requested = Signal()
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
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # -- Title label (shows request name + dirty indicator) --
        self._title_label = QLabel()
        self._title_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {COLOR_TEXT};")
        root.addWidget(self._title_label)

        # -- Top bar: method dropdown + URL + Send --
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        self._method_combo = QComboBox()
        self._method_combo.addItems(list(_HTTP_METHODS))
        self._method_combo.setFixedWidth(90)
        self._method_combo.setStyleSheet(
            f"""
            QComboBox {{
                background: {COLOR_WHITE};
                border: 1px solid {COLOR_BORDER};
                padding: 4px 8px;
                font-weight: bold;
                color: {COLOR_TEXT};
            }}
            """
        )
        self._method_combo.currentTextChanged.connect(self._on_field_changed)
        top_bar.addWidget(self._method_combo)

        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("Enter request URL")
        self._url_input.setStyleSheet(
            f"""
            background: {COLOR_WHITE};
            border: 1px solid {COLOR_BORDER};
            padding: 4px 8px;
            color: {COLOR_TEXT};
            """
        )
        self._url_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._url_input.textChanged.connect(self._on_field_changed)
        top_bar.addWidget(self._url_input)

        self._send_btn = QPushButton("Send")
        self._send_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {COLOR_ACCENT};
                color: {COLOR_WHITE};
                border: none;
                padding: 6px 16px;
                font-weight: bold;
                border-radius: 3px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            """
        )
        self._send_btn.clicked.connect(self.send_requested.emit)
        top_bar.addWidget(self._send_btn)

        root.addLayout(top_bar)

        # -- Tabbed area: Params, Headers, Body, Scripts --
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"""
            QTabBar::tab {{
                padding: 6px 14px;
                color: {COLOR_TEXT_MUTED};
            }}
            QTabBar::tab:selected {{
                color: {COLOR_TEXT};
                border-bottom: 2px solid {COLOR_ACCENT};
            }}
            """
        )

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
            self._body_mode_buttons[mode] = rb
            self._body_mode_group.addButton(rb)
            mode_row.addWidget(rb)
            rb.toggled.connect(self._on_body_mode_changed)
        self._body_mode_buttons["none"].setChecked(True)
        mode_row.addStretch()

        # Raw format dropdown (visible only when mode is "raw")
        self._raw_format_combo = QComboBox()
        self._raw_format_combo.addItems(list(_RAW_FORMATS))
        self._raw_format_combo.setFixedWidth(80)
        self._raw_format_combo.setStyleSheet(
            f"""
            QComboBox {{
                background: {COLOR_WHITE};
                border: 1px solid {COLOR_BORDER};
                padding: 2px 6px;
                font-size: 11px;
            }}
            """
        )
        self._raw_format_combo.currentTextChanged.connect(self._on_field_changed)
        self._raw_format_combo.hide()
        mode_row.addWidget(self._raw_format_combo)

        body_layout.addLayout(mode_row)

        self._body_edit = QTextEdit()
        self._body_edit.setPlaceholderText("Request body")
        self._body_edit.textChanged.connect(self._on_field_changed)
        body_layout.addWidget(self._body_edit, 1)

        self._tabs.addTab(self._body_tab, "Body")

        # Auth tab with type selector
        self._auth_tab = QWidget()
        auth_layout = QVBoxLayout(self._auth_tab)
        auth_layout.setContentsMargins(0, 6, 0, 0)

        auth_type_row = QHBoxLayout()
        auth_type_row.setSpacing(8)
        auth_type_label = QLabel("Type:")
        auth_type_label.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 12px;")
        auth_type_row.addWidget(auth_type_label)

        self._auth_type_combo = QComboBox()
        self._auth_type_combo.addItems(list(_AUTH_TYPES))
        self._auth_type_combo.setFixedWidth(140)
        self._auth_type_combo.setStyleSheet(
            f"""
            QComboBox {{
                background: {COLOR_WHITE};
                border: 1px solid {COLOR_BORDER};
                padding: 4px 8px;
                color: {COLOR_TEXT};
            }}
            """
        )
        self._auth_type_combo.currentTextChanged.connect(self._on_auth_type_changed)
        auth_type_row.addWidget(self._auth_type_combo)
        auth_type_row.addStretch()
        auth_layout.addLayout(auth_type_row)

        # Auth fields stack
        self._auth_fields_stack = QStackedWidget()

        # No Auth page (empty)
        no_auth_page = QLabel("This request does not use any authorization.")
        no_auth_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        no_auth_page.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-style: italic; padding: 20px;")
        self._auth_fields_stack.addWidget(no_auth_page)

        # Bearer Token page
        bearer_page = QWidget()
        bearer_layout = QVBoxLayout(bearer_page)
        bearer_layout.setContentsMargins(0, 8, 0, 0)
        token_label = QLabel("Token")
        token_label.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 12px;")
        bearer_layout.addWidget(token_label)
        self._bearer_token_input = QLineEdit()
        self._bearer_token_input.setPlaceholderText("Enter bearer token")
        self._bearer_token_input.setStyleSheet(
            f"background: {COLOR_WHITE}; border: 1px solid {COLOR_BORDER};"
            f" padding: 4px 8px; color: {COLOR_TEXT};"
        )
        self._bearer_token_input.textChanged.connect(self._on_field_changed)
        bearer_layout.addWidget(self._bearer_token_input)
        bearer_layout.addStretch()
        self._auth_fields_stack.addWidget(bearer_page)

        # Basic Auth page
        basic_page = QWidget()
        basic_layout = QVBoxLayout(basic_page)
        basic_layout.setContentsMargins(0, 8, 0, 0)
        username_label = QLabel("Username")
        username_label.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 12px;")
        basic_layout.addWidget(username_label)
        self._basic_username_input = QLineEdit()
        self._basic_username_input.setPlaceholderText("Username")
        self._basic_username_input.setStyleSheet(
            f"background: {COLOR_WHITE}; border: 1px solid {COLOR_BORDER};"
            f" padding: 4px 8px; color: {COLOR_TEXT};"
        )
        self._basic_username_input.textChanged.connect(self._on_field_changed)
        basic_layout.addWidget(self._basic_username_input)
        password_label = QLabel("Password")
        password_label.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 12px;")
        basic_layout.addWidget(password_label)
        self._basic_password_input = QLineEdit()
        self._basic_password_input.setPlaceholderText("Password")
        self._basic_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._basic_password_input.setStyleSheet(
            f"background: {COLOR_WHITE}; border: 1px solid {COLOR_BORDER};"
            f" padding: 4px 8px; color: {COLOR_TEXT};"
        )
        self._basic_password_input.textChanged.connect(self._on_field_changed)
        basic_layout.addWidget(self._basic_password_input)
        basic_layout.addStretch()
        self._auth_fields_stack.addWidget(basic_page)

        # API Key page
        apikey_page = QWidget()
        apikey_layout = QVBoxLayout(apikey_page)
        apikey_layout.setContentsMargins(0, 8, 0, 0)
        key_label = QLabel("Key")
        key_label.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 12px;")
        apikey_layout.addWidget(key_label)
        self._apikey_key_input = QLineEdit()
        self._apikey_key_input.setPlaceholderText("Header or query parameter name")
        self._apikey_key_input.setStyleSheet(
            f"background: {COLOR_WHITE}; border: 1px solid {COLOR_BORDER};"
            f" padding: 4px 8px; color: {COLOR_TEXT};"
        )
        self._apikey_key_input.textChanged.connect(self._on_field_changed)
        apikey_layout.addWidget(self._apikey_key_input)
        value_label = QLabel("Value")
        value_label.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 12px;")
        apikey_layout.addWidget(value_label)
        self._apikey_value_input = QLineEdit()
        self._apikey_value_input.setPlaceholderText("API key value")
        self._apikey_value_input.setStyleSheet(
            f"background: {COLOR_WHITE}; border: 1px solid {COLOR_BORDER};"
            f" padding: 4px 8px; color: {COLOR_TEXT};"
        )
        self._apikey_value_input.textChanged.connect(self._on_field_changed)
        apikey_layout.addWidget(self._apikey_value_input)

        add_to_label = QLabel("Add to")
        add_to_label.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 12px;")
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
        self._description_edit.setStyleSheet(
            f"""
            QTextEdit {{
                border: 1px solid {COLOR_BORDER};
                background: {COLOR_WHITE};
                font-size: 12px;
                color: {COLOR_TEXT};
            }}
            """
        )
        self._description_edit.textChanged.connect(self._on_field_changed)
        self._tabs.addTab(self._description_edit, "Description")

        self._scripts_edit = QTextEdit()
        self._scripts_edit.setPlaceholderText("Scripts")
        self._scripts_edit.textChanged.connect(self._on_field_changed)
        self._tabs.addTab(self._scripts_edit, "Scripts")

        root.addWidget(self._tabs, 1)

        # -- Empty state --
        self._empty_label = QLabel("Select a request to view its details.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-style: italic; font-size: 13px;"
        )
        root.addWidget(self._empty_label)

        # Start in empty state
        self._set_content_visible(False)

    # -- Visibility helpers -------------------------------------------

    def _set_content_visible(self, visible: bool) -> None:
        """Toggle between the editor content and the empty-state label."""
        self._title_label.setVisible(visible)
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

            self._title_label.setText(data.get("name", ""))

            method = data.get("method", "GET").upper()
            idx = self._method_combo.findText(method)
            if idx >= 0:
                self._method_combo.setCurrentIndex(idx)

            self._url_input.setText(data.get("url", ""))

            self._load_key_value_data(self._params_table, data.get("request_parameters"))
            self._load_key_value_data(self._headers_table, data.get("headers"))
            self._body_edit.setPlainText(data.get("body") or "")

            # Body mode
            body_mode = data.get("body_mode") or "none"
            btn = self._body_mode_buttons.get(body_mode)
            if btn:
                btn.setChecked(True)

            # Raw format sub-option
            body_options = data.get("body_options") or {}
            raw_lang = (body_options.get("raw", {}) or {}).get("language", "text")
            lang_map = {"json": "JSON", "xml": "XML", "html": "HTML", "text": "Text"}
            self._raw_format_combo.setCurrentText(lang_map.get(raw_lang, "Text"))

            scripts = data.get("scripts")
            if isinstance(scripts, dict):
                self._scripts_edit.setPlainText(json.dumps(scripts, indent=2))
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

        return {
            "method": self._method_combo.currentText(),
            "url": self._url_input.text(),
            "body": self._body_edit.toPlainText(),
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
            self._title_label.setText("")
            self._method_combo.setCurrentIndex(0)
            self._url_input.clear()
            self._params_table.set_data([])
            self._headers_table.set_data([])
            self._body_edit.clear()
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
            self._set_dirty(False)
        finally:
            self._loading = False

    # -- Dirty tracking -----------------------------------------------

    def _set_dirty(self, dirty: bool) -> None:
        """Update the dirty flag and title indicator."""
        self._is_dirty = dirty
        title = self._title_label.text()
        if dirty and not title.startswith("\u2022 "):
            self._title_label.setText(f"\u2022 {title}")
        elif not dirty and title.startswith("\u2022 "):
            self._title_label.setText(title[2:])

    def _on_field_changed(self) -> None:
        """Handle any field modification -- mark dirty and start debounce."""
        if self._loading:
            return
        self._set_dirty(True)
        self._debounce_timer.start()

    def _on_body_mode_changed(self, checked: bool) -> None:
        """Toggle raw format combo visibility and mark dirty."""
        if not checked:
            return
        # Guard: combo may not exist yet during __init__ construction
        if not hasattr(self, "_raw_format_combo"):
            return
        # Show raw format dropdown only when "raw" mode is selected
        is_raw = self._body_mode_buttons.get("raw", QRadioButton()).isChecked()
        self._raw_format_combo.setVisible(is_raw)

        # Disable body edit when mode is "none"
        is_none = self._body_mode_buttons.get("none", QRadioButton()).isChecked()
        self._body_edit.setEnabled(not is_none)

        if not self._loading:
            self._set_dirty(True)
            self._debounce_timer.start()

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
