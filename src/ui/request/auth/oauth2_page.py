"""Custom OAuth 2.0 page with grant-type switching and token management.

Unlike FieldSpec-driven pages, this widget has specialised UI sections:

1. **Current Token** — shows the active access token, header prefix,
   and where to add it (header or query).
2. **Configure New Token** — grant-type selector with conditional
   fields for Authorization Code, Implicit, Password Credentials,
   and Client Credentials.
3. **Get New Access Token** button that triggers the OAuth flow.

The page stores all values in Postman key-value format for seamless
round-tripping through :func:`load` / :func:`get_entries`.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QScrollArea,
                               QToolButton, QVBoxLayout, QWidget)

from ui.widgets.variable_line_edit import VariableLineEdit

_INPUT_MAX_WIDTH = 360
_GRANT_TYPES = (
    "Authorization Code",
    "Implicit",
    "Password Credentials",
    "Client Credentials",
)
_GRANT_TYPE_KEYS: dict[str, str] = {
    "Authorization Code": "authorization_code",
    "Implicit": "implicit",
    "Password Credentials": "password",
    "Client Credentials": "client_credentials",
}
_GRANT_KEY_TO_DISPLAY: dict[str, str] = {v: k for k, v in _GRANT_TYPE_KEYS.items()}

_CLIENT_AUTH_OPTIONS = (
    "Send as Basic Auth header",
    "Send client credentials in body",
)
_CLIENT_AUTH_KEYS: dict[str, str] = {
    "Send as Basic Auth header": "header",
    "Send client credentials in body": "body",
}
_CLIENT_AUTH_DISPLAY: dict[str, str] = {v: k for k, v in _CLIENT_AUTH_KEYS.items()}


class OAuth2Page(QScrollArea):
    """Custom OAuth 2.0 configuration page.

    Signals:
        field_changed: Emitted when any field value changes.
        get_token_requested: Emitted when user clicks *Get New Access Token*.
    """

    field_changed = Signal()
    get_token_requested = Signal()

    def __init__(self, on_change: Callable[[], None]) -> None:
        """Build the OAuth 2.0 page with token and configuration sections."""
        super().__init__()
        self._initializing = True
        self._on_change = on_change
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)

        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(16, 8, 0, 0)
        root.setSpacing(0)

        self._build_current_token_section(root)
        root.addSpacing(16)
        self._build_configure_section(root)
        root.addSpacing(12)
        self._build_get_token_button(root)
        root.addStretch()

        self.setWidget(inner)
        self._initializing = False

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _build_current_token_section(self, root: QVBoxLayout) -> None:
        """Build the *Current Token* section."""
        header = QLabel("Current Token")
        header.setObjectName("sectionLabel")
        header.setStyleSheet("font-weight: bold; font-size: 12px;")
        root.addWidget(header)
        root.addSpacing(8)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self._token_name_display = VariableLineEdit()
        self._token_name_display.setPlaceholderText("Token name")
        self._token_name_display.setMaximumWidth(_INPUT_MAX_WIDTH)
        self._token_name_display.setReadOnly(True)
        _add_row(form, "Token", self._token_name_display)

        self._access_token = VariableLineEdit()
        self._access_token.setPlaceholderText("Paste or obtain a token")
        self._access_token.setMaximumWidth(_INPUT_MAX_WIDTH)
        self._access_token.textChanged.connect(self._on_change)
        _add_row(form, "Access Token", self._access_token)

        self._header_prefix = VariableLineEdit()
        self._header_prefix.setPlaceholderText("Bearer")
        self._header_prefix.setMaximumWidth(_INPUT_MAX_WIDTH)
        self._header_prefix.setText("Bearer")
        self._header_prefix.textChanged.connect(self._on_change)
        _add_row(form, "Header Prefix", self._header_prefix)

        self._add_token_to = QComboBox()
        self._add_token_to.addItems(("Header", "Query Params"))
        self._add_token_to.setMaximumWidth(_INPUT_MAX_WIDTH)
        self._add_token_to.currentTextChanged.connect(lambda _: self._on_change())
        _add_row(form, "Add token to", self._add_token_to)

        root.addLayout(form)

    def _build_configure_section(self, root: QVBoxLayout) -> None:
        """Build the *Configure New Token* section with grant-type switching."""
        toggle = QToolButton()
        toggle.setObjectName("advancedToggle")
        toggle.setText("\u25b8 Configure New Token")
        toggle.setCheckable(True)
        toggle.setChecked(False)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.setStyleSheet("QToolButton { border: none; font-weight: bold; font-size: 12px; }")
        root.addWidget(toggle)

        self._config_container = QWidget()
        config_layout = QVBoxLayout(self._config_container)
        config_layout.setContentsMargins(0, 4, 0, 0)
        config_layout.setSpacing(0)

        # Token Name + Grant Type
        top_form = QFormLayout()
        top_form.setContentsMargins(0, 0, 0, 0)
        top_form.setHorizontalSpacing(12)
        top_form.setVerticalSpacing(10)
        top_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self._token_name = VariableLineEdit()
        self._token_name.setPlaceholderText("Token Name")
        self._token_name.setMaximumWidth(_INPUT_MAX_WIDTH)
        self._token_name.textChanged.connect(self._on_change)
        _add_row(top_form, "Token Name", self._token_name)

        self._grant_type = QComboBox()
        self._grant_type.addItems(_GRANT_TYPES)
        self._grant_type.setMaximumWidth(_INPUT_MAX_WIDTH)
        self._grant_type.currentTextChanged.connect(self._on_grant_type_changed)
        _add_row(top_form, "Grant Type", self._grant_type)

        config_layout.addLayout(top_form)
        config_layout.addSpacing(8)

        # Grant-type specific fields
        self._grant_fields: dict[str, dict[str, QWidget]] = {}
        self._grant_containers: dict[str, QWidget] = {}
        for display_name in _GRANT_TYPES:
            container, widgets = self._build_grant_fields(display_name)
            self._grant_containers[display_name] = container
            self._grant_fields[display_name] = widgets
            config_layout.addWidget(container)

        self._config_container.setVisible(False)
        root.addWidget(self._config_container)

        def _on_toggle(checked: bool) -> None:
            self._config_container.setVisible(checked)
            toggle.setText(
                "\u25be Configure New Token" if checked else "\u25b8 Configure New Token"
            )

        toggle.toggled.connect(_on_toggle)
        self._on_grant_type_changed(self._grant_type.currentText())

    def _build_grant_fields(self, grant_display: str) -> tuple[QWidget, dict[str, QWidget]]:
        """Build the conditional field group for a single grant type."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        widgets: dict[str, QWidget] = {}

        if grant_display == "Authorization Code":
            widgets["callbackUrl"] = _text(form, "Callback URL", "https://localhost:5000/callback")
            widgets["useBrowser"] = _checkbox(form, "Authorize using browser")
            widgets["authUrl"] = _text(form, "Auth URL", "https://example.com/authorize")
            widgets["accessTokenUrl"] = _text(form, "Access Token URL", "https://example.com/token")
            widgets["clientId"] = _text(form, "Client ID", "Client ID")
            widgets["clientSecret"] = _password(form, "Client Secret", "Client secret")
            widgets["scope"] = _text(form, "Scope", "read write")
            widgets["state"] = _text(form, "State", "random_state")
            widgets["client_authentication"] = _auth_combo(form)

        elif grant_display == "Implicit":
            widgets["callbackUrl"] = _text(form, "Callback URL", "https://localhost:5000/callback")
            widgets["authUrl"] = _text(form, "Auth URL", "https://example.com/authorize")
            widgets["clientId"] = _text(form, "Client ID", "Client ID")
            widgets["scope"] = _text(form, "Scope", "read write")
            widgets["state"] = _text(form, "State", "random_state")

        elif grant_display == "Password Credentials":
            widgets["accessTokenUrl"] = _text(form, "Access Token URL", "https://example.com/token")
            widgets["username"] = _text(form, "Username", "Username")
            widgets["password"] = _password(form, "Password", "Password")
            widgets["clientId"] = _text(form, "Client ID", "Client ID")
            widgets["clientSecret"] = _password(form, "Client Secret", "Client secret")
            widgets["scope"] = _text(form, "Scope", "read write")
            widgets["client_authentication"] = _auth_combo(form)

        elif grant_display == "Client Credentials":
            widgets["accessTokenUrl"] = _text(form, "Access Token URL", "https://example.com/token")
            widgets["clientId"] = _text(form, "Client ID", "Client ID")
            widgets["clientSecret"] = _password(form, "Client Secret", "Client secret")
            widgets["scope"] = _text(form, "Scope", "read write")
            widgets["client_authentication"] = _auth_combo(form)

        layout.addLayout(form)

        # Connect change signals
        for w in widgets.values():
            if isinstance(w, QLineEdit):
                w.textChanged.connect(self._on_change)
            elif isinstance(w, QComboBox):
                w.currentTextChanged.connect(lambda _: self._on_change())
            elif isinstance(w, QCheckBox):
                w.stateChanged.connect(lambda _: self._on_change())

        return container, widgets

    def _build_get_token_button(self, root: QVBoxLayout) -> None:
        """Create the *Get New Access Token* button."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self._get_token_btn = QPushButton("Get New Access Token")
        self._get_token_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._get_token_btn.setMaximumWidth(200)
        self._get_token_btn.clicked.connect(self.get_token_requested.emit)
        row.addWidget(self._get_token_btn)
        row.addStretch()
        root.addLayout(row)

    # ------------------------------------------------------------------
    # Grant type switching
    # ------------------------------------------------------------------

    def _on_grant_type_changed(self, display_name: str) -> None:
        """Show fields for the selected grant type, hide others."""
        for name, container in self._grant_containers.items():
            container.setVisible(name == display_name)
        if not self._initializing:
            self._on_change()

    # ------------------------------------------------------------------
    # Load / Save (Postman key-value format)
    # ------------------------------------------------------------------

    def load(self, entries: list[dict]) -> None:
        """Populate the page from Postman key-value *entries*."""
        entry_map: dict[str, object] = {}
        for e in entries:
            if isinstance(e, dict):
                entry_map[e["key"]] = e.get("value", "")

        # Current token section
        _set_text(self._access_token, str(entry_map.get("accessToken", "")))
        _set_text(self._header_prefix, str(entry_map.get("headerPrefix", "Bearer")))
        _set_text(self._token_name, str(entry_map.get("tokenName", "")))
        _set_text(self._token_name_display, str(entry_map.get("tokenName", "")))

        add_to = str(entry_map.get("addTokenTo", "header"))
        add_to_map = {"header": "Header", "queryParams": "Query Params"}
        self._add_token_to.setCurrentText(add_to_map.get(add_to, "Header"))

        # Grant type
        grant_raw = str(entry_map.get("grant_type", "authorization_code"))
        grant_display = _GRANT_KEY_TO_DISPLAY.get(grant_raw, "Authorization Code")
        self._grant_type.setCurrentText(grant_display)

        # Grant-specific fields (load into ALL containers — widgets may overlap)
        for _display_name, widgets in self._grant_fields.items():
            for key, widget in widgets.items():
                raw = entry_map.get(key, "")
                if isinstance(widget, QCheckBox):
                    widget.setChecked(raw is True or str(raw).lower() == "true")
                elif isinstance(widget, QComboBox):
                    if key == "client_authentication":
                        display = _CLIENT_AUTH_DISPLAY.get(str(raw), str(raw))
                        widget.setCurrentText(display)
                    else:
                        widget.setCurrentText(str(raw))
                elif isinstance(widget, QLineEdit):
                    _set_text(widget, str(raw) if raw else "")

    def get_entries(self) -> list[dict]:
        """Serialise all field values to Postman key-value entry list."""
        entries: list[dict] = []

        def _add(key: str, value: str | bool) -> None:
            entries.append({"key": key, "value": value, "type": "string"})

        # Current token
        _add("accessToken", self._access_token.text())
        _add("headerPrefix", self._header_prefix.text() or "Bearer")
        _add("tokenName", self._token_name.text())

        add_to_rev = {"Header": "header", "Query Params": "queryParams"}
        _add("addTokenTo", add_to_rev.get(self._add_token_to.currentText(), "header"))

        # Grant type
        grant_display = self._grant_type.currentText()
        grant_key = _GRANT_TYPE_KEYS.get(grant_display, "authorization_code")
        _add("grant_type", grant_key)

        # Active grant fields only
        active_widgets = self._grant_fields.get(grant_display, {})
        for key, widget in active_widgets.items():
            if isinstance(widget, QCheckBox):
                _add(key, widget.isChecked())
            elif isinstance(widget, QComboBox):
                if key == "client_authentication":
                    _add(key, _CLIENT_AUTH_KEYS.get(widget.currentText(), "header"))
                else:
                    _add(key, widget.currentText())
            elif isinstance(widget, QLineEdit):
                _add(key, widget.text())

        return entries

    def get_config(self) -> dict:
        """Return configuration needed for the token flow.

        Used by the token worker to know which grant type and endpoints
        to use.
        """
        grant_display = self._grant_type.currentText()
        grant_key = _GRANT_TYPE_KEYS.get(grant_display, "authorization_code")
        active = self._grant_fields.get(grant_display, {})

        config: dict[str, str | bool] = {"grant_type": grant_key}
        for key, widget in active.items():
            if isinstance(widget, QCheckBox):
                config[key] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                if key == "client_authentication":
                    config[key] = _CLIENT_AUTH_KEYS.get(widget.currentText(), "header")
                else:
                    config[key] = widget.currentText()
            elif isinstance(widget, QLineEdit):
                config[key] = widget.text()
        config["tokenName"] = self._token_name.text()
        return config

    def set_token(self, token: str, name: str = "") -> None:
        """Set the obtained token into the current-token section."""
        self._access_token.setText(token)
        if name:
            _set_text(self._token_name_display, name)

    def clear(self) -> None:
        """Reset all fields to defaults."""
        self._access_token.clear()
        self._header_prefix.setText("Bearer")
        self._add_token_to.setCurrentIndex(0)
        self._token_name.clear()
        self._token_name_display.clear()
        self._grant_type.setCurrentIndex(0)
        for widgets in self._grant_fields.values():
            for w in widgets.values():
                if isinstance(w, QLineEdit):
                    w.clear()
                elif isinstance(w, QComboBox):
                    w.setCurrentIndex(0)
                elif isinstance(w, QCheckBox):
                    w.setChecked(False)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _add_row(form: QFormLayout, label_text: str, widget: QWidget) -> None:
    """Add a labelled row to *form*."""
    lbl = QLabel(label_text)
    lbl.setObjectName("sectionLabel")
    form.addRow(lbl, widget)


def _text(form: QFormLayout, label: str, placeholder: str) -> VariableLineEdit:
    """Create a text input and add it to *form*."""
    w = VariableLineEdit()
    w.setPlaceholderText(placeholder)
    w.setMaximumWidth(_INPUT_MAX_WIDTH)
    _add_row(form, label, w)
    return w


def _password(form: QFormLayout, label: str, placeholder: str) -> VariableLineEdit:
    """Create a password input and add it to *form*."""
    w = VariableLineEdit()
    w.setPlaceholderText(placeholder)
    w.setEchoMode(QLineEdit.EchoMode.Password)
    w.setMaximumWidth(_INPUT_MAX_WIDTH)
    _add_row(form, label, w)
    return w


def _checkbox(form: QFormLayout, label: str) -> QCheckBox:
    """Create a checkbox and add it to *form* (full-row)."""
    cb = QCheckBox(label)
    form.addRow(cb)
    return cb


def _auth_combo(form: QFormLayout) -> QComboBox:
    """Create a *Client Authentication* combo and add it to *form*."""
    w = QComboBox()
    w.addItems(_CLIENT_AUTH_OPTIONS)
    w.setMaximumWidth(_INPUT_MAX_WIDTH)
    _add_row(form, "Client Authentication", w)
    return w


def _set_text(widget: QLineEdit, text: str) -> None:
    """Set text on a QLineEdit without triggering change signals."""
    widget.blockSignals(True)
    widget.setText(text)
    widget.blockSignals(False)
