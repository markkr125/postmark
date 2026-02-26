"""Environment selector dropdown for the toolbar.

Provides a ``QComboBox`` that lists all available environments and
emits a signal when the active environment changes.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QWidget

from ui.theme import COLOR_BORDER, COLOR_TEXT, COLOR_WHITE

logger = logging.getLogger(__name__)

# Sentinel text for "No Environment" option
_NO_ENVIRONMENT = "No Environment"

# Sentinel userData for the "Manage Environments..." entry
_MANAGE_SENTINEL = "__manage__"


class EnvironmentSelector(QComboBox):
    """Dropdown for selecting the active environment.

    Signals:
        environment_changed(int | None): Emitted with the environment ID
            when selection changes, or ``None`` for no-env.
    """

    environment_changed = Signal(object)  # int | None
    manage_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise with the 'No Environment' placeholder."""
        super().__init__(parent)
        self._prev_index: int = 0
        self.setFixedWidth(180)
        self.setStyleSheet(
            f"""
            QComboBox {{
                background: {COLOR_WHITE};
                border: 1px solid {COLOR_BORDER};
                padding: 4px 8px;
                color: {COLOR_TEXT};
                font-size: 12px;
            }}
            """
        )
        self.addItem(_NO_ENVIRONMENT, userData=None)
        self.currentIndexChanged.connect(self._on_index_changed)

    # -- Public API ----------------------------------------------------

    def load_environments(self, environments: list[dict]) -> None:
        """Populate the dropdown from a list of environment dicts.

        Each dict must have ``id`` and ``name`` keys.  The current
        selection is preserved if possible.
        """
        current_id = self.current_environment_id()
        self.blockSignals(True)
        try:
            self.clear()
            self.addItem(_NO_ENVIRONMENT, userData=None)
            restore_index = 0
            for env in environments:
                self.addItem(env["name"], userData=env["id"])
                if env["id"] == current_id:
                    restore_index = self.count() - 1
            # Separator and manage entry
            self.insertSeparator(self.count())
            self.addItem("Manage Environments\u2026", userData=_MANAGE_SENTINEL)
            self.setCurrentIndex(restore_index)
            self._prev_index = restore_index
        finally:
            self.blockSignals(False)

    def current_environment_id(self) -> int | None:
        """Return the selected environment ID, or ``None``."""
        data = self.currentData()
        if data is None or data == _MANAGE_SENTINEL:
            return None
        return int(data)

    def refresh(self) -> None:
        """Reload environments from the service layer."""
        from services.environment_service import EnvironmentService

        envs = EnvironmentService.fetch_all()
        self.load_environments(envs)

    # -- Internal ------------------------------------------------------

    def _on_index_changed(self, _index: int) -> None:
        """Forward selection change or open manage dialog."""
        if self.currentData() == _MANAGE_SENTINEL:
            self.blockSignals(True)
            self.setCurrentIndex(self._prev_index)
            self.blockSignals(False)
            self.manage_requested.emit()
            return
        self._prev_index = _index
        self.environment_changed.emit(self.current_environment_id())
