"""Folder detail editor pane with Overview, Authorization, Scripts, and Variables tabs.

Mirrors the Postman folder view.  Opened when the user double-clicks a
folder in the collection tree.  Changes are auto-saved via the debounced
``collection_changed`` signal.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QStackedWidget, QTabWidget,
                               QTextEdit, QVBoxLayout, QWidget)

from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.key_value_table import KeyValueTableWidget

# Authorization type identifiers (same as RequestEditorWidget)
_AUTH_TYPES = ("Inherit auth from parent", "No Auth", "Bearer Token", "Basic Auth", "API Key")

# Human-readable labels for resolved auth types shown in the inherit preview
_AUTH_TYPE_LABELS: dict[str, str] = {
    "bearer": "Bearer Token",
    "basic": "Basic Auth",
    "apikey": "API Key",
}

# Debounce delay (ms) for the collection_changed signal
_DEBOUNCE_MS = 800


def _normalize_events(events: Any) -> dict[str, str]:
    """Convert events from any format to our internal dict format.

    Accepts:
    - ``None`` or empty → ``{}``
    - Our dict format: ``{"pre_request": "...", "test": "..."}``
    - Postman list format: ``[{"listen": "prerequest", "script": {...}}]``
    """
    if not events:
        return {}
    if isinstance(events, dict):
        return events
    if isinstance(events, list):
        result: dict[str, str] = {}
        listen_map = {"prerequest": "pre_request", "test": "test"}
        for entry in events:
            if not isinstance(entry, dict):
                continue
            listen = entry.get("listen", "")
            our_key = listen_map.get(listen)
            if our_key is None:
                continue
            script = entry.get("script", {})
            if isinstance(script, dict):
                exec_lines = script.get("exec", [])
                if isinstance(exec_lines, list):
                    result[our_key] = "\n".join(exec_lines)
        return result
    return {}


class FolderEditorWidget(QWidget):
    """Editable folder detail view with Overview, Auth, Scripts, and Variables.

    Call :meth:`load_collection` to populate the pane from a collection dict.
    Emits ``collection_changed`` (debounced) when any field is modified,
    carrying the current data dict for auto-save.
    """

    collection_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the folder editor layout."""
        super().__init__(parent)

        self._collection_id: int | None = None
        self._loading: bool = False

        # Debounce timer for collection_changed
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(_DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._emit_collection_changed)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # -- Title label (folder name) --
        self._title_label = QLabel()
        self._title_label.setObjectName("titleLabel")
        root.addWidget(self._title_label)

        # -- Tabbed area --
        self._tabs = QTabWidget()

        # ---- Overview tab ----
        self._overview_tab = QWidget()
        overview_layout = QVBoxLayout(self._overview_tab)
        overview_layout.setContentsMargins(0, 6, 0, 0)

        self._request_count_label = QLabel()
        self._request_count_label.setObjectName("mutedLabel")
        overview_layout.addWidget(self._request_count_label)

        # Metadata row (created / updated)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(24)
        self._created_label = QLabel()
        self._created_label.setObjectName("mutedLabel")
        meta_row.addWidget(self._created_label)
        self._updated_label = QLabel()
        self._updated_label.setObjectName("mutedLabel")
        meta_row.addWidget(self._updated_label)
        meta_row.addStretch()
        overview_layout.addLayout(meta_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        overview_layout.addWidget(sep)

        desc_label = QLabel("Description")
        desc_label.setObjectName("sectionLabel")
        overview_layout.addWidget(desc_label)

        self._description_edit = QTextEdit()
        self._description_edit.setPlaceholderText("Add folder description\u2026")
        self._description_edit.textChanged.connect(self._on_field_changed)
        overview_layout.addWidget(self._description_edit, 1)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        overview_layout.addWidget(sep2)

        # Recent requests section
        recent_label = QLabel("Recent requests")
        recent_label.setObjectName("sectionLabel")
        overview_layout.addWidget(recent_label)
        self._recent_requests_label = QLabel()
        self._recent_requests_label.setObjectName("mutedLabel")
        self._recent_requests_label.setWordWrap(True)
        overview_layout.addWidget(self._recent_requests_label)

        self._tabs.addTab(self._overview_tab, "Overview")

        # ---- Authorization tab ----
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
        self._auth_type_combo.setFixedWidth(200)
        self._auth_type_combo.currentTextChanged.connect(self._on_auth_type_changed)
        auth_type_row.addWidget(self._auth_type_combo)
        auth_type_row.addStretch()
        auth_layout.addLayout(auth_type_row)

        # Auth fields stack
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
        no_auth_page = QLabel("This folder does not use any authorization.")
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
        self._bearer_token_input = QLineEdit()
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
        self._basic_username_input = QLineEdit()
        self._basic_username_input.setPlaceholderText("Username")
        self._basic_username_input.textChanged.connect(self._on_field_changed)
        basic_layout.addWidget(self._basic_username_input)
        password_label = QLabel("Password")
        password_label.setObjectName("sectionLabel")
        basic_layout.addWidget(password_label)
        self._basic_password_input = QLineEdit()
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
        self._apikey_key_input = QLineEdit()
        self._apikey_key_input.setPlaceholderText("Header or query parameter name")
        self._apikey_key_input.textChanged.connect(self._on_field_changed)
        apikey_layout.addWidget(self._apikey_key_input)
        value_label = QLabel("Value")
        value_label.setObjectName("sectionLabel")
        apikey_layout.addWidget(value_label)
        self._apikey_value_input = QLineEdit()
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
        self._tabs.addTab(self._auth_tab, "Authorization")

        # ---- Scripts tab ----
        self._scripts_tab = QWidget()
        scripts_layout = QVBoxLayout(self._scripts_tab)
        scripts_layout.setContentsMargins(0, 6, 0, 0)

        pre_label = QLabel("Pre-request Script")
        pre_label.setObjectName("sectionLabel")
        scripts_layout.addWidget(pre_label)
        self._pre_request_edit = CodeEditorWidget()
        self._pre_request_edit.set_language("javascript")
        self._pre_request_edit.setPlaceholderText("Script to run before the request is sent\u2026")
        self._pre_request_edit.textChanged.connect(self._on_field_changed)
        scripts_layout.addWidget(self._pre_request_edit, 1)

        post_label = QLabel("Tests / Post-response Script")
        post_label.setObjectName("sectionLabel")
        scripts_layout.addWidget(post_label)
        self._test_script_edit = CodeEditorWidget()
        self._test_script_edit.set_language("javascript")
        self._test_script_edit.setPlaceholderText(
            "Script to run after the response is received\u2026"
        )
        self._test_script_edit.textChanged.connect(self._on_field_changed)
        scripts_layout.addWidget(self._test_script_edit, 1)

        self._tabs.addTab(self._scripts_tab, "Scripts")

        # ---- Variables tab ----
        self._variables_table = KeyValueTableWidget(
            placeholder_key="Variable name",
            placeholder_value="Variable value",
        )
        self._variables_table.data_changed.connect(self._on_field_changed)
        self._tabs.addTab(self._variables_table, "Variables")

        root.addWidget(self._tabs, 1)

        # -- Empty state --
        self._empty_label = QLabel("Select a folder to view its details.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("emptyStateLabel")
        root.addWidget(self._empty_label)

        # Start in empty state
        self._set_content_visible(False)

    # -- Visibility helpers -------------------------------------------

    def _set_content_visible(self, visible: bool) -> None:
        """Toggle between the editor content and the empty-state label."""
        self._title_label.setVisible(visible)
        self._tabs.setVisible(visible)
        self._empty_label.setVisible(not visible)

    # -- Public properties --------------------------------------------

    @property
    def collection_id(self) -> int | None:
        """Return the database PK of the loaded collection, or ``None``."""
        return self._collection_id

    # -- Load / get / clear -------------------------------------------

    def load_collection(
        self,
        data: dict,
        *,
        collection_id: int | None = None,
        request_count: int = 0,
        created_at: str | None = None,
        updated_at: str | None = None,
        recent_requests: list[dict[str, Any]] | None = None,
    ) -> None:
        """Populate the editor from a collection data dict.

        Expected keys: ``name``, ``description``, ``auth``, ``events``,
        ``variables``.

        The ``events`` value may be either:
        - Our dict format: ``{"pre_request": "...", "test": "..."}``
        - Postman list format: ``[{"listen": "prerequest", "script": {...}}]``
        Both formats are handled transparently.
        """
        self._loading = True
        try:
            self._collection_id = collection_id
            self._set_content_visible(True)

            self._title_label.setText(data.get("name", ""))

            # Request count
            self._request_count_label.setText(
                f"\u21c5 {request_count} request{'s' if request_count != 1 else ''}"
            )

            # Metadata
            self._created_label.setText(f"Created: {created_at}" if created_at else "")
            self._updated_label.setText(f"Updated: {updated_at}" if updated_at else "")

            # Description
            self._description_edit.setPlainText(data.get("description") or "")

            # Auth
            self._load_auth(data.get("auth"))

            # Scripts (events -- accept both dict and Postman list format)
            events = _normalize_events(data.get("events"))
            self._pre_request_edit.setPlainText(events.get("pre_request") or "")
            self._test_script_edit.setPlainText(events.get("test") or "")

            # Variables
            variables = data.get("variables") or []
            rows = [
                {
                    "key": v.get("key", ""),
                    "value": v.get("value", ""),
                    "description": v.get("description", ""),
                    "enabled": not v.get("disabled", False),
                }
                for v in variables
                if isinstance(v, dict)
            ]
            self._variables_table.set_data(rows)

            # Recent requests
            self._load_recent_requests(recent_requests or [])
        finally:
            self._loading = False

    def _load_auth(self, auth: dict | None) -> None:
        """Populate the auth UI from a Postman-style auth dict.

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

    def get_collection_data(self) -> dict:
        """Return the current editor state as a dict suitable for saving."""
        return {
            "description": self._description_edit.toPlainText() or None,
            "auth": self._get_auth_data(),
            "events": self._get_events_data(),
            "variables": self._get_variables_data(),
        }

    def clear(self) -> None:
        """Reset the editor to the empty state."""
        self._loading = True
        try:
            self._collection_id = None
            self._set_content_visible(False)
            self._title_label.setText("")
            self._request_count_label.setText("")
            self._created_label.setText("")
            self._updated_label.setText("")
            self._recent_requests_label.setText("")
            self._description_edit.clear()
            self._auth_type_combo.setCurrentText("Inherit auth from parent")
            self._bearer_token_input.clear()
            self._basic_username_input.clear()
            self._basic_password_input.clear()
            self._apikey_key_input.clear()
            self._apikey_value_input.clear()
            self._apikey_add_to_combo.setCurrentIndex(0)
            self._pre_request_edit.clear()
            self._test_script_edit.clear()
            self._variables_table.set_data([])
        finally:
            self._loading = False

    # -- Overview helpers ------------------------------------------------

    def _load_recent_requests(self, requests: list[dict[str, Any]]) -> None:
        """Populate the recent-requests label from a list of request dicts.

        Each dict should have ``name``, ``method``, and optionally
        ``updated_at``.
        """
        if not requests:
            self._recent_requests_label.setText("No recent activity.")
            return
        lines: list[str] = []
        for req in requests:
            method = req.get("method", "GET")
            name = req.get("name", "Untitled")
            updated = req.get("updated_at")
            ts_str = f"  ({updated})" if updated else ""
            lines.append(f"{method}  {name}{ts_str}")
        self._recent_requests_label.setText("\n".join(lines))

    # -- Auth helpers --------------------------------------------------

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
            self._debounce_timer.start()

    def _update_inherit_preview(self) -> None:
        """Refresh the inherit page label with the resolved parent auth."""
        from services.collection_service import CollectionService

        collection_id = self._collection_id
        if not collection_id:
            self._inherit_preview_label.setText("No parent auth configured.")
            return
        resolved = CollectionService.get_collection_inherited_auth(collection_id)
        if not resolved:
            self._inherit_preview_label.setText("No parent auth configured.")
            return
        auth_type = resolved.get("type", "")
        label = _AUTH_TYPE_LABELS.get(auth_type, auth_type)
        self._inherit_preview_label.setText(f"Using {label} from parent.")

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
                    {
                        "key": "token",
                        "value": self._bearer_token_input.text(),
                        "type": "string",
                    },
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
                    {
                        "key": "key",
                        "value": self._apikey_key_input.text(),
                        "type": "string",
                    },
                    {
                        "key": "value",
                        "value": self._apikey_value_input.text(),
                        "type": "string",
                    },
                    {
                        "key": "in",
                        "value": add_to,
                        "type": "string",
                    },
                ],
            }
        return None

    # -- Events / scripts helpers --------------------------------------

    def _get_events_data(self) -> dict | None:
        """Build the events dict from the script text edits."""
        pre = self._pre_request_edit.toPlainText()
        test = self._test_script_edit.toPlainText()
        if not pre and not test:
            return None
        return {
            "pre_request": pre or None,
            "test": test or None,
        }

    # -- Variables helper ----------------------------------------------

    def _get_variables_data(self) -> list[dict] | None:
        """Build the variables list from the key-value table."""
        rows = self._variables_table.get_data()
        if not rows:
            return None
        return [
            {
                "key": r.get("key", ""),
                "value": r.get("value", ""),
                "description": r.get("description", ""),
                "disabled": not r.get("enabled", True),
            }
            for r in rows
        ]

    # -- Change tracking -----------------------------------------------

    def _on_field_changed(self) -> None:
        """Handle any field modification and start debounce."""
        if self._loading:
            return
        self._debounce_timer.start()

    def _emit_collection_changed(self) -> None:
        """Emit the debounced collection_changed signal with current data."""
        self.collection_changed.emit(self.get_collection_data())
