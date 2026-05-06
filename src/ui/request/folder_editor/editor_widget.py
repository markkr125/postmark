"""Folder detail editor pane with Overview, Authorization, Scripts, Variables, and Runs.

The **Runs** tab hosts an inline collection runner (**New run**) and a
**History** sub-tab for past runs.  Opened when the user double-clicks a
folder in the collection tree.  Changes are auto-saved via the debounced
``collection_changed`` signal.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.run_history_service import RunHistoryService
from ui.request.auth import _AuthMixin
from ui.request.folder_editor.runner_panel import _RunnerPanel
from ui.request.folder_editor.runs import _build_runs_table, _RunsMixin
from ui.request.request_editor.scripts.scripts_mixin import _ScriptsMixin
from ui.widgets.key_value_table import KeyValueTableWidget

_RUN_DETAIL_HEADERS = [
    "Request",
    "Method",
    "Status",
    "Time (ms)",
    "Tests",
    "Result",
]

# Debounce delay (ms) for the collection_changed signal
_DEBOUNCE_MS = 800


class FolderEditorWidget(_AuthMixin, _RunsMixin, _ScriptsMixin, QWidget):
    """Editable folder detail view with Overview, Auth, Scripts, and Variables.

    Call :meth:`load_collection` to populate the pane from a collection dict.
    Emits ``collection_changed`` (debounced) when any field is modified,
    carrying the current data dict for auto-save.
    """

    collection_changed = Signal(dict)
    debug_step_requested = Signal(str)
    open_scripting_settings_requested = Signal()

    # Folders are sources of the inheritance chain, not consumers — no banner.
    _inherited_banners_supported = False

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the folder editor layout."""
        self._script_output_host_kind = "folder"
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

        # ---- Scripts tab (with Pre-request / Post-response sub-tabs) ----
        self._scripts_tab = QWidget()
        scripts_outer = QVBoxLayout(self._scripts_tab)
        scripts_outer.setContentsMargins(0, 0, 0, 0)
        scripts_outer.setSpacing(0)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("scriptSubTabsSep")
        sep.setFixedHeight(1)
        scripts_outer.addWidget(sep)

        self._scripts_sub_tabs = QTabWidget()
        self._scripts_sub_tabs.setObjectName("scriptSubTabs")
        self._scripts_sub_tabs.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)

        self._pre_scripts_tab = QWidget()
        pre_scripts_layout = QVBoxLayout(self._pre_scripts_tab)
        pre_scripts_layout.setContentsMargins(0, 6, 0, 0)
        self._build_pre_request_tab(pre_scripts_layout)
        self._scripts_sub_tabs.addTab(self._pre_scripts_tab, "Pre-request")

        # ---- Post-response sub-tab ----
        self._test_scripts_tab = QWidget()
        test_scripts_layout = QVBoxLayout(self._test_scripts_tab)
        test_scripts_layout.setContentsMargins(0, 6, 0, 0)
        self._build_test_script_tab(test_scripts_layout)
        self._scripts_sub_tabs.addTab(self._test_scripts_tab, "Post-response")

        scripts_outer.addWidget(self._scripts_sub_tabs, 1)
        self._tabs.addTab(self._scripts_tab, "Scripts")

        # ---- Variables tab ----
        self._variables_table = KeyValueTableWidget(
            placeholder_key="Variable name",
            placeholder_value="Variable value",
        )
        self._variables_table.data_changed.connect(self._on_field_changed)
        self._tabs.addTab(self._variables_table, "Variables")

        # ---- Runs tab (New run + History sub-tabs) ----
        self._runs_tab = QWidget()
        runs_outer = QVBoxLayout(self._runs_tab)
        runs_outer.setContentsMargins(0, 0, 0, 0)
        runs_outer.setSpacing(0)

        runs_sep = QFrame()
        runs_sep.setFrameShape(QFrame.Shape.HLine)
        runs_sep.setObjectName("scriptSubTabsSep")
        runs_sep.setFixedHeight(1)
        runs_outer.addWidget(runs_sep)

        self._runs_sub_tabs = QTabWidget()
        self._runs_sub_tabs.setObjectName("scriptSubTabs")
        self._runs_sub_tabs.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)

        self._runner_new_tab = QWidget()
        runner_layout = QVBoxLayout(self._runner_new_tab)
        runner_layout.setContentsMargins(0, 6, 0, 0)
        self._runner_panel = _RunnerPanel()
        self._runner_panel.run_finished.connect(self._on_runner_finished)
        runner_layout.addWidget(self._runner_panel, 1)
        self._runs_sub_tabs.addTab(self._runner_new_tab, "New run")

        self._runner_history_tab = QWidget()
        history_layout = QVBoxLayout(self._runner_history_tab)
        history_layout.setContentsMargins(0, 6, 0, 0)
        self._runs_table = _build_runs_table()
        self._run_detail_table = QTableWidget(0, len(_RUN_DETAIL_HEADERS))
        self._run_detail_table.setHorizontalHeaderLabels(_RUN_DETAIL_HEADERS)
        self._run_detail_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._run_detail_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        detail_header = self._run_detail_table.horizontalHeader()
        if detail_header:
            detail_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for col in range(1, len(_RUN_DETAIL_HEADERS)):
                detail_header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        runs_splitter = QSplitter(Qt.Orientation.Vertical)
        runs_splitter.addWidget(self._runs_table)
        runs_splitter.addWidget(self._run_detail_table)
        runs_splitter.setStretchFactor(0, 2)
        runs_splitter.setStretchFactor(1, 1)
        history_layout.addWidget(runs_splitter, 1)

        self._runs_table.itemSelectionChanged.connect(self._on_run_history_row_selected)
        self._runs_sub_tabs.addTab(self._runner_history_tab, "History")

        runs_outer.addWidget(self._runs_sub_tabs, 1)
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
        self._tabs.setVisible(visible)
        self._empty_label.setVisible(not visible)

    # -- Public properties --------------------------------------------

    @property
    def collection_id(self) -> int | None:
        """Return the database PK of the loaded collection, or ``None``."""
        return self._collection_id

    # -- Load / get / clear -------------------------------------------

    def focus_scripts_panel(self, script_kind: str) -> None:
        """Show the Scripts tab and the Pre-request or Post-response sub-tab.

        *script_kind* is ``"pre_request"`` or ``"test"`` (same as request editor).
        """
        if script_kind not in ("pre_request", "test"):
            return
        main_idx = self._tabs.indexOf(self._scripts_tab)
        if main_idx < 0:
            return
        self._tabs.setCurrentIndex(main_idx)
        self._scripts_sub_tabs.setCurrentIndex(0 if script_kind == "pre_request" else 1)

    def focus_runner_panel(self) -> None:
        """Show the Runs tab with the **New run** sub-tab and refresh runner data."""
        main_idx = self._tabs.indexOf(self._runs_tab)
        if main_idx < 0:
            return
        self._tabs.setCurrentIndex(main_idx)
        self._runs_sub_tabs.setCurrentIndex(0)
        if self._collection_id is not None:
            self._runner_panel.load_collection(self._collection_id)

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
            self._load_scripts(data.get("events"))

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

            if collection_id is not None:
                self._runner_panel.load_collection(collection_id)
            else:
                self._runner_panel.clear()
        finally:
            self._loading = False
        # Script editors populate while ``_loading`` is True, so the debounced
        # Deno banner check from ``textChanged`` was skipped; refresh now.
        self._update_runtime_banners()

    def get_collection_data(self) -> dict:
        """Return the current editor state as a dict suitable for saving."""
        return {
            "description": self._description_edit.toPlainText() or None,
            "auth": self._get_auth_data(),
            "events": self._get_scripts_data(),
            "variables": self._get_variables_data(),
        }

    def clear(self) -> None:
        """Reset the editor to the empty state."""
        self._loading = True
        try:
            self._runner_panel.clear()
            self._collection_id = None
            self._set_content_visible(False)
            self._request_count_label.setText("")
            self._created_label.setText("")
            self._updated_label.setText("")
            self._recent_requests_label.setText("")
            self._description_edit.clear()
            self._clear_auth()
            self._clear_scripts()
            self._variables_table.set_data([])
        finally:
            self._loading = False
        self._update_runtime_banners()

    def shutdown_runner(self) -> None:
        """Stop the collection runner thread before the widget is destroyed."""
        self._runner_panel.shutdown()

    def _on_runner_finished(self) -> None:
        """Reload run history after an inline collection run completes."""
        if self._collection_id is None:
            return
        self.load_runs(RunHistoryService.get_runs(self._collection_id))

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
