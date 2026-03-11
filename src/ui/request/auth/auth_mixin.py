"""Shared auth-tab mixin for request and folder editors.

Provides :class:`_AuthMixin` containing auth UI construction
(type selector, stacked field pages for all supported auth types),
inherit-preview logic, and load / save / clear helpers.

Mixed into both :class:`RequestEditorWidget` and
:class:`FolderEditorWidget`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QStackedWidget,
                               QTextEdit, QVBoxLayout, QWidget)

from ui.request.auth.auth_field_specs import AUTH_FIELD_SPECS
from ui.request.auth.auth_pages import (AUTH_FIELD_ORDER, AUTH_KEY_TO_DISPLAY,
                                        AUTH_PAGE_INDEX,
                                        AUTH_TYPE_DESCRIPTIONS, AUTH_TYPE_KEYS,
                                        AUTH_TYPE_LABELS, AUTH_TYPES,
                                        build_fields_page, build_inherit_page,
                                        build_noauth_page)
from ui.request.auth.auth_serializer import get_auth_fields, load_auth_fields
from ui.request.auth.oauth2_page import OAuth2Page

if TYPE_CHECKING:
    from PySide6.QtCore import QTimer

    from ui.widgets.variable_line_edit import VariableLineEdit

logger = logging.getLogger(__name__)


class _AuthMixin:
    """Mixin that adds auth tab building and auth data helpers.

    Expects the host class to provide :meth:`_on_field_changed` and
    a ``_loading`` flag.  Works with both :class:`RequestEditorWidget`
    (which has ``_request_id``) and :class:`FolderEditorWidget`
    (which has ``_collection_id``).
    """

    # -- Host-class interface (declared for type checkers) --------------
    _loading: bool
    _debounce_timer: QTimer

    def _on_field_changed(self) -> None: ...

    # -- UI construction (called from host __init__) --------------------

    def _build_auth_tab(self, auth_layout: QVBoxLayout) -> None:
        """Construct the auth tab with Postman-style two-column layout.

        Left column: auth type selector + description text.
        Right column: stacked field pages for the selected auth type.
        """
        columns = QHBoxLayout()
        columns.setSpacing(0)
        columns.setContentsMargins(0, 0, 0, 0)

        # -- Left column: type picker + description -----------------------
        left = QWidget()
        left.setFixedWidth(260)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 16, 0)

        type_label = QLabel("Auth Type")
        type_label.setObjectName("sectionLabel")
        left_layout.addWidget(type_label)

        self._auth_type_combo = QComboBox()
        self._auth_type_combo.addItems(list(AUTH_TYPES))
        self._auth_type_combo.currentTextChanged.connect(self._on_auth_type_changed)
        left_layout.addWidget(self._auth_type_combo)

        left_layout.addSpacing(12)

        self._auth_description_label = QLabel()
        self._auth_description_label.setObjectName("mutedLabel")
        self._auth_description_label.setWordWrap(True)
        self._auth_description_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._auth_description_label.setText(
            AUTH_TYPE_DESCRIPTIONS.get("Inherit auth from parent", "")
        )
        left_layout.addWidget(self._auth_description_label)

        # Inherit preview sits below the description
        self._inherit_preview_label = QLabel()
        self._inherit_preview_label.setObjectName("sectionLabel")
        self._inherit_preview_label.setWordWrap(True)
        left_layout.addWidget(self._inherit_preview_label)

        left_layout.addStretch()
        columns.addWidget(left)

        # -- Vertical separator -------------------------------------------
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        columns.addWidget(sep)

        # -- Right column: stacked field pages ----------------------------
        self._auth_fields_stack = QStackedWidget()
        self._auth_widget_map: dict[str, dict[str, QWidget]] = {}

        # 1. Inherit page (index 0) — just a preview label
        inherit_page, _ = build_inherit_page()
        self._auth_fields_stack.addWidget(inherit_page)

        # 2. No Auth page (index 1) — empty placeholder
        self._auth_fields_stack.addWidget(build_noauth_page())

        # 3. Field-based pages (bearer, basic, apikey, digest, ...)
        #    OAuth 2.0 gets a custom page instead of FieldSpec.
        self._oauth2_page: OAuth2Page | None = None
        for auth_key in AUTH_FIELD_ORDER:
            if auth_key == "oauth2":
                oauth2_page = OAuth2Page(self._on_field_changed)
                oauth2_page.get_token_requested.connect(self._on_get_oauth2_token)
                self._oauth2_page = oauth2_page
                self._auth_fields_stack.addWidget(oauth2_page)
                self._auth_widget_map[auth_key] = {}
            else:
                specs = AUTH_FIELD_SPECS.get(auth_key, ())
                page, widgets = build_fields_page(specs, self._on_field_changed)
                self._auth_fields_stack.addWidget(page)
                self._auth_widget_map[auth_key] = widgets

        # Backward-compat attributes used by existing tests
        bw = self._auth_widget_map.get("bearer", {})
        self._bearer_token_input = cast("VariableLineEdit", bw.get("token"))
        baw = self._auth_widget_map.get("basic", {})
        self._basic_username_input = cast("VariableLineEdit", baw.get("username"))
        self._basic_password_input = cast("VariableLineEdit", baw.get("password"))
        akw = self._auth_widget_map.get("apikey", {})
        self._apikey_key_input = cast("VariableLineEdit", akw.get("key"))
        self._apikey_value_input = cast("VariableLineEdit", akw.get("value"))
        self._apikey_add_to_combo = cast(QComboBox, akw.get("in"))

        # OAuth 2.0 worker state
        self._oauth2_thread: QThread | None = None

        columns.addWidget(self._auth_fields_stack, 1)
        auth_layout.addLayout(columns, 1)

    # -- Auth type switching -------------------------------------------

    def _on_auth_type_changed(self, auth_type: str) -> None:
        """Switch the stacked page, update description, and track changes."""
        idx = AUTH_PAGE_INDEX.get(auth_type, 0)
        self._auth_fields_stack.setCurrentIndex(idx)
        self._auth_description_label.setText(AUTH_TYPE_DESCRIPTIONS.get(auth_type, ""))
        is_inherit = auth_type == "Inherit auth from parent"
        self._inherit_preview_label.setVisible(is_inherit)
        if is_inherit:
            self._update_inherit_preview()
        self._on_field_changed()

    # -- Inherit preview -----------------------------------------------

    def _update_inherit_preview(self) -> None:
        """Refresh the inherit page label with the resolved parent auth."""
        from services.collection_service import CollectionService

        request_id = getattr(self, "_request_id", None)
        collection_id = getattr(self, "_collection_id", None)
        if request_id:
            resolved = CollectionService.get_request_inherited_auth(request_id)
        elif collection_id:
            resolved = CollectionService.get_collection_inherited_auth(collection_id)
        else:
            self._inherit_preview_label.setText("No parent auth configured.")
            return
        self._set_inherit_preview_from_auth(resolved)

    def _set_inherit_preview_from_auth(self, auth: dict[str, Any] | None) -> None:
        """Set the inherit preview label from a resolved auth dict."""
        if not auth:
            self._inherit_preview_label.setText("No parent auth configured.")
            return
        auth_type = auth.get("type", "")
        label = AUTH_TYPE_LABELS.get(auth_type, auth_type)
        self._inherit_preview_label.setText(f"Using {label} from parent.")

    # -- OAuth 2.0 token flow ------------------------------------------

    def _on_get_oauth2_token(self) -> None:
        """Launch the OAuth 2.0 token worker on a background thread."""
        if self._oauth2_page is None:
            return

        config = self._oauth2_page.get_config()
        if not config:
            return

        from ui.request.http_worker import OAuth2TokenWorker

        worker = OAuth2TokenWorker()
        worker.set_config(config)

        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_oauth2_token_received)
        worker.error.connect(self._on_oauth2_token_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._oauth2_thread = thread
        thread.start()

    def _on_oauth2_token_received(self, data: dict) -> None:
        """Store the obtained token in the OAuth 2.0 page."""
        if self._oauth2_page is None:
            return
        token = data.get("access_token", "")
        name = self._oauth2_page.get_config().get("tokenName", "")
        if token:
            self._oauth2_page.set_token(token, str(name))
            self._on_field_changed()

    def _on_oauth2_token_error(self, msg: str) -> None:
        """Show an error dialog when the token flow fails."""
        logger.error("OAuth 2.0 token error: %s", msg)
        parent = self if isinstance(self, QWidget) else None
        QMessageBox.warning(parent, "OAuth 2.0 Error", msg)

    # -- Load / save / clear -------------------------------------------

    def _load_auth(self, auth: dict | None) -> None:
        """Populate auth fields from a Postman-format auth dict.

        ``None`` or ``{}`` maps to *Inherit auth from parent*.
        ``{"type": "noauth"}`` maps to *No Auth*.
        """
        if not auth:
            self._auth_type_combo.setCurrentText("Inherit auth from parent")
            return

        auth_type = auth.get("type", "inherit")
        display = AUTH_KEY_TO_DISPLAY.get(auth_type, "Inherit auth from parent")
        self._auth_type_combo.setCurrentText(display)

        entries = auth.get(auth_type, [])
        if auth_type == "oauth2" and self._oauth2_page is not None:
            self._oauth2_page.load(entries)
        else:
            widgets = self._auth_widget_map.get(auth_type, {})
            if entries and widgets:
                load_auth_fields(auth_type, widgets, entries)

    def _get_auth_data(self) -> dict | None:
        """Build the auth configuration dict from the current UI state.

        Returns ``None`` for *Inherit auth from parent* (stored as
        ``auth = None`` in the database).
        """
        display_name = self._auth_type_combo.currentText()
        if display_name == "Inherit auth from parent":
            return None
        if display_name == "No Auth":
            return {"type": "noauth"}

        auth_key = AUTH_TYPE_KEYS.get(display_name)
        if not auth_key:
            return None

        if auth_key == "oauth2" and self._oauth2_page is not None:
            entries = self._oauth2_page.get_entries()
        else:
            widgets = self._auth_widget_map.get(auth_key, {})
            entries = get_auth_fields(auth_key, widgets)
        return {"type": auth_key, auth_key: entries}

    def _clear_auth(self) -> None:
        """Reset the auth combo and all field widgets to defaults."""
        self._auth_type_combo.setCurrentText("Inherit auth from parent")
        for widgets in self._auth_widget_map.values():
            for widget in widgets.values():
                if isinstance(widget, QLineEdit):
                    widget.clear()
                elif isinstance(widget, QComboBox):
                    widget.setCurrentIndex(0)
                elif isinstance(widget, QTextEdit):
                    widget.clear()
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(False)
        if self._oauth2_page is not None:
            self._oauth2_page.clear()
