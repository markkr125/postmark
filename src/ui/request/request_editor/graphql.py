"""GraphQL editor panel and schema introspection for the request editor.

Provides ``_GraphQLMixin`` with the GraphQL split-pane UI construction
(query + variables editors, schema label, fetch button) and all schema
introspection methods.  Mixed into ``RequestEditorWidget``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSplitter, QVBoxLayout, QWidget

from ui.request.http_worker import SchemaFetchWorker
from ui.styling.icons import phi
from ui.widgets.code_editor import CodeEditorWidget

if TYPE_CHECKING:
    from ui.widgets.key_value_table import KeyValueTableWidget
    from ui.widgets.variable_line_edit import VariableLineEdit


class _GraphQLMixin:
    """Mixin that adds GraphQL editing and schema introspection.

    Expects the host class to provide ``_on_field_changed``,
    ``_url_input``, and ``_headers_table`` attributes.
    """

    # -- Host-class interface (declared for mypy) -----------------------
    _url_input: VariableLineEdit
    _headers_table: KeyValueTableWidget

    def _on_field_changed(self) -> None: ...

    # -- UI construction (called from __init__) -------------------------

    def _build_graphql_page(self) -> QWidget:
        """Build and return the GraphQL split-pane page widget.

        Creates query and variables code editors, a toolbar with
        prettify/wrap/schema buttons, and the schema fetch worker state.
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._gql_prettify_btn = QPushButton("Pretty")
        self._gql_prettify_btn.setIcon(phi("magic-wand", color="#ffffff"))
        self._gql_prettify_btn.setObjectName("smallPrimaryButton")
        self._gql_prettify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gql_prettify_btn.clicked.connect(self._on_gql_prettify)
        toolbar.addWidget(self._gql_prettify_btn)

        self._gql_wrap_btn = QPushButton("Wrap")
        self._gql_wrap_btn.setIcon(phi("text-align-left"))
        self._gql_wrap_btn.setObjectName("outlineButton")
        self._gql_wrap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gql_wrap_btn.setCheckable(True)
        self._gql_wrap_btn.setChecked(True)
        self._gql_wrap_btn.clicked.connect(self._on_gql_wrap_toggle)
        toolbar.addWidget(self._gql_wrap_btn)

        self._gql_error_label = QLabel()
        self._gql_error_label.setObjectName("mutedLabel")
        self._gql_error_label.hide()
        toolbar.addWidget(self._gql_error_label)

        toolbar.addStretch()

        self._gql_schema_label = QPushButton("No schema")
        self._gql_schema_label.setObjectName("outlineButton")
        self._gql_schema_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gql_schema_label.setFlat(True)
        self._gql_schema_label.clicked.connect(self._on_schema_label_clicked)
        toolbar.addWidget(self._gql_schema_label)

        self._gql_fetch_schema_btn = QPushButton()
        self._gql_fetch_schema_btn.setIcon(phi("arrow-clockwise"))
        self._gql_fetch_schema_btn.setObjectName("outlineButton")
        self._gql_fetch_schema_btn.setToolTip("Fetch schema via introspection")
        self._gql_fetch_schema_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gql_fetch_schema_btn.setFixedWidth(30)
        self._gql_fetch_schema_btn.clicked.connect(self._on_fetch_schema)
        toolbar.addWidget(self._gql_fetch_schema_btn)

        layout.addLayout(toolbar)

        # Split pane: query | variables
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("gqlSplitter")
        splitter.setHandleWidth(8)

        # Left pane: QUERY
        query_pane = QWidget()
        query_layout = QVBoxLayout(query_pane)
        query_layout.setContentsMargins(0, 0, 0, 0)
        query_layout.setSpacing(2)
        query_label = QLabel("QUERY")
        query_label.setObjectName("sectionLabel")
        query_layout.addWidget(query_label)
        self._gql_query_editor = CodeEditorWidget()
        self._gql_query_editor.set_language("graphql")
        self._gql_query_editor.textChanged.connect(self._on_field_changed)
        self._gql_query_editor.validation_changed.connect(self._on_gql_validation)
        query_layout.addWidget(self._gql_query_editor, 1)
        splitter.addWidget(query_pane)

        # Right pane: GRAPHQL VARIABLES
        vars_pane = QWidget()
        vars_layout = QVBoxLayout(vars_pane)
        vars_layout.setContentsMargins(0, 0, 0, 0)
        vars_layout.setSpacing(2)
        vars_label = QLabel("GRAPHQL VARIABLES")
        vars_label.setObjectName("sectionLabel")
        vars_layout.addWidget(vars_label)
        self._gql_variables_editor = CodeEditorWidget()
        self._gql_variables_editor.set_language("json")
        self._gql_variables_editor.textChanged.connect(self._on_field_changed)
        vars_layout.addWidget(self._gql_variables_editor, 1)
        splitter.addWidget(vars_pane)

        # Default 60/40 split ratio
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter, 1)

        # Schema introspection state
        self._schema_thread: QThread | None = None
        self._schema_worker: SchemaFetchWorker | None = None
        self._gql_schema: dict | None = None

        return page

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
        from services.http.graphql_schema_service import GraphQLSchemaService

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

        from services.http.graphql_schema_service import GraphQLSchemaService

        summary = GraphQLSchemaService.format_schema_summary(self._gql_schema)  # type: ignore[arg-type]
        self._show_schema_dialog(summary)

    def _show_schema_dialog(self, summary: str) -> None:
        """Display a modal dialog with the fetched schema summary."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox

        dialog = QDialog(self)  # type: ignore[arg-type]
        dialog.setWindowTitle("GraphQL Schema")
        dialog.resize(520, 480)
        dlg_layout = QVBoxLayout(dialog)

        viewer = CodeEditorWidget()
        viewer.set_language("text")
        viewer.setPlainText(summary)
        viewer.setReadOnly(True)
        dlg_layout.addWidget(viewer, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dialog.reject)
        dlg_layout.addWidget(btn_box)

        dialog.exec()
