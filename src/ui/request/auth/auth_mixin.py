"""Shared auth-tab mixin for request and folder editors.

Provides :class:`_AuthMixin` containing auth UI construction
(type selector, stacked field pages for all supported auth types),
inherit-preview logic, and load / save / clear helpers.

Mixed into both :class:`RequestEditorWidget` and
:class:`FolderEditorWidget`.

Auth pages are built **lazily** — only the inherit and no-auth pages
are constructed eagerly.  Field-based pages (bearer, basic, apikey, …)
and the OAuth 2.0 page are materialised on first use (user selection,
data load, or test property access) to avoid ~1 s of widget-creation
overhead per editor instance at startup.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.request.auth.auth_field_specs import AUTH_FIELD_SPECS
from ui.request.auth.auth_pages import (
    AUTH_FIELD_ORDER,
    AUTH_KEY_TO_DISPLAY,
    AUTH_PAGE_INDEX,
    AUTH_TYPE_DESCRIPTIONS,
    AUTH_TYPE_KEYS,
    AUTH_TYPE_LABELS,
    AUTH_TYPES,
    build_fields_page,
    build_inherit_page,
    build_noauth_page,
)
from ui.request.auth.auth_serializer import get_auth_fields, load_auth_fields
from ui.request.auth.oauth2_page import OAuth2Page

if TYPE_CHECKING:
    from PySide6.QtCore import QTimer

    from services.environment_service import VariableDetail
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

        Field-based pages are **not** built here — lightweight placeholder
        widgets are inserted instead.  The real page is materialised on
        first use by :meth:`_ensure_auth_page`.
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
        self._auth_built_pages: set[str] = set()
        self._auth_placeholders: dict[str, QWidget] = {}
        self._auth_variable_map: dict[str, VariableDetail] | None = None

        # 1. Inherit page (index 0) — just a preview label
        inherit_page, _ = build_inherit_page()
        self._auth_fields_stack.addWidget(inherit_page)

        # 2. No Auth page (index 1) — empty placeholder
        self._auth_fields_stack.addWidget(build_noauth_page())

        # 3. Lightweight placeholders for field-based pages.
        #    Real widgets created on demand by _ensure_auth_page().
        self._oauth2_page: OAuth2Page | None = None
        for auth_key in AUTH_FIELD_ORDER:
            placeholder = QWidget()
            self._auth_fields_stack.addWidget(placeholder)
            self._auth_placeholders[auth_key] = placeholder
            self._auth_widget_map[auth_key] = {}

        # OAuth 2.0 worker state
        self._oauth2_thread: QThread | None = None

        columns.addWidget(self._auth_fields_stack, 1)
        auth_layout.addLayout(columns, 1)

    # -- Lazy page construction ----------------------------------------

    def _ensure_auth_page(self, auth_key: str) -> None:
        """Materialise the field page for *auth_key* if not yet built.

        Replaces the lightweight placeholder in the stacked widget with
        the real form page (or :class:`OAuth2Page`).  Applies the stored
        variable map to any :class:`VariableLineEdit` children so that
        ``{{variable}}`` highlighting works immediately.
        """
        if auth_key in self._auth_built_pages:
            return
        if auth_key not in self._auth_placeholders:
            return  # inherit / noauth — always present
        self._auth_built_pages.add(auth_key)

        placeholder = self._auth_placeholders.pop(auth_key)
        idx = self._auth_fields_stack.indexOf(placeholder)
        self._auth_fields_stack.removeWidget(placeholder)
        placeholder.deleteLater()

        if auth_key == "oauth2":
            page: QWidget = OAuth2Page(self._on_field_changed)
            assert isinstance(page, OAuth2Page)
            page.get_token_requested.connect(self._on_get_oauth2_token)
            self._oauth2_page = page
            self._auth_widget_map[auth_key] = {}
        else:
            specs = AUTH_FIELD_SPECS.get(auth_key, ())
            page, widgets = build_fields_page(specs, self._on_field_changed)
            self._auth_widget_map[auth_key] = widgets
            # Apply stored variable map to new VariableLineEdit widgets
            if self._auth_variable_map is not None:
                from ui.widgets.variable_line_edit import VariableLineEdit

                for widget in widgets.values():
                    if isinstance(widget, VariableLineEdit):
                        widget.set_variable_map(self._auth_variable_map)
        self._auth_fields_stack.insertWidget(idx, page)

    # -- Backward-compat lazy properties --------------------------------

    @property
    def _bearer_token_input(self) -> VariableLineEdit:
        """Lazily build the bearer page and return the token input."""
        self._ensure_auth_page("bearer")
        return cast("VariableLineEdit", self._auth_widget_map["bearer"]["token"])

    @property
    def _basic_username_input(self) -> VariableLineEdit:
        """Lazily build the basic-auth page and return the username input."""
        self._ensure_auth_page("basic")
        return cast("VariableLineEdit", self._auth_widget_map["basic"]["username"])

    @property
    def _basic_password_input(self) -> VariableLineEdit:
        """Lazily build the basic-auth page and return the password input."""
        self._ensure_auth_page("basic")
        return cast("VariableLineEdit", self._auth_widget_map["basic"]["password"])

    @property
    def _apikey_key_input(self) -> VariableLineEdit:
        """Lazily build the API-key page and return the key input."""
        self._ensure_auth_page("apikey")
        return cast("VariableLineEdit", self._auth_widget_map["apikey"]["key"])

    @property
    def _apikey_value_input(self) -> VariableLineEdit:
        """Lazily build the API-key page and return the value input."""
        self._ensure_auth_page("apikey")
        return cast("VariableLineEdit", self._auth_widget_map["apikey"]["value"])

    @property
    def _apikey_add_to_combo(self) -> QComboBox:
        """Lazily build the API-key page and return the *Add to* combo."""
        self._ensure_auth_page("apikey")
        return cast(QComboBox, self._auth_widget_map["apikey"]["in"])

    # -- Auth variable map propagation ---------------------------------

    def _set_auth_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Store the variable map and propagate to built auth widgets.

        Pages that have not been materialised yet will receive the map
        when :meth:`_ensure_auth_page` constructs them.
        """
        from ui.widgets.variable_line_edit import VariableLineEdit

        self._auth_variable_map = variables
        for auth_key in self._auth_built_pages:
            for widget in self._auth_widget_map.get(auth_key, {}).values():
                if isinstance(widget, VariableLineEdit):
                    widget.set_variable_map(variables)

    # -- Auth type switching -------------------------------------------

    def _on_auth_type_changed(self, auth_type: str) -> None:
        """Switch the stacked page, update description, and track changes."""
        auth_key = AUTH_TYPE_KEYS.get(auth_type)
        if auth_key:
            self._ensure_auth_page(auth_key)
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

        # Materialise the page before populating fields
        if auth_type not in ("inherit", "noauth"):
            self._ensure_auth_page(auth_type)

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

        self._ensure_auth_page(auth_key)
        if auth_key == "oauth2" and self._oauth2_page is not None:
            entries = self._oauth2_page.get_entries()
        else:
            widgets = self._auth_widget_map.get(auth_key, {})
            entries = get_auth_fields(auth_key, widgets)
        return {"type": auth_key, auth_key: entries}

    def _clear_auth(self) -> None:
        """Reset the auth combo and all field widgets to defaults.

        Only clears pages that have been materialised — unbuilt
        placeholder pages have no widgets to reset.
        """
        self._auth_type_combo.setCurrentText("Inherit auth from parent")
        for auth_key in self._auth_built_pages:
            for widget in self._auth_widget_map.get(auth_key, {}).values():
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
