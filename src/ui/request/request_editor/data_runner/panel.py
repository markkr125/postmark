"""Data file picker and preview for inline data-driven script runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.scripting.data_loader import parse_data_file
from ui.styling.icons import phi
from ui.styling.theme import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_SOLID_BUTTON_FG,
    COLOR_SUCCESS,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
)

_PREVIEW_ROW_LIMIT = 5

_HEADING_TEXT = "Run this script once per row of a data file"
_SUBTITLE_HTML = (
    "Run the same script with <b>different inputs each time</b> — one row "
    "per run. Put anything you want to vary in the file (request IDs, "
    "expected status codes, credentials, …)."
)

_HELP_DIALOG_TITLE = "How iteration runs work"
_HELP_INTRO_HTML = (
    "Iteration runs let you execute the same pre/post-response script many "
    "times in a row, each time with a different row of values from a data "
    "file. Inside the script, the current row is exposed as "
    "<code>pm.iterationData</code>."
)
_HELP_FILE_RULES_HTML = (
    "<b>The file you provide</b>"
    "<ul>"
    "<li>Format: <b>.csv</b> or <b>.json</b>.</li>"
    "<li>For CSV, the <b>first row is the header</b> — its values become "
    "column names. Subsequent rows are the data.</li>"
    "<li>For JSON, supply <b>an array of objects</b>. The object keys are "
    "the column names.</li>"
    "<li>Column names are <b>entirely up to you</b> — pick whatever fits "
    "what the script needs.</li>"
    "<li>Each row in the file becomes one run (one iteration) of the "
    "script.</li>"
    "</ul>"
)
_HELP_SCENARIO_HTML = (
    "<b>Worked example.</b> You want to verify that "
    "<code>GET /users/{id}</code> returns <code>200</code> for a real user "
    "and <code>404</code> for a missing one. Save this two-row file as "
    "<code>users.csv</code> — the columns <code>userId</code> and "
    "<code>expectedStatus</code> are names you chose:"
)
_CSV_EXAMPLE = "userId,expectedStatus\n1,200\n999,404"
_JSON_EXAMPLE = (
    '[\n  {"userId": 1,   "expectedStatus": 200},\n  {"userId": 999, "expectedStatus": 404}\n]'
)
_SCRIPT_EXAMPLE = (
    "const id = pm.iterationData.userId;\n"
    "const expected = pm.iterationData.expectedStatus;\n"
    "pm.test(`GET /users/${id} → ${expected}`, () => {\n"
    "  pm.response.to.have.status(expected);\n"
    "});"
)
_HELP_OUTCOME_HTML = (
    "Load <code>users.csv</code>, then click <b>Run iterations</b>. The "
    "script runs twice: first with "
    "<code>pm.iterationData = {userId: 1, expectedStatus: 200}</code>, then "
    "with <code>{userId: 999, expectedStatus: 404}</code>. Each iteration "
    "becomes a row in the results matrix below — click any row to drill "
    "into that iteration's output."
)

_PICK_BTN_TOOLTIP = (
    "Choose a CSV or JSON file.\n"
    "Each row becomes one iteration; columns are read in the script "
    "via pm.iterationData."
)
_CHANGE_BTN_TOOLTIP = "Replace the current data file with a different CSV or JSON file."
_CLEAR_BTN_TOOLTIP = "Unload the current data file and return to the empty state."
_RUN_DISABLED_TIP = (
    "Disabled — load a CSV or JSON data file first using the “Choose data file…”\n"
    "button. Each row of that file becomes one script iteration."
)
_RUN_ENABLED_TIP = (
    "Run this script once per loaded row. Each row is exposed inside the "
    "script as pm.iterationData."
)
_SPIN_TOOLTIP = (
    "Number of iterations to run.\n"
    "Defaults to the loaded row count; lower it to run only the first N rows, "
    "or raise it to repeat rows."
)
_HELP_BTN_TOOLTIP = "Open a step-by-step walkthrough with a sample CSV and script."


class IterationsHelpDialog(QDialog):
    """Modal walkthrough showing what a data file is and how the script reads it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the help dialog with example script and data-file walkthrough."""
        super().__init__(parent)
        self.setWindowTitle(_HELP_DIALOG_TITLE)
        self.setModal(True)
        self.resize(720, 640)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(12)

        heading = QLabel(_HELP_DIALOG_TITLE)
        heading.setObjectName("titleLabel")
        outer.addWidget(heading)

        intro = QLabel(_HELP_INTRO_HTML)
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setWordWrap(True)
        outer.addWidget(intro)

        file_rules = QLabel(_HELP_FILE_RULES_HTML)
        file_rules.setTextFormat(Qt.TextFormat.RichText)
        file_rules.setWordWrap(True)
        outer.addWidget(file_rules)

        scenario = QLabel(_HELP_SCENARIO_HTML)
        scenario.setTextFormat(Qt.TextFormat.RichText)
        scenario.setWordWrap(True)
        outer.addWidget(scenario)

        examples_row = QHBoxLayout()
        examples_row.setSpacing(8)
        examples_row.addWidget(_build_example_card("1. Data file (users.csv)", _CSV_EXAMPLE), 1)
        examples_row.addWidget(_build_example_card("Or the same as JSON", _JSON_EXAMPLE), 1)
        outer.addLayout(examples_row)

        script_intro = QLabel(
            "Then in your post-response script, read the columns via <code>pm.iterationData</code>:"
        )
        script_intro.setTextFormat(Qt.TextFormat.RichText)
        script_intro.setWordWrap(True)
        outer.addWidget(script_intro)

        outer.addWidget(_build_example_card("2. Script that uses the data", _SCRIPT_EXAMPLE))

        outcome = QLabel(_HELP_OUTCOME_HTML)
        outcome.setTextFormat(Qt.TextFormat.RichText)
        outcome.setWordWrap(True)
        outer.addWidget(outcome)

        outer.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setObjectName("outlineButton")
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        outer.addWidget(buttons)


def _build_example_card(title: str, code: str) -> QFrame:
    """Bordered card with a small caption and a monospace code block."""
    card = QFrame()
    card.setFrameShape(QFrame.Shape.NoFrame)
    card.setStyleSheet(f"QFrame {{ border: 1px solid {COLOR_BORDER}; border-radius: 4px; }}")
    inner = QVBoxLayout(card)
    inner.setContentsMargins(8, 6, 8, 8)
    inner.setSpacing(4)

    caption = QLabel(title)
    caption.setStyleSheet(
        f"color: {COLOR_TEXT_MUTED}; font-size: 10px; "
        "font-weight: bold; text-transform: uppercase; border: none;"
    )
    inner.addWidget(caption)

    code_label = QLabel(code)
    code_label.setTextFormat(Qt.TextFormat.PlainText)
    code_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    code_label.setStyleSheet(
        f"color: {COLOR_TEXT}; font-family: monospace; font-size: 11px; border: none;"
    )
    code_label.setWordWrap(False)
    inner.addWidget(code_label)
    inner.addStretch()
    return card


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
        """Build heading, onboarding empty state, and loaded compact state."""
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._iteration_data: list[dict[str, Any]] = []
        self._loaded_file_name: str = ""
        self._build_ui()
        self._show_empty_state()

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
        """Lay out heading + show/hide empty and loaded states."""
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 4)
        root.setSpacing(6)

        heading = QLabel(_HEADING_TEXT)
        heading.setObjectName("sectionLabel")
        heading.setWordWrap(True)
        root.addWidget(heading)

        subtitle = QLabel(_SUBTITLE_HTML)
        subtitle.setObjectName("mutedLabel")
        subtitle.setTextFormat(Qt.TextFormat.RichText)
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self._empty_state = self._build_empty_state()
        self._loaded_state = self._build_loaded_state()
        root.addWidget(self._empty_state)
        root.addWidget(self._loaded_state)
        self._loaded_state.hide()
        self._refresh_run_button_state()

    def _build_empty_state(self) -> QWidget:
        """Onboarding card: CTA button + a help-dialog link."""
        page = QWidget()
        page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 4, 0, 0)
        col.setSpacing(8)

        cta_row = QHBoxLayout()
        cta_row.setSpacing(10)
        self._cta_pick_btn = QPushButton("Choose data file…")
        self._cta_pick_btn.setIcon(phi("file-csv", color=COLOR_SOLID_BUTTON_FG, size=14))
        self._cta_pick_btn.setIconSize(QSize(14, 14))
        self._cta_pick_btn.setObjectName("smallPrimaryButton")
        self._cta_pick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cta_pick_btn.setToolTip(_PICK_BTN_TOOLTIP)
        self._cta_pick_btn.clicked.connect(self._pick_data_file)
        cta_row.addWidget(self._cta_pick_btn)

        self._help_btn = QPushButton("How does this work?")
        self._help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._help_btn.setFlat(True)
        self._help_btn.setToolTip(_HELP_BTN_TOOLTIP)
        self._help_btn.setStyleSheet(
            f"QPushButton {{ border: none; padding: 4px 2px; "
            f"color: {COLOR_ACCENT}; font-size: 12px; "
            f"text-decoration: underline; }} "
            f"QPushButton:hover {{ color: {COLOR_TEXT}; }}"
        )
        self._help_btn.clicked.connect(self._open_help_dialog)
        cta_row.addWidget(self._help_btn)
        cta_row.addStretch()
        col.addLayout(cta_row)
        return page

    def _build_loaded_state(self) -> QWidget:
        """Compact state once a file is loaded: status + preview + run controls."""
        page = QWidget()
        page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 4, 0, 0)
        col.setSpacing(6)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self._loaded_label = QLabel()
        self._loaded_label.setTextFormat(Qt.TextFormat.RichText)
        self._loaded_label.setWordWrap(True)
        status_row.addWidget(self._loaded_label, 1)

        self._change_btn = QPushButton("Change…")
        self._change_btn.setObjectName("outlineButton")
        self._change_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._change_btn.setToolTip(_CHANGE_BTN_TOOLTIP)
        self._change_btn.clicked.connect(self._pick_data_file)
        status_row.addWidget(self._change_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setObjectName("outlineButton")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setToolTip(_CLEAR_BTN_TOOLTIP)
        self._clear_btn.clicked.connect(self._clear_data_file)
        status_row.addWidget(self._clear_btn)
        col.addLayout(status_row)

        self._preview = QTableWidget(0, 0)
        self._preview.setObjectName("dataRunnerPreviewTable")
        self._preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._preview.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._preview.setMaximumHeight(120)
        col.addWidget(self._preview)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)
        iter_label = QLabel("Iterations:")
        iter_label.setObjectName("mutedLabel")
        iter_label.setToolTip(_SPIN_TOOLTIP)
        ctrl_row.addWidget(iter_label)
        self._iter_spin = QSpinBox()
        self._iter_spin.setRange(1, 9999)
        self._iter_spin.setValue(1)
        self._iter_spin.setToolTip(_SPIN_TOOLTIP)
        ctrl_row.addWidget(self._iter_spin)
        ctrl_row.addStretch()

        self._run_btn = QPushButton("Run iterations")
        self._run_btn.setIcon(phi("play", color=COLOR_SOLID_BUTTON_FG, size=14))
        self._run_btn.setIconSize(QSize(14, 14))
        self._run_btn.setObjectName("smallPrimaryButton")
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setToolTip(_RUN_ENABLED_TIP)
        self._run_btn.clicked.connect(self._emit_run_requested)
        ctrl_row.addWidget(self._run_btn)
        col.addLayout(ctrl_row)
        return page

    def _open_help_dialog(self) -> None:
        """Show the worked-example walkthrough in a modal dialog."""
        IterationsHelpDialog(self).exec()

    def _show_empty_state(self) -> None:
        """Show the onboarding row and hide the loaded controls."""
        self._loaded_state.hide()
        self._empty_state.show()

    def _show_loaded_state(self) -> None:
        """Show the loaded controls and refresh the file status row."""
        n = len(self._iteration_data)
        row_word = "row" if n == 1 else "rows"
        self._loaded_label.setText(
            f"<span style='color: {COLOR_SUCCESS};'>●</span> "
            f"<b>{self._loaded_file_name}</b> &nbsp;·&nbsp; "
            f"<span style='color: {COLOR_TEXT_MUTED};'>{n} {row_word} loaded — "
            "ready to run.</span>"
        )
        self._refresh_preview()
        self._refresh_run_button_state()
        self._empty_state.hide()
        self._loaded_state.show()

    def _refresh_run_button_state(self) -> None:
        """Sync Run button enabled state, label, and tooltip with loaded data."""
        has_rows = bool(self._iteration_data)
        self._run_btn.setEnabled(has_rows)
        if has_rows:
            n = len(self._iteration_data)
            self._run_btn.setToolTip(
                f"{_RUN_ENABLED_TIP}\n({n} row{'s' if n != 1 else ''} loaded.)"
            )
        else:
            self._run_btn.setToolTip(_RUN_DISABLED_TIP)

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
            self._iteration_data = []
            self._loaded_file_name = ""
            self._loaded_label.setTextFormat(Qt.TextFormat.PlainText)
            self._loaded_label.setText(
                f"Couldn't load {Path(path).name}: {exc}\nPick another file or check the format."
            )
            self._loaded_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
            self._preview.setRowCount(0)
            self._refresh_run_button_state()
            self._empty_state.hide()
            self._loaded_state.show()
            return

        self._iteration_data = rows
        self._loaded_file_name = Path(path).name
        count = max(1, len(rows))
        self._iter_spin.setValue(count)
        self._show_loaded_state()

    def _clear_data_file(self) -> None:
        """Drop the loaded file and return to the onboarding state."""
        self._iteration_data = []
        self._loaded_file_name = ""
        self._preview.setRowCount(0)
        self._iter_spin.setValue(1)
        self._refresh_run_button_state()
        self._show_empty_state()

    def _refresh_preview(self) -> None:
        """Show the first N rows of loaded data in the preview table."""
        rows = self._iteration_data[:_PREVIEW_ROW_LIMIT]
        if not rows:
            self._preview.setRowCount(0)
            return

        columns = list(dict.fromkeys(k for row in rows for k in row))
        self._preview.setColumnCount(len(columns))
        self._preview.setHorizontalHeaderLabels(columns)
        self._preview.setRowCount(len(rows))
        for r_idx, row in enumerate(rows):
            for c_idx, col in enumerate(columns):
                self._preview.setItem(r_idx, c_idx, QTableWidgetItem(str(row.get(col, ""))))

    def _emit_run_requested(self) -> None:
        """Emit :py:attr:`run_requested` when data is loaded."""
        if not self._iteration_data:
            return
        self.run_requested.emit(list(self._iteration_data), self._iter_spin.value())
