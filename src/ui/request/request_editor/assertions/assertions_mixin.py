"""Assertions tab mixin for request editors."""

from __future__ import annotations

import logging

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QVBoxLayout, QWidget

from services.assertion_service import AssertionDict, AssertionService
from ui.request.request_editor.assertions.assertions_tab import AssertionsTab
from ui.widgets.lazy_editor_placeholder import LazyEditorPlaceholder

logger = logging.getLogger(__name__)

_SAVE_DEBOUNCE_MS = 500


class _AssertionsMixin:
    """Lazy Assertions tab with DB-backed persistence via :class:`AssertionService`."""

    _assertions_tab: QWidget
    _assertions_tab_layout: QVBoxLayout
    _assertions_placeholder: LazyEditorPlaceholder
    _assertions_editor_materialized: bool
    _assertions_table: AssertionsTab
    _assertions_save_timer: QTimer

    def _init_assertions_tab_shell(self) -> None:
        """Create the Assertions tab placeholder (call from host ``__init__``)."""
        self._assertions_editor_materialized = False
        self._assertions_tab = QWidget()
        self._assertions_tab_layout = QVBoxLayout(self._assertions_tab)
        self._assertions_tab_layout.setContentsMargins(0, 0, 0, 6)
        self._assertions_tab_layout.setSpacing(0)
        self._assertions_placeholder = LazyEditorPlaceholder("Loading assertions\u2026")
        self._assertions_tab_layout.addWidget(self._assertions_placeholder, 1)

    def _ensure_assertions_editors(self) -> None:
        """Build the assertions table once."""
        if self._assertions_editor_materialized:
            return
        self._assertions_tab_layout.removeWidget(self._assertions_placeholder)
        self._assertions_placeholder.hide()
        self._assertions_placeholder.deleteLater()

        self._assertions_table = AssertionsTab(self._assertions_tab)
        self._assertions_tab_layout.addWidget(self._assertions_table, 1)
        self._assertions_save_timer = QTimer(self._assertions_tab)
        self._assertions_save_timer.setSingleShot(True)
        self._assertions_save_timer.setInterval(_SAVE_DEBOUNCE_MS)
        self._assertions_save_timer.timeout.connect(self._persist_assertions)
        self._assertions_table.rows_changed.connect(self._on_assertions_changed)
        self._assertions_editor_materialized = True

        request_id = getattr(self, "_request_id", None)
        if request_id is not None:
            self._load_assertions_for_request(request_id)

    def _load_assertions_for_request(self, request_id: int) -> None:
        """Fetch assertion rows from the service layer."""
        rows = AssertionService.fetch_for_request(request_id)
        self._assertions_table.set_rows(rows)

    def _load_assertions(self) -> None:
        """Load assertions for the current request id, if any."""
        request_id = getattr(self, "_request_id", None)
        if request_id is None:
            if getattr(self, "_assertions_editor_materialized", False):
                self._assertions_table.set_rows([])
            return
        if getattr(self, "_assertions_editor_materialized", False):
            self._load_assertions_for_request(request_id)

    def _clear_assertions(self) -> None:
        """Reset the assertions tab for an empty editor."""
        if getattr(self, "_assertions_editor_materialized", False):
            self._assertions_table.set_rows([])

    def _on_assertions_changed(self) -> None:
        """Debounce persistence and refresh tab indicators."""
        sync = getattr(self, "_sync_tab_indicators", None)
        if callable(sync):
            sync()
        if getattr(self, "_request_id", None) is None:
            return
        self._assertions_save_timer.start()

    def _persist_assertions(self) -> None:
        """Save assertion rows for the loaded request."""
        request_id = getattr(self, "_request_id", None)
        if request_id is None or not getattr(self, "_assertions_editor_materialized", False):
            return
        rows = self._assertions_table.get_rows()
        filtered = [row for row in rows if row.get("subject", "").strip()]
        try:
            AssertionService.save_for_request(request_id, filtered)
        except Exception:
            logger.exception("Failed to save assertions for request %s", request_id)

    def assertions_has_content(self) -> bool:
        """Return whether the assertions tab has at least one subject row."""
        if not getattr(self, "_assertions_editor_materialized", False):
            return False
        return self._assertions_table.has_content()

    def get_assertions_rows(self) -> list[AssertionDict]:
        """Return current assertion rows (for tests)."""
        if not getattr(self, "_assertions_editor_materialized", False):
            return []
        return self._assertions_table.get_rows()
