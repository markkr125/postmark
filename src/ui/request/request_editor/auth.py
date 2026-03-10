"""Authorization tab mixin for the request editor.

Provides ``_AuthMixin`` with the auth tab UI construction
(type selector and field pages for Inherit, No Auth, Bearer,
Basic, API Key) and serialisation / deserialisation helpers.
Mixed into ``RequestEditorWidget``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit,
                               QStackedWidget, QVBoxLayout, QWidget)

from ui.widgets.variable_line_edit import VariableLineEdit

if TYPE_CHECKING:
    from PySide6.QtCore import QTimer

# Authorization type identifiers (must match stacked-widget page order)
_AUTH_TYPES = ("Inherit auth from parent", "No Auth", "Bearer Token", "Basic Auth", "API Key")

# Human-readable labels for resolved auth types shown in the inherit preview
_AUTH_TYPE_LABELS: dict[str, str] = {
    "bearer": "Bearer Token",
    "basic": "Basic Auth",
    "apikey": "API Key",
}


class _AuthMixin:
    """Mixin that adds auth tab building and auth data helpers.

    Expects the host class to provide ``_on_field_changed``,
    ``_loading``, ``_set_dirty``, and ``_debounce_timer`` attributes.
    """

    # -- Host-class interface (declared for mypy) -----------------------
    _loading: bool
    _debounce_timer: QTimer
    _request_id: int | None

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
        self._auth_type_combo.setFixedWidth(200)
        self._auth_type_combo.currentTextChanged.connect(self._on_auth_type_changed)
        auth_type_row.addWidget(self._auth_type_combo)
        auth_type_row.addStretch()
        auth_layout.addLayout(auth_type_row)

        self._auth_fields_stack = QStackedWidget()

        # Inherit auth from parent page (index 0)
        inherit_page = QWidget()
        inherit_layout = QVBoxLayout(inherit_page)
        inherit_layout.setContentsMargins(0, 8, 0, 0)
        inherit_msg = QLabel(
            "The authorization header will be automatically\ngenerated when you send the request."
        )
        inherit_msg.setObjectName("emptyStateLabel")
        inherit_layout.addWidget(inherit_msg)
        self._inherit_preview_label = QLabel()
        self._inherit_preview_label.setObjectName("sectionLabel")
        self._inherit_preview_label.setWordWrap(True)
        inherit_layout.addWidget(self._inherit_preview_label)
        inherit_layout.addStretch()
        self._auth_fields_stack.addWidget(inherit_page)

        # No Auth page (index 1)
        no_auth_page = QLabel("This request does not use any authorization.")
        no_auth_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        no_auth_page.setObjectName("emptyStateLabel")
        self._auth_fields_stack.addWidget(no_auth_page)

        # Bearer Token page (index 2)
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

        # Basic Auth page (index 3)
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

        # API Key page (index 4)
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
            "Inherit auth from parent": 0,
            "No Auth": 1,
            "Bearer Token": 2,
            "Basic Auth": 3,
            "API Key": 4,
        }
        self._auth_fields_stack.setCurrentIndex(page_map.get(auth_type, 0))
        if auth_type == "Inherit auth from parent":
            self._update_inherit_preview()
        if not self._loading:
            self._set_dirty(True)
            self._debounce_timer.start()
            self._sync_tab_indicators()

    # -- Inherit preview -----------------------------------------------

    def _update_inherit_preview(self) -> None:
        """Refresh the inherit page label with the resolved parent auth."""
        from services.collection_service import CollectionService

        request_id = getattr(self, "_request_id", None)
        if not request_id:
            self._inherit_preview_label.setText("No parent auth configured.")
            return
        resolved = CollectionService.get_request_inherited_auth(request_id)
        self._set_inherit_preview_from_auth(resolved)

    def _set_inherit_preview_from_auth(self, auth: dict[str, Any] | None) -> None:
        """Set the inherit preview label from a resolved auth dict."""
        if not auth:
            self._inherit_preview_label.setText("No parent auth configured.")
            return
        auth_type = auth.get("type", "")
        label = _AUTH_TYPE_LABELS.get(auth_type, auth_type)
        self._inherit_preview_label.setText(f"Using {label} from parent.")

    # -- Load / save helpers -------------------------------------------

    def _load_auth(self, auth: dict | None) -> None:
        """Populate auth fields from a Postman-format auth dict.

        ``None`` or ``{}`` maps to "Inherit auth from parent".
        ``{"type": "noauth"}`` maps to "No Auth".
        """
        if not auth:
            self._auth_type_combo.setCurrentText("Inherit auth from parent")
            return

        auth_type = auth.get("type", "inherit")
        auth_type_map: dict[str, str] = {
            "inherit": "Inherit auth from parent",
            "noauth": "No Auth",
            "bearer": "Bearer Token",
            "basic": "Basic Auth",
            "apikey": "API Key",
        }
        self._auth_type_combo.setCurrentText(
            auth_type_map.get(auth_type, "Inherit auth from parent")
        )
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
        """Build the auth configuration dict from the current UI state.

        Returns ``None`` for "Inherit auth from parent" (stored as
        ``auth = None`` in the database).
        """
        auth_type = self._auth_type_combo.currentText()
        if auth_type == "Inherit auth from parent":
            return None
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
