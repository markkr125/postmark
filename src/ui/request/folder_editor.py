"""Folder detail editor pane with Overview, Authorization, Scripts, and Variables tabs.

Mirrors the Postman folder view.  Opened when the user double-clicks a
folder in the collection tree.  Changes are auto-saved via the debounced
``collection_changed`` signal.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.script_version_service import ScriptVersionService
from services.scripting.context import normalize_events as _normalize_events
from ui.request.auth import _AuthMixin
from ui.styling.icons import phi
from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.key_value_table import KeyValueTableWidget

# Debounce delay (ms) for the collection_changed signal
_DEBOUNCE_MS = 800

# Debounce delay (ms) for version capture after script edits.
_VERSION_CAPTURE_MS = 2000


# Supported script languages (display label → CodeEditorWidget language)
_SCRIPT_LANGUAGES: dict[str, str] = {
    "JavaScript": "javascript",
    "Python": "python",
}


_RUNS_HEADERS = [
    "Start time",
    "Source",
    "Duration",
    "All tests",
    "Passed",
    "Failed",
    "Skipped",
    "Avg. Resp. Time",
    "Status",
]


def _build_runs_table() -> QTableWidget:
    """Create a read-only table widget for displaying run history."""
    table = QTableWidget(0, len(_RUNS_HEADERS))
    table.setHorizontalHeaderLabels(_RUNS_HEADERS)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    header = table.horizontalHeader()
    if header:
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(_RUNS_HEADERS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
    return table


class FolderEditorWidget(_AuthMixin, QWidget):
    """Editable folder detail view with Overview, Auth, Scripts, and Variables.

    Call :meth:`load_collection` to populate the pane from a collection dict.
    Emits ``collection_changed`` (debounced) when any field is modified,
    carrying the current data dict for auto-save.
    """

    collection_changed = Signal(dict)
    run_requested = Signal(int)  # collection_id

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

        # -- Title row (folder name + Run button) --
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        self._title_label = QLabel()
        self._title_label.setObjectName("titleLabel")
        title_row.addWidget(self._title_label, 1)
        self._run_btn = QPushButton("Run")
        self._run_btn.setIcon(phi("play"))
        self._run_btn.setObjectName("primaryButton")
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.clicked.connect(self._on_run_clicked)
        title_row.addWidget(self._run_btn)
        root.addLayout(title_row)

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

        self._build_auth_tab(auth_layout)
        self._tabs.addTab(self._auth_tab, "Authorization")

        # ---- Scripts tab ----
        self._scripts_tab = QWidget()
        scripts_layout = QVBoxLayout(self._scripts_tab)
        scripts_layout.setContentsMargins(0, 6, 0, 0)

        # Language selector row
        lang_row = QHBoxLayout()
        lang_row.setContentsMargins(0, 0, 0, 0)
        lang_label = QLabel("Language")
        lang_label.setObjectName("mutedLabel")
        lang_row.addWidget(lang_label)
        self._script_lang_combo = QComboBox()
        self._script_lang_combo.addItems(list(_SCRIPT_LANGUAGES.keys()))
        self._script_lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._script_lang_combo.setFixedWidth(120)
        self._script_lang_combo.currentTextChanged.connect(self._on_script_language_changed)
        lang_row.addWidget(self._script_lang_combo)

        self._history_btn = QPushButton("History")
        self._history_btn.setIcon(phi("clock-counter-clockwise", size=14))
        self._history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._history_btn.setToolTip("View script version history")
        self._history_btn.clicked.connect(self._open_version_history)
        lang_row.addWidget(self._history_btn)
        lang_row.addStretch()

        scripts_layout.addLayout(lang_row)

        pre_label = QLabel("Pre-request Script")
        pre_label.setObjectName("sectionLabel")
        scripts_layout.addWidget(pre_label)
        self._pre_request_edit = CodeEditorWidget()
        self._pre_request_edit.set_language("javascript")
        self._pre_request_edit.setPlaceholderText("Script to run before the request is sent\u2026")
        self._pre_request_edit.textChanged.connect(self._on_field_changed)
        self._pre_request_edit.textChanged.connect(self._schedule_version_capture)
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
        self._test_script_edit.textChanged.connect(self._schedule_version_capture)
        scripts_layout.addWidget(self._test_script_edit, 1)

        # Version capture debounce timer
        self._version_capture_timer = QTimer(self)
        self._version_capture_timer.setSingleShot(True)
        self._version_capture_timer.setInterval(_VERSION_CAPTURE_MS)
        self._version_capture_timer.timeout.connect(self._capture_script_versions)

        self._tabs.addTab(self._scripts_tab, "Scripts")

        # ---- Variables tab ----
        self._variables_table = KeyValueTableWidget(
            placeholder_key="Variable name",
            placeholder_value="Variable value",
        )
        self._variables_table.data_changed.connect(self._on_field_changed)
        self._tabs.addTab(self._variables_table, "Variables")

        # ---- Runs tab ----
        self._runs_tab = QWidget()
        runs_layout = QVBoxLayout(self._runs_tab)
        runs_layout.setContentsMargins(0, 6, 0, 0)

        self._runs_table = _build_runs_table()
        runs_layout.addWidget(self._runs_table, 1)

        self._tabs.addTab(self._runs_tab, "Runs")

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

            # Script language
            lang_display = "JavaScript"
            raw_events = data.get("events")
            if isinstance(raw_events, dict):
                stored_lang = raw_events.get("language", "").lower()
                for display, code in _SCRIPT_LANGUAGES.items():
                    if code == stored_lang:
                        lang_display = display
                        break
            self._script_lang_combo.setCurrentText(lang_display)

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
            self._clear_auth()
            self._pre_request_edit.clear()
            self._test_script_edit.clear()
            self._script_lang_combo.setCurrentText("JavaScript")
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

    # -- Events / scripts helpers --------------------------------------

    def _get_events_data(self) -> dict | None:
        """Build the events dict from the script text edits."""
        pre = self._pre_request_edit.toPlainText()
        test = self._test_script_edit.toPlainText()
        if not pre and not test:
            return None
        lang = _SCRIPT_LANGUAGES.get(self._script_lang_combo.currentText(), "javascript")
        return {
            "pre_request": pre or None,
            "test": test or None,
            "language": lang,
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

    def _on_script_language_changed(self, display_name: str) -> None:
        """Update both editors when the language selector changes."""
        lang = _SCRIPT_LANGUAGES.get(display_name, "javascript")
        self._pre_request_edit.set_language(lang)
        self._test_script_edit.set_language(lang)
        if not self._loading:
            self._debounce_timer.start()

    def _on_field_changed(self) -> None:
        """Handle any field modification and start debounce."""
        if self._loading:
            return
        self._debounce_timer.start()

    def _emit_collection_changed(self) -> None:
        """Emit the debounced collection_changed signal with current data."""
        self.collection_changed.emit(self.get_collection_data())

    # -- Script version capture ----------------------------------------

    def _schedule_version_capture(self) -> None:
        """Restart the debounce timer on any script text change."""
        if self._loading:
            return
        self._version_capture_timer.start()

    def _capture_script_versions(self) -> None:
        """Capture current script content as version snapshots."""
        if self._collection_id is None:
            return
        lang = _SCRIPT_LANGUAGES.get(self._script_lang_combo.currentText(), "javascript")

        pre = self._pre_request_edit.toPlainText()
        if pre.strip():
            ScriptVersionService.capture(
                request_id=None,
                collection_id=self._collection_id,
                script_type="pre_request",
                content=pre,
                language=lang,
            )

        test = self._test_script_edit.toPlainText()
        if test.strip():
            ScriptVersionService.capture(
                request_id=None,
                collection_id=self._collection_id,
                script_type="test",
                content=test,
                language=lang,
            )

    def _open_version_history(self) -> None:
        """Open the version history dialog for this collection."""
        from ui.request.request_editor.scripts.version_history import VersionHistoryDialog

        if self._collection_id is None:
            return

        dlg = VersionHistoryDialog(
            request_id=None,
            collection_id=self._collection_id,
            current_pre=self._pre_request_edit.toPlainText(),
            current_test=self._test_script_edit.toPlainText(),
            parent=self._pre_request_edit,
        )
        if dlg.exec():
            restored = dlg.restored_content()
            if restored:
                script_type, content = restored
                editor = (
                    self._pre_request_edit
                    if script_type == "pre_request"
                    else self._test_script_edit
                )
                editor.selectAll()
                editor.insertPlainText(content)

    # -- Run actions ---------------------------------------------------

    def _on_run_clicked(self) -> None:
        """Emit run_requested when the Run button is clicked."""
        if self._collection_id is not None:
            self.run_requested.emit(self._collection_id)

    def load_runs(self, runs: list[dict]) -> None:
        """Populate the Runs tab table with run history data.

        Each dict should contain ``started_at``, ``source``, ``duration_ms``,
        ``total_tests``, ``passed``, ``failed``, ``avg_response_ms``, and
        ``status``.
        """
        self._runs_table.setRowCount(0)
        for run in runs:
            row = self._runs_table.rowCount()
            self._runs_table.insertRow(row)

            started = run.get("started_at", "")
            if hasattr(started, "strftime"):
                started = started.strftime("%Y-%m-%d %H:%M:%S")
            self._runs_table.setItem(row, 0, QTableWidgetItem(str(started)))
            self._runs_table.setItem(row, 1, QTableWidgetItem(run.get("source", "")))

            dur = run.get("duration_ms", 0)
            dur_str = f"{dur / 1000:.1f}s" if dur >= 1000 else f"{dur}ms"
            self._runs_table.setItem(row, 2, QTableWidgetItem(dur_str))

            self._runs_table.setItem(row, 3, QTableWidgetItem(str(run.get("total_tests", 0))))
            self._runs_table.setItem(row, 4, QTableWidgetItem(str(run.get("passed", 0))))
            self._runs_table.setItem(row, 5, QTableWidgetItem(str(run.get("failed", 0))))
            self._runs_table.setItem(row, 6, QTableWidgetItem(str(run.get("skipped", 0))))

            avg = run.get("avg_response_ms", 0.0)
            self._runs_table.setItem(row, 7, QTableWidgetItem(f"{avg:.0f}ms"))
            self._runs_table.setItem(row, 8, QTableWidgetItem(run.get("status", "")))
