"""Script output panel for inline script execution results.

Displays console logs, test results, and errors from running a script
in the editor without sending an actual HTTP request.  Post-response
scripts add a **Mock response** tab (status, headers table, JSON body
editor; live vs manual on request tabs) beside Output and Problems.
"""

from __future__ import annotations

import contextlib
import html
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from services.environment_service import VariableDetail

from PySide6.QtCore import QObject, Qt, QThread, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.scripting.debug import DebugPauseInfo, DebugProtocol
from ui.sidebar.debug_panel import DebugVariablesPanel
from ui.request.request_editor.scripts.lsp_problems_tab import ScriptLspProblemsTab
from ui.request.request_editor.scripts.mock_response_tab import ScriptMockResponseTab
from ui.styling.icons import phi
from ui.styling.theme import COLOR_ACCENT, COLOR_DANGER, COLOR_SUCCESS, COLOR_WARNING
from ui.widgets.key_value_table import KeyValueTableWidget

# Matches the send-pipeline QThread wait budget in tab_manager.
_THREAD_WAIT_MS = 3000

# Console log level → colour mapping.
_LOG_COLORS: dict[str, str] = {
    "log": "",  # default text colour
    "info": COLOR_ACCENT,
    "warn": COLOR_WARNING,
    "error": COLOR_DANGER,
}


