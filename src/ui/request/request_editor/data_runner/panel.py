"""Data file picker and preview for inline data-driven script runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.scripting.data_loader import parse_data_file
from ui.styling.icons import phi
from ui.styling.theme import COLOR_TEXT_MUTED

_PREVIEW_ROW_LIMIT = 5


class DataRunnerPanel(QWidget):
    """Pick a CSV/JSON data file, preview rows, and launch iteration runs.

    Signals
    -------
    run_requested(list, int)
        Emitted when the user clicks **Run iterations** with
        ``(iteration_data, iteration_count)``.
    """

    run_requested = Signal(list, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build file picker, preview table, and iteration controls."""
        super().__init__(parent)
        self._iteration_data: list[dict[str, Any]] = []
        self._build_ui()

    @property
    def iteration_data(self) -> list[dict[str, Any]]:
        """Parsed rows from the last successfully loaded data file."""
        return list(self._iteration_data)

    @property
    def iteration_count(self) -> int:
        """Configured iteration count (may exceed loaded row count)."""
        return self._iter_spin.value()

    def has_data(self) -> bool:
        """Return ``True`` when a data file with at least one row is loaded."""
        return bool(self._iteration_data)

    def _build_ui(self) -> None:
        """Lay out picker, preview, and run controls."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 4)
        root.setSpacing(4)

        pick_row = QHBoxLayout()
        self._file_label = QLabel("No data file")
        self._file_label.setObjectName("mutedLabel")
        pick_row.addWidget(self._file_label, 1)

        pick_btn = QPushButton("Data file…")
        pick_btn.setIcon(phi("file-csv"))
        pick_btn.setObjectName("outlineButton")
        pick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pick_btn.setToolTip(
            "CSV or JSON — each row drives one script iteration.\n"
            "Values are available as pm.iterationData in the script."
        )
        pick_btn.clicked.connect(self._pick_data_file)
        pick_row.addWidget(pick_btn)
        root.addLayout(pick_row)

        help_lbl = QLabel(
            "Each row runs the current script once with pm.iterationData set to that row."
        )
        help_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
        help_lbl.setWordWrap(True)
        root.addWidget(help_lbl)

        self._preview = QTableWidget(0, 0)
        self._preview.setObjectName("dataRunnerPreviewTable")
        self._preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._preview.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._preview.setMaximumHeight(120)
        self._preview.hide()
        root.addWidget(self._preview)

        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel("Iterations:"))
        self._iter_spin = QSpinBox()
        self._iter_spin.setRange(1, 9999)
        self._iter_spin.setValue(1)
        self._iter_spin.setToolTip("Number of iterations (defaults to row count when a file loads)")
        ctrl_row.addWidget(self._iter_spin)
        ctrl_row.addStretch()

        self._run_btn = QPushButton("Run iterations")
        self._run_btn.setIcon(phi("play"))
        self._run_btn.setObjectName("smallPrimaryButton")
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._emit_run_requested)
        ctrl_row.addWidget(self._run_btn)
        root.addLayout(ctrl_row)

    def _pick_data_file(self) -> None:
        """Open a file dialog and parse the selected CSV/JSON file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select data file",
            "",
            "Data files (*.csv *.json);;CSV (*.csv);;JSON (*.json)",
        )
        if not path:
            return
        try:
            rows = parse_data_file(Path(path))
        except Exception as exc:
            self._file_label.setText(f"Error: {exc}")
            self._iteration_data = []
            self._preview.hide()
            self._run_btn.setEnabled(False)
            return

        self._iteration_data = rows
        name = Path(path).name
        self._file_label.setText(f"{name} ({len(rows)} rows)")
        self._refresh_preview()
        count = max(1, len(rows))
        self._iter_spin.setValue(count)
        self._run_btn.setEnabled(bool(rows))

    def _refresh_preview(self) -> None:
        """Show the first N rows of loaded data in the preview table."""
        rows = self._iteration_data[:_PREVIEW_ROW_LIMIT]
        if not rows:
            self._preview.hide()
            return

        columns = list(dict.fromkeys(k for row in rows for k in row))
        self._preview.setColumnCount(len(columns))
        self._preview.setHorizontalHeaderLabels(columns)
        self._preview.setRowCount(len(rows))
        for r_idx, row in enumerate(rows):
            for c_idx, col in enumerate(columns):
                self._preview.setItem(r_idx, c_idx, QTableWidgetItem(str(row.get(col, ""))))
        self._preview.show()

    def _emit_run_requested(self) -> None:
        """Emit :py:attr:`run_requested` when data is loaded."""
        if not self._iteration_data:
            return
        self.run_requested.emit(list(self._iteration_data), self._iter_spin.value())
