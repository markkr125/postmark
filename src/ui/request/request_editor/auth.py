"""Authorization tab mixin for the request editor.

Provides ``_AuthMixin`` with the auth tab UI construction
(type selector and field pages for Bearer, Basic, API Key) and
serialisation / deserialisation helpers.  Mixed into
``RequestEditorWidget``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.variable_line_edit import VariableLineEdit

if TYPE_CHECKING:
    from PySide6.QtCore import QTimer

# Authorization type identifiers (must match editor_widget._AUTH_TYPES order)
_AUTH_TYPES = ("No Auth", "Bearer Token", "Basic Auth", "API Key")


class _AuthMixin:
    """Mixin that adds auth tab building and auth data helpers.

    Expects the host class to provide ``_on_field_changed``,
    ``_loading``, ``_set_dirty``, and ``_debounce_timer`` attributes.
    """

    # -- Host-class interface (declared for mypy) -----------------------
    _loading: bool
    _debounce_timer: QTimer

    def _on_field_changed(self) -> None: ...
    def _set_dirty(self, dirty: bool) -> None: ...
    def _sync_tab_indicators(self) -> None: ...

    # -- UI construction (called from __init__) -------------------------

    def _build_auth_tab(self, auth_layout: QVBoxLayout) -> None:
        """Construct the auth tab contents: type selector + fields stack."""
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

        self._auth_fields_stack = QStackedWidget()

        # No Auth page
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

    # -- Auth type switching -------------------------------------------

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

    # -- Load / save helpers -------------------------------------------

    def _load_auth(self, auth: dict) -> None:
        """Populate auth fields from a Postman-format auth dict."""
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
