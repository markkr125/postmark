"""Script output panel for inline script execution results.

Displays console logs, test results, and errors from running a script
in the editor without sending an actual HTTP request.  For post-response
(test) scripts, provides response input fields so the user can supply
a response body to test against.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Qt, QThread, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.styling.icons import phi
from ui.styling.theme import COLOR_ACCENT, COLOR_DANGER, COLOR_SUCCESS, COLOR_WARNING

# Console log level → colour mapping.
_LOG_COLORS: dict[str, str] = {
    "log": "",  # default text colour
    "info": COLOR_ACCENT,
    "warn": COLOR_WARNING,
    "error": COLOR_DANGER,
}


class ScriptOutputPanel(QWidget):
    """Panel displaying inline script execution results.

    For test (post-response) scripts, also provides response input
    fields (status code + body) so the user can supply a mock response.
    """

    def __init__(
        self,
        *,
        script_type: str = "pre_request",
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the output panel.

        *script_type*: ``"pre_request"`` or ``"test"``.  When
        ``"test"``, response input fields are shown.
        """
        super().__init__(parent)
        self._script_type = script_type
        self._run_btn: QPushButton | None = None
        self._worker_thread: QThread | None = None
        self._current_worker: QObject | None = None
        self._build_ui()

    # -- UI construction -----------------------------------------------

    def _build_ui(self) -> None:
        """Build the panel layout."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(4)

        # 1. Response input section (test scripts only).
        if self._script_type == "test":
            self._build_response_input(root)

        # 2. Output header row.
        self._build_output_header(root)

        # 3. Scrollable results area.
        self._build_results_area(root)

        # Visible before any run so users discover Run / Ctrl+Enter.
        self._show_idle_hint()

        # Minimum height for the whole panel so the splitter allocates a
        # meaningful output band (QSplitter::setStretchFactor does not set
        # the initial handle position).
        if self._script_type == "test":
            self.setMinimumHeight(280)
        else:
            self.setMinimumHeight(240)

    def _build_response_input(self, parent_layout: QVBoxLayout) -> None:
        """Build the response body/status input for test scripts."""
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel("Response")
        lbl.setObjectName("mutedLabel")
        lbl.setStyleSheet("font-weight: bold;")
        header.addWidget(lbl)

        status_lbl = QLabel("Status:")
        status_lbl.setObjectName("mutedLabel")
        header.addWidget(status_lbl)

        self._status_spin = QSpinBox()
        self._status_spin.setRange(100, 599)
        self._status_spin.setValue(200)
        self._status_spin.setFixedWidth(70)
        self._status_spin.setToolTip("HTTP status code for the mock response")
        header.addWidget(self._status_spin)

        header.addStretch()
        parent_layout.addLayout(header)

        self._response_body_edit = QPlainTextEdit()
        self._response_body_edit.setPlaceholderText("Paste or type response body here\u2026")
        self._response_body_edit.setMaximumHeight(100)
        self._response_body_edit.setMinimumHeight(40)
        parent_layout.addWidget(self._response_body_edit)

    def _build_output_header(self, parent_layout: QVBoxLayout) -> None:
        """Build the output results header row."""
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel("Output")
        lbl.setObjectName("mutedLabel")
        lbl.setStyleSheet("font-weight: bold;")
        header.addWidget(lbl)

        self._elapsed_label = QLabel()
        self._elapsed_label.setObjectName("mutedLabel")
        header.addWidget(self._elapsed_label)

        header.addStretch()

        clear_btn = QPushButton()
        clear_btn.setIcon(phi("eraser"))
        clear_btn.setFixedSize(28, 28)
        clear_btn.setObjectName("iconButton")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setToolTip("Clear output")
        clear_btn.clicked.connect(self.clear_results)
        header.addWidget(clear_btn)

        parent_layout.addLayout(header)

    def _build_results_area(self, parent_layout: QVBoxLayout) -> None:
        """Build the scrollable results container."""
        scroll = QScrollArea()
        scroll.setObjectName("scriptOutputScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setMinimumHeight(180)
        self._results_scroll = scroll

        container = QWidget()
        container.setObjectName("scriptOutputInner")
        self._results_layout = QVBoxLayout(container)
        self._results_layout.setContentsMargins(4, 2, 4, 2)
        self._results_layout.setSpacing(2)
        self._results_layout.addStretch()
        scroll.setWidget(container)
        parent_layout.addWidget(scroll, 1)

    def _show_idle_hint(self) -> None:
        """Show placeholder text when there is no output yet (or after clear)."""
        msg = (
            "Execute the script with the Run button or Ctrl+Enter to see output here."
            if self._script_type == "pre_request"
            else "Execute the script with the Run button or Ctrl+Enter — output and tests "
            "appear here using the mock response above."
        )
        hint = QLabel(f"<span style='font-size:12px;'>{html.escape(msg)}</span>")
        hint.setObjectName("mutedLabel")
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setWordWrap(True)
        self._insert_row(hint)

    # -- Public API ----------------------------------------------------

    if TYPE_CHECKING:
        from services.scripting import ScriptInput

    def run_script(
        self,
        *,
        script: str,
        language: str,
        context: ScriptInput,
        run_btn: QPushButton | None = None,
    ) -> None:
        """Launch a background thread to execute *script* and show results.

        Disables *run_btn* during execution and re-enables on completion.
        """
        from ui.request.request_editor.scripts.script_run_worker import ScriptRunWorker

        self._run_btn = run_btn
        if run_btn:
            run_btn.setEnabled(False)

        thread = QThread()
        worker = ScriptRunWorker()
        worker.set_params(script=script, language=language, context=context)
        worker.moveToThread(thread)

        # Connect to @Slot methods (not closures) so Qt can resolve
        # receiver thread affinity and marshal to the main thread.
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        thread.finished.connect(self._on_thread_finished)
        thread.started.connect(worker.run)

        self._worker_thread = thread
        self._current_worker = worker
        thread.start()

    @Slot(dict, float)
    def _on_worker_finished(self, output: dict, elapsed_ms: float) -> None:
        """Handle successful script execution on the main thread."""
        self.show_results(output, elapsed_ms)
        if self._worker_thread:
            self._worker_thread.quit()

    @Slot(str)
    def _on_worker_error(self, msg: str) -> None:
        """Handle script execution error on the main thread."""
        self.show_error(msg)
        if self._worker_thread:
            self._worker_thread.quit()

    @Slot()
    def _on_thread_finished(self) -> None:
        """Clean up worker and thread after completion."""
        if self._current_worker:
            self._current_worker.deleteLater()
            self._current_worker = None
        if self._worker_thread:
            self._worker_thread.deleteLater()
            self._worker_thread = None
        if self._run_btn:
            self._run_btn.setEnabled(True)
            self._run_btn = None

    def show_results(
        self,
        output: dict[str, Any],
        elapsed_ms: float,
    ) -> None:
        """Populate the panel with *output* from a script run."""
        self._clear_result_rows()
        self._elapsed_label.setText(f"{elapsed_ms:.0f} ms")

        # 1. Console logs.
        logs = output.get("console_logs", [])
        for log in logs:
            self._add_console_row(log)

        # 2. Test results.
        test_results: list[dict[str, Any]] = output.get("test_results", [])
        for result in test_results:
            self._add_test_row(result)

        # 3. Summary line.
        if test_results:
            self._add_test_summary(test_results)

        # 4. Variable changes.
        var_changes: dict[str, str] = output.get("variable_changes", {})
        if var_changes:
            self._add_variable_section(var_changes)

        # 5. Runtime-error-only output with no logs/tests — show message.
        if not logs and not test_results and not var_changes:
            note = QLabel("<span style='font-size:12px;'>Script executed with no output.</span>")
            note.setObjectName("mutedLabel")
            note.setTextFormat(Qt.TextFormat.RichText)
            self._insert_row(note)

        self.setVisible(True)

    def show_error(self, message: str) -> None:
        """Display a single error message."""
        self._clear_result_rows()
        self._elapsed_label.setText("")

        row = QLabel(f"<span style='color:{COLOR_DANGER};'>{html.escape(message)}</span>")
        row.setWordWrap(True)
        row.setTextFormat(Qt.TextFormat.RichText)
        self._insert_row(row)
        self.setVisible(True)

    def clear_results(self) -> None:
        """Clear all result rows and restore the idle placeholder."""
        self._clear_result_rows()
        self._elapsed_label.setText("")
        self._show_idle_hint()

    def get_response_data(self) -> dict[str, Any]:
        """Return mock response data from the input fields.

        Only meaningful for ``script_type="test"`` panels.  Returns
        a dict suitable for the ``response`` field of ``ScriptInput``.
        """
        if self._script_type != "test":
            return {
                "code": 200,
                "status": "OK",
                "headers": [],
                "body": "",
                "responseTime": 0,
                "responseSize": 0,
            }
        body = self._response_body_edit.toPlainText()
        code = self._status_spin.value()
        return {
            "code": code,
            "status": f"{code}",
            "headers": [],
            "body": body,
            "responseTime": 0,
            "responseSize": len(body.encode("utf-8")),
        }

    # -- Internal helpers ----------------------------------------------

    def _insert_row(self, widget: QWidget) -> None:
        """Insert *widget* before the trailing stretch."""
        self._enable_text_selection(widget)
        idx = self._results_layout.count() - 1
        self._results_layout.insertWidget(max(idx, 0), widget)

    @staticmethod
    def _enable_text_selection(widget: QWidget) -> None:
        """Make all ``QLabel`` descendants selectable by mouse."""
        targets: list[QLabel] = []
        if isinstance(widget, QLabel):
            targets.append(widget)
        targets.extend(widget.findChildren(QLabel))
        for label in targets:
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def _clear_result_rows(self) -> None:
        """Remove all rows from the results layout (keep stretch)."""
        layout = self._results_layout
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

    def _add_console_row(self, log: dict[str, Any]) -> None:
        """Add a single console-log row."""
        level = log.get("level", "log")
        message = log.get("message", "")
        color = _LOG_COLORS.get(level, "")
        style = f"color:{color};" if color else ""

        # Prefix for warn/error.
        prefix = ""
        if level == "warn":
            prefix = "\u26a0 "
        elif level == "error":
            prefix = "\u2716 "

        label = QLabel(
            f"<span style='{style}font-size:12px;'>{prefix}{html.escape(message)}</span>"
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        self._insert_row(label)

    def _add_test_row(self, result: dict[str, Any]) -> None:
        """Add a single test-result row."""
        passed = result.get("passed", False)
        is_error = result.get("name") == "(runtime error)"
        icon_name = "warning" if is_error else ("check-circle" if passed else "x-circle")
        color = COLOR_DANGER if (is_error or not passed) else COLOR_SUCCESS

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 1, 0, 1)
        row_layout.setSpacing(6)

        icon_label = QLabel()
        icon_label.setPixmap(phi(icon_name, color=color).pixmap(14, 14))
        icon_label.setFixedSize(16, 16)
        row_layout.addWidget(icon_label)

        display = result.get("name", "unnamed")
        if is_error:
            source = result.get("source_name", "")
            display = f"Script error in \u2018{source}\u2019" if source else "Script error"
        name_label = QLabel(display)
        name_label.setStyleSheet("font-size: 12px;")
        row_layout.addWidget(name_label, 1)

        duration = result.get("duration_ms", 0.0)
        if duration > 0:
            dur_label = QLabel(f"{duration:.0f} ms")
            dur_label.setObjectName("mutedLabel")
            dur_label.setStyleSheet("font-size: 11px;")
            row_layout.addWidget(dur_label)

        error_msg = result.get("error")
        if error_msg and not passed:
            name_label.setToolTip(str(error_msg))

            err_label = QLabel(str(error_msg))
            err_label.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 11px;")
            err_label.setWordWrap(True)

            outer = QWidget()
            outer_layout = QVBoxLayout(outer)
            outer_layout.setContentsMargins(0, 0, 0, 0)
            outer_layout.setSpacing(0)
            outer_layout.addWidget(row)
            outer_layout.addWidget(err_label)
            self._insert_row(outer)
        else:
            self._insert_row(row)

    def _add_test_summary(self, results: list[dict[str, Any]]) -> None:
        """Add a summary line for test results."""
        runtime_errors = [r for r in results if r.get("name") == "(runtime error)"]
        real_tests = [r for r in results if r.get("name") != "(runtime error)"]

        if runtime_errors and not real_tests:
            text = f"<span style='color:{COLOR_DANGER};font-weight:bold;'>Script error</span>"
        else:
            passed = sum(1 for r in results if r.get("passed"))
            total = len(results)
            color = COLOR_SUCCESS if passed == total else COLOR_DANGER
            text = (
                f"<span style='color:{color};font-weight:bold;'>"
                f"{passed}/{total} tests passed</span>"
            )

        summary = QLabel(text)
        summary.setTextFormat(Qt.TextFormat.RichText)
        summary.setStyleSheet("font-size: 12px; padding-top: 4px;")
        self._insert_row(summary)

    def _add_variable_section(self, changes: dict[str, str]) -> None:
        """Add a section showing variable changes from the script."""
        header = QLabel("<span style='font-weight:bold;font-size:12px;'>Variable changes</span>")
        header.setObjectName("mutedLabel")
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setStyleSheet("padding-top: 6px;")
        self._insert_row(header)

        for key, value in changes.items():
            row = QLabel(
                f"<span style='font-size:12px;'>"
                f"<b>{html.escape(str(key))}</b> = "
                f"{html.escape(str(value))}</span>"
            )
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setWordWrap(True)
            self._insert_row(row)