class ScriptOutputPanel(QWidget):
    """Panel displaying inline script execution results.

    Post-response panels add **Mock response**, **Output**, and **Problems**
    tabs (mock tab: status, headers table, JSON body editor); pre-request panels show Output and Problems only.
    """

    def __init__(
        self,
        *,
        script_type: str = "pre_request",
        parent: QWidget | None = None,
        host_kind: str = "request",
    ) -> None:
        """Initialise the output panel.

        *script_type*: ``"pre_request"`` or ``"test"``.  When ``"test"``, a
        **Mock response** tab holds status, headers, and body (and live vs
        manual controls on request tabs).

        *host_kind*: ``"request"`` shows the **Response source** combo (live vs
        manual).  ``"folder"`` has **no** live path and no combo, but still shows
        **Mock response** (status + headers + body) for ``pm.response`` in inline runs.
        """
        super().__init__(parent)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        self._script_type = script_type
        self._host_kind = host_kind
        self._mock_response_tab: ScriptMockResponseTab | None = None
        self._mock_headers_table: KeyValueTableWidget | None = None
        self._busy_buttons: list[QPushButton] = []
        self._worker_thread: QThread | None = None
        self._current_worker: QObject | None = None
        self._is_inline_debug = False
        self._build_ui()

    # -- UI construction -----------------------------------------------

    def _build_ui(self) -> None:
        """Build the panel layout."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(4)

        # Tab strip: Output, Problems, and (post-response only) Mock response.
        self._build_output_section(root)

        # Visible before any run so users discover Run / Ctrl+Enter.
        self._show_idle_hint()

        # Minimum height for the whole panel so the splitter allocates a
        # meaningful output band (QSplitter::setStretchFactor does not set
        # the initial handle position).
        if self._script_type == "test":
            self.setMinimumHeight(280)
        else:
            self.setMinimumHeight(240)

    def _build_output_section(self, parent_layout: QVBoxLayout) -> None:
        """Tab strip: Output, Problems, and Mock response (post-response only)."""
        tabs = QTabWidget()
        tabs.setObjectName("scriptOutputTabs")
        tabs.setCursor(Qt.CursorShape.PointingHandCursor)

        output_page = QWidget()
        output_page.setObjectName("scriptOutputSection")
        col = QVBoxLayout(output_page)
        col.setContentsMargins(0, 2, 0, 0)
        col.setSpacing(2)

        self._build_output_timing_row(col)
        self._build_results_area(col)

        tabs.addTab(output_page, "Output")

        self._problems_tab = ScriptLspProblemsTab(tabs)
        tabs.addTab(self._problems_tab, "Problems (0)")

        if self._script_type == "test":
            self._mock_response_tab = ScriptMockResponseTab(host_kind=self._host_kind, parent=tabs)
            tabs.addTab(self._mock_response_tab, "Mock response")
            self._response_source_combo = self._mock_response_tab.response_source_combo
            self._live_response_hint = self._mock_response_tab.live_response_hint
            self._manual_response_container = self._mock_response_tab.manual_response_container
            self._status_spin = self._mock_response_tab.status_spin
            self._mock_headers_table = self._mock_response_tab.headers_table
            self._response_body_edit = self._mock_response_tab.response_body_edit

        self._script_output_tabs = tabs
        self._problems_tab.problem_count_changed.connect(self._update_problems_tab_label)
        self._update_problems_tab_label(self._problems_tab.diagnostic_count())

        parent_layout.addWidget(tabs, 1)

    def _update_problems_tab_label(self, count: int) -> None:
        """Keep the Problems tab title in sync with the LSP diagnostic count."""
        tabs = getattr(self, "_script_output_tabs", None)
        if tabs is None:
            return
        idx = tabs.indexOf(self._problems_tab)
        if idx < 0:
            return
        tabs.setTabText(idx, f"Problems ({count})")

    def _build_debug_variables(self, parent_layout: QVBoxLayout) -> None:
        """Variable inspector (hidden until a debug session pauses)."""
        self._debug_variables = DebugVariablesPanel(self)
        self._debug_variables.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        self._debug_variables.hide()
        # Large stretch vs trailing addStretch(1) so almost all spare height goes
        # to the inspector (``DebugVariablesPanel`` fills with a single ``QTreeWidget``).
        parent_layout.addWidget(self._debug_variables, 100)

    def show_debug_controls(self, info: dict[str, Any]) -> None:
        """Show the debug variable list for the current pause payload.

        Step/continue/stop controls now live in the editor toolbar
        (see :class:`_ScriptsMixin`); this panel only surfaces the
        variable inspector here.
        """
        self._clear_result_rows()
        self._elapsed_label.setText("")
        self._timing_row.hide()
        pause: DebugPauseInfo = cast(DebugPauseInfo, info)
        self._debug_variables.update_pause(pause)
        self._debug_variables.setVisible(True)

    def hide_debug_controls(self) -> None:
        """Hide the debug variable list."""
        self._debug_variables.set_idle()
        self._debug_variables.hide()

    def response_source_mode(self) -> str:
        """Return selected test response source: ``live`` or ``manual``."""
        if self._mock_response_tab is None:
            return "manual"
        return self._mock_response_tab.response_source_mode()

    def set_response_source_mode(self, mode: str) -> None:
        """Set response source mode for test scripts."""
        if self._mock_response_tab is None:
            return
        self._mock_response_tab.set_response_source_mode(mode)

    def set_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Push resolved variables to mock headers/body editors (test panels only)."""
        if self._mock_response_tab is None:
            return
        self._mock_response_tab.set_variable_map(variables)

    def _build_output_timing_row(self, parent_layout: QVBoxLayout) -> None:
        """Right-aligned run timing — hidden until a run supplies elapsed ms."""
        self._timing_row = QWidget()
        row = QHBoxLayout(self._timing_row)
        row.setContentsMargins(0, 0, 0, 0)

        row.addStretch()

        self._elapsed_label = QLabel()
        self._elapsed_label.setObjectName("mutedLabel")
        row.addWidget(self._elapsed_label)

        parent_layout.addWidget(self._timing_row)
        self._timing_row.hide()

    def _build_results_area(self, parent_layout: QVBoxLayout) -> None:
        """Build the scrollable body: variable inspector, dynamic rows, stretch.

        The first layout item is always :attr:`_debug_variables` (hidden
        when no debug session is paused).  Step controls live in the
        editor toolbar, not here.  Hint text and console log rows are
        inserted at index 1+ so the variable inspector stays pinned to
        the top of the output box during a debug pause.
        """
        scroll = QScrollArea()
        scroll.setObjectName("scriptOutputScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setMinimumHeight(180)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        self._results_scroll = scroll

        container = QWidget()
        container.setObjectName("scriptOutputInner")
        self._results_layout = QVBoxLayout(container)
        self._results_layout.setContentsMargins(4, 2, 4, 2)
        self._results_layout.setSpacing(2)

        self._build_debug_variables(self._results_layout)
        # When the inspector is visible it should win almost all extra height; when
        # hidden, the trailing stretch absorbs flex so log rows still breathe.
        self._results_layout.addStretch(1)

        scroll.setWidget(container)
        parent_layout.addWidget(scroll, 1)

    def _show_idle_hint(self) -> None:
        """Show placeholder text when there is no output yet (or after clear)."""
        if self._script_type == "pre_request":
            msg = "Execute the script with the Run button or Ctrl+Enter to see output here."
        elif self._host_kind == "request":
            msg = (
                "Execute the script with the Run button or Ctrl+Enter — output and tests "
                "use the mock body from the Mock response tab (when using manual mock)."
            )
        else:
            msg = (
                "Execute the script with the Run button or Ctrl+Enter — output and tests "
                "use the mock body from the Mock response tab for pm.response."
            )
        hint = QLabel(f"<span style='font-size:12px;'>{html.escape(msg)}</span>")
        hint.setObjectName("mutedLabel")
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setWordWrap(True)
        self._insert_row(hint)

    # -- Public API ----------------------------------------------------

    if TYPE_CHECKING:
        from services.scripting import ScriptInput
        from ui.widgets.code_editor.editor_widget import CodeEditorWidget

    def bind_script_editor(self, editor: CodeEditorWidget) -> None:
        """Wire language-server diagnostics into the Problems tab for *editor*."""
        self._problems_tab.set_editor(editor)

    def run_script(
        self,
        *,
        script: str,
        language: str,
        context: ScriptInput,
        run_btn: QPushButton | None = None,
        debug_btn: QPushButton | None = None,
    ) -> None:
        """Launch a background thread to execute *script* and show results.

        Disables *run_btn* and *debug_btn* (when provided) for this panel
        while the worker is active and re-enables them on completion.
        """
        from ui.request.request_editor.scripts.script_run_worker import ScriptRunWorker

        if self._worker_thread is not None and self._worker_thread.isRunning():
            return

        self._busy_buttons = [b for b in (run_btn, debug_btn) if b is not None]
        for b in self._busy_buttons:
            b.setEnabled(False)

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

    def run_script_chain(
        self,
        *,
        chain: list[Any],
        script_type: str,
        context: ScriptInput,
        run_btn: QPushButton | None = None,
        debug_btn: QPushButton | None = None,
    ) -> None:
        """Run an inherited script chain (collection→folder→request) inline.

        Uses :class:`~services.scripting.ScriptEngine` chain execution so
        variable changes propagate between scripts in the same way they do
        during a real Send. ``script_type`` is ``"pre_request"`` or ``"test"``
        — the engine handles the order; this method just dispatches.
        """
        from ui.request.request_editor.scripts.script_run_worker import (
            ScriptChainRunWorker,
        )

        if self._worker_thread is not None and self._worker_thread.isRunning():
            return

        self._busy_buttons = [b for b in (run_btn, debug_btn) if b is not None]
        for b in self._busy_buttons:
            b.setEnabled(False)

        thread = QThread()
        worker = ScriptChainRunWorker()
        worker.set_params(chain=chain, script_type=script_type, context=context)
        worker.moveToThread(thread)

        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        thread.finished.connect(self._on_thread_finished)
        thread.started.connect(worker.run)

        self._worker_thread = thread
        self._current_worker = worker
        thread.start()

    def run_script_debug(
        self,
        *,
        script: str,
        language: str,
        context: ScriptInput,
        protocol: DebugProtocol,
        script_type: str,
        run_btn: QPushButton | None = None,
        debug_btn: QPushButton | None = None,
    ) -> None:
        """Run *script* with :class:`DebugProtocol` and show output on completion."""
        from ui.request.request_editor.scripts.script_run_worker import ScriptDebugWorker

        if self._worker_thread is not None and self._worker_thread.isRunning():
            return

        self._busy_buttons = [b for b in (run_btn, debug_btn) if b is not None]
        for b in self._busy_buttons:
            b.setEnabled(False)
        self._is_inline_debug = True

        thread = QThread()
        worker = ScriptDebugWorker()
        worker.set_params(
            script=script,
            language=language,
            context=context,
            protocol=protocol,
            script_type=script_type,
        )
        worker.moveToThread(thread)

        main = self.window()
        on_pause = getattr(main, "_on_debug_paused", None)
        if callable(on_pause):
            worker.debug_paused.connect(on_pause)

        worker.finished.connect(self._on_debug_worker_finished)
        worker.error.connect(self._on_debug_worker_error)
        thread.finished.connect(self._on_thread_finished)
        thread.started.connect(worker.run)

        self._worker_thread = thread
        self._current_worker = worker
        thread.start()

    @Slot(object, float)
    def _on_debug_worker_finished(self, output: dict, elapsed_ms: float) -> None:
        """Handle successful inline debug run."""
        self.show_results(output, elapsed_ms)
        self._end_inline_debug_if_current()
        self._stop_worker_thread()

    @Slot(str)
    def _on_debug_worker_error(self, msg: str) -> None:
        """Handle inline debug run error."""
        self.show_error(msg)
        self._end_inline_debug_if_current()
        self._stop_worker_thread()

    def _end_inline_debug_if_current(self) -> None:
        if not self._is_inline_debug:
            return
        self._is_inline_debug = False
        end = getattr(self.window(), "end_inline_script_debug", None)
        if callable(end):
            end()

    @Slot(object, float)
    def _on_worker_finished(self, output: dict, elapsed_ms: float) -> None:
        """Handle successful script execution on the main thread."""
        self.show_results(output, elapsed_ms)
        self._stop_worker_thread()

    @Slot(str)
    def _on_worker_error(self, msg: str) -> None:
        """Handle script execution error on the main thread."""
        self.show_error(msg)
        self._stop_worker_thread()

    def _stop_worker_thread(self) -> None:
        """Quit and join the worker QThread, if any."""
        thread = self._worker_thread
        if thread is None:
            return
        thread.quit()
        thread.wait(_THREAD_WAIT_MS)

    def cleanup(self) -> None:
        """Tear down any running script/debug worker before the app closes.

        Called from ``MainWindow.closeEvent`` so a worker still running
        at close does not pin the process (non-daemon timers + blocked
        subprocess reads).
        """
        worker = self._current_worker
        if worker is not None:
            protocol = getattr(worker, "_protocol", None)
            if protocol is not None:
                with contextlib.suppress(Exception):
                    protocol.stop()
        self._stop_worker_thread()

    @Slot()
    def _on_thread_finished(self) -> None:
        """Clean up worker and thread after completion."""
        if self._current_worker:
            self._current_worker.deleteLater()
            self._current_worker = None
        if self._worker_thread:
            self._worker_thread.deleteLater()
            self._worker_thread = None
        for b in self._busy_buttons:
            b.setEnabled(True)
        self._busy_buttons = []

    def show_results(
        self,
        output: dict[str, Any],
        elapsed_ms: float,
    ) -> None:
        """Populate the panel with *output* from a script run."""
        self._clear_result_rows()
        self._elapsed_label.setText(f"{elapsed_ms:.0f} ms")
        self._timing_row.show()

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
        self._timing_row.hide()

        row = QLabel(f"<span style='color:{COLOR_DANGER};'>{html.escape(message)}</span>")
        row.setWordWrap(True)
        row.setTextFormat(Qt.TextFormat.RichText)
        self._insert_row(row)
        self.setVisible(True)

    def clear_results(self) -> None:
        """Clear all result rows and restore the idle placeholder."""
        self._clear_result_rows()
        self._elapsed_label.setText("")
        self._timing_row.hide()
        self._show_idle_hint()

    def get_response_data(self) -> dict[str, Any]:
        """Return mock response data from the input fields.

        Only meaningful for ``script_type="test"`` panels.  Returns
        a dict suitable for the ``response`` field of ``ScriptInput``.
        """
        if self._script_type != "test" or self._mock_response_tab is None:
            return {
                "code": 200,
                "status": "OK",
                "headers": [],
                "body": "",
                "responseTime": 0,
                "responseSize": 0,
            }
        return self._mock_response_tab.get_response_data()

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
        """Remove dynamic rows: keep debug variables and trailing stretch."""
        layout = self._results_layout
        # [0]: debug variables. Last: stretch. [1..-2]: hint / log rows.
        # Stop at count 2 so we never remove the stretch.
        while layout.count() > 2:
            item = layout.takeAt(1)
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
