"""Configuration view for the collection runner.

Provides data-file picker, iteration count, delay input, and start/cancel
controls.  The actual request execution is handled by the dialog.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.dialogs.collection_runner.worker import parse_data_file
from ui.styling.icons import phi


class RunnerConfigView(QWidget):
    """Configuration panel for runner settings.

    Signals
    -------
    run_requested()
        Emitted when the user clicks Run.
    cancel_requested()
        Emitted when the user clicks Cancel.
    """

    run_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the config view layout."""
        super().__init__(parent)

        self._iteration_data: list[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Info label
        self._info_label = QLabel("Preparing\u2026")
        root.addWidget(self._info_label)

        # Data file / iterations row
        data_row = QHBoxLayout()
        self._data_file_label = QLabel("No data file")
        data_row.addWidget(self._data_file_label, 1)
        data_btn = QPushButton("Data File\u2026")
        data_btn.setIcon(phi("file-csv"))
        data_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        data_btn.clicked.connect(self._pick_data_file)
        data_row.addWidget(data_btn)
        root.addLayout(data_row)

        # Environment selector row
        env_row = QHBoxLayout()
        env_row.addWidget(QLabel("Environment:"))
        self._env_combo = QComboBox()
        self._env_combo.addItem("No Environment", userData=None)
        self._env_combo.setFixedWidth(200)
        env_row.addWidget(self._env_combo)
        env_row.addStretch()
        root.addLayout(env_row)

        # Request selection list (checkboxes)
        req_label = QLabel("Requests:")
        root.addWidget(req_label)
        self._request_list = QListWidget()
        self._request_list.setMaximumHeight(120)
        root.addWidget(self._request_list)

        # Select all / deselect all
        sel_row = QHBoxLayout()
        sel_all_btn = QPushButton("Select All")
        sel_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sel_all_btn.clicked.connect(self._select_all)
        sel_row.addWidget(sel_all_btn)
        desel_btn = QPushButton("Deselect All")
        desel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        desel_btn.clicked.connect(self._deselect_all)
        sel_row.addWidget(desel_btn)
        sel_row.addStretch()
        root.addLayout(sel_row)

        # Iterations + delay row
        settings_row = QHBoxLayout()
        settings_row.addWidget(QLabel("Iterations:"))
        self._iter_spin = QSpinBox()
        self._iter_spin.setRange(1, 10_000)
        self._iter_spin.setValue(1)
        settings_row.addWidget(self._iter_spin)

        settings_row.addSpacing(16)
        settings_row.addWidget(QLabel("Delay (ms):"))
        self._delay_spin = QSpinBox()
        self._delay_spin.setRange(0, 60_000)
        self._delay_spin.setValue(0)
        self._delay_spin.setSingleStep(100)
        settings_row.addWidget(self._delay_spin)

        settings_row.addStretch()
        root.addLayout(settings_row)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._run_btn = QPushButton("Run")
        self._run_btn.setIcon(phi("play"))
        self._run_btn.setObjectName("primaryButton")
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.clicked.connect(self.run_requested)
        btn_row.addWidget(self._run_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setIcon(phi("stop"))
        self._cancel_btn.setObjectName("dangerButton")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.cancel_requested)
        self._cancel_btn.setEnabled(False)
        btn_row.addWidget(self._cancel_btn)
        root.addLayout(btn_row)

    # -- Public API ------------------------------------------------

    @property
    def info_label(self) -> QLabel:
        """Return the info label for external updates."""
        return self._info_label

    @property
    def iterations(self) -> int:
        """Return the configured iteration count."""
        return self._iter_spin.value()

    @property
    def delay_ms(self) -> int:
        """Return the configured delay in milliseconds."""
        return self._delay_spin.value()

    @property
    def iteration_data(self) -> list[dict[str, Any]]:
        """Return the loaded data-file rows."""
        return self._iteration_data

    @property
    def environment_id(self) -> int | None:
        """Return the selected environment ID, or ``None``."""
        data = self._env_combo.currentData()
        return int(data) if data is not None else None

    def load_environments(self, environments: list[dict[str, Any]]) -> None:
        """Populate the environment combo from a list of environment dicts."""
        self._env_combo.clear()
        self._env_combo.addItem("No Environment", userData=None)
        for env in environments:
            self._env_combo.addItem(env["name"], userData=env["id"])

    def load_requests(self, requests: list[dict[str, Any]]) -> None:
        """Populate the request checklist from a list of request dicts."""
        self._request_list.clear()
        for req in requests:
            method = req.get("method", "GET")
            name = req.get("name", "Untitled")
            item = QListWidgetItem(f"{method}  {name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._request_list.addItem(item)

    @property
    def selected_indices(self) -> list[int]:
        """Return indices of checked requests."""
        return [
            i
            for i in range(self._request_list.count())
            if self._request_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def set_request_count(self, count: int) -> None:
        """Update the info label with the request count."""
        self._info_label.setText(f"{count} request(s) to run")

    def set_running(self, running: bool) -> None:
        """Toggle button states between running and idle."""
        self._run_btn.setEnabled(not running)
        self._cancel_btn.setEnabled(running)

    # -- Data file picker -----------------------------------------

    def _pick_data_file(self) -> None:
        """Open a file dialog to choose a CSV or JSON data file."""
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Data File",
            "",
            "Data Files (*.csv *.json);;All Files (*)",
        )
        if not path:
            return
        try:
            self._iteration_data = parse_data_file(Path(path))
            name = Path(path).name
            self._data_file_label.setText(f"{name} ({len(self._iteration_data)} rows)")
            self._iter_spin.setValue(len(self._iteration_data))
        except Exception as exc:
            self._data_file_label.setText(f"Error: {exc}")
            self._iteration_data = []

    def _select_all(self) -> None:
        """Check all request items."""
        for i in range(self._request_list.count()):
            self._request_list.item(i).setCheckState(Qt.CheckState.Checked)

    def _deselect_all(self) -> None:
        """Uncheck all request items."""
        for i in range(self._request_list.count()):
            self._request_list.item(i).setCheckState(Qt.CheckState.Unchecked)
