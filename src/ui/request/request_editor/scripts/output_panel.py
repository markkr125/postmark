"""Script output panel for inline script execution results.

Displays console logs, test results, and errors from running a script
in the editor without sending an actual HTTP request.  Post-response
scripts add a **Mock response** tab (status, headers table, JSON body
editor; live vs manual on request tabs) beside Output, Debugger, and Problems.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.environment_service import VariableDetail
    from services.scripting import ScriptInput
    from ui.request.request_editor.scripts.lsp_problems_tab import ScriptLspProblemsTab
    from ui.sidebar.debug_call_stack_panel import CallStackPanel
    from ui.sidebar.debug_inspector_split import DebugInspectorSplit

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.scripting.debug import DebugProtocol
from ui.request.request_editor.data_runner.panel import DataRunnerPanel
from ui.request.request_editor.scripts.mock_response_tab import ScriptMockResponseTab
from ui.request.request_editor.scripts.output_iterations_tab import ScriptOutputIterationsTab
from ui.styling.theme import COLOR_DANGER
from ui.widgets.key_value_table import KeyValueTableWidget
from ui.widgets.code_editor.editor_widget import CodeEditorWidget
from ui.request.request_editor.scripts.output_console_tab import (
    add_console_row,
    inline_log_annotations_from_console_logs as inline_log_annotations_from_console_logs,
)
from ui.request.request_editor.scripts.output_test_results_tab import (
    add_test_row as _add_test_row_impl,
    add_test_summary as _add_test_summary_impl,
    apply_run_elapsed_header,
    refresh_test_rows as _refresh_test_rows_impl,
    sync_timing_row,
)
from ui.request.request_editor.scripts.output_debug_bar import (
    hide_debug_controls as _hide_debug_controls_impl,
    set_debug_protocol as _set_debug_protocol_impl,
    show_debug_controls as _show_debug_controls_impl,
)
from ui.request.request_editor.scripts.output_panel_build import (
    build_ui as _build_ui_impl,
    show_idle_hint as _show_idle_hint_impl,
)
from ui.request.request_editor.scripts.output_script_runner import (
    cleanup_runner as _cleanup_runner_impl,
    on_debug_worker_error as _on_debug_worker_error_impl,
    on_debug_worker_finished as _on_debug_worker_finished_impl,
    on_thread_finished as _on_thread_finished_impl,
    on_worker_error as _on_worker_error_impl,
    on_worker_finished as _on_worker_finished_impl,
    run_script as _run_script_impl,
    run_script_chain as _run_script_chain_impl,
    run_script_debug as _run_script_debug_impl,
    run_script_iterations as _run_script_iterations_impl,
    stop_worker_thread as _stop_worker_thread_impl,
)
from ui.request.request_editor.scripts.output_variable_section import (
    add_variable_section as _add_variable_section_impl,
)

# Trailing stretch only (debugger lives on its own tab).
_OUTPUT_DEBUG_ROW_COUNT = 0


class ScriptOutputPanel(QWidget):
    """Panel displaying inline script execution results.

    Post-response panels add **Mock response**, **Output**, **Debugger**, and **Problems**
    tabs (mock tab: status, headers table, JSON body editor); pre-request panels show
    Output, Debugger, and Problems.
    """

    rerun_test_requested = Signal(str)
    debug_step_requested = Signal(str)

    _problems_tab: ScriptLspProblemsTab
    _script_output_tabs: QTabWidget
    _output_tab_page: QWidget
    _debugger_tab_page: QWidget
    _elapsed_label: QLabel
    _timing_row: QWidget
    _results_layout: QVBoxLayout
    _results_scroll: QScrollArea
    _debug_call_stack: CallStackPanel
    _debug_inspector: DebugInspectorSplit
    _debug_controls: Any  # DebugControls — step row on Debugger tab
    _debug_variables: Any  # scopes pane alias set in build_debug_variables
    # Mock response (test panels only) — wired by output_panel_build._build_ui_impl.
    _response_body_edit: Any
    _response_source_combo: Any
    _live_response_hint: Any
    _manual_response_container: Any
    _status_spin: Any

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
        self._last_test_results: list[dict[str, Any]] = []
        self._test_row_widgets: dict[str, QWidget] = {}
        self._export_suite_name = "(inline run)"
        self._pending_test_filter: str | None = None
        self._data_runner: DataRunnerPanel | None = None
        self._iterations_tab: ScriptOutputIterationsTab | None = None
        self._iteration_run_active = False
        self._data_run_host_callback: Any | None = None
        self._bound_editor: CodeEditorWidget | None = None
        self._host_pane: QWidget | None = None
        self._restoring_output_tab = False
        self._output_tab_prefs_wired = False
        self._build_ui()

    # -- UI construction -----------------------------------------------

    def _build_ui(self) -> None:
        """Build the panel layout."""
        _build_ui_impl(self)

    @property
    def debug_controls(self) -> Any:
        """Step/continue toolbar on the Debugger tab."""
        return self._debug_controls

    def set_debug_protocol(self, protocol: DebugProtocol | None) -> None:
        """Attach the active :class:`DebugProtocol` for watch / frame selection."""
        _set_debug_protocol_impl(self, protocol)

    def show_debug_controls(self, info: dict[str, Any]) -> None:
        """Show the debug variable list for the current pause payload."""
        _show_debug_controls_impl(self, info)

    def hide_debug_controls(self) -> None:
        """Hide the debug inspector sections."""
        _hide_debug_controls_impl(self)

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

    def _show_idle_hint(self) -> None:
        """Show placeholder text when there is no output yet (or after clear)."""
        _show_idle_hint_impl(self)

    # -- Public API ----------------------------------------------------

    if TYPE_CHECKING:
        from services.scripting import ScriptInput

    @property
    def debug_scopes(self) -> Any:
        """Variables/watches tree host for this output panel."""
        return self._debug_inspector._scopes

    def bind_host_pane(self, pane: QWidget | None) -> None:
        """Attach the owning :class:`ScriptEditorPane` for run-busy overlay updates."""
        self._host_pane = pane

    def bind_script_editor(self, editor: CodeEditorWidget) -> None:
        """Wire language-server diagnostics into the Problems tab for *editor*."""
        self._bound_editor = editor
        self._problems_tab.set_editor(editor)

    def focus_output_tab(self) -> None:
        """Switch the tab strip to **Output**."""
        self._script_output_tabs.setCurrentWidget(self._output_tab_page)
        self._persist_output_sub_tab_choice()

    def focus_debugger_tab(self) -> None:
        """Switch the tab strip to **Debugger**."""
        self._script_output_tabs.setCurrentWidget(self._debugger_tab_page)
        self._persist_output_sub_tab_choice()

    def focus_problems_tab(self) -> None:
        """Switch the output stack to the Problems tab."""
        self._script_output_tabs.setCurrentWidget(self._problems_tab)
        self._persist_output_sub_tab_choice()

    def _persist_output_sub_tab_choice(self) -> None:
        """Save the active output-strip tab after programmatic focus."""
        from ui.request.request_editor.scripts.script_output_tab_prefs import (
            persist_current_output_sub_tab,
        )

        persist_current_output_sub_tab(self)

    def clear_inline_log_annotations(self) -> None:
        """Clear inline console decorations on the bound script editor."""
        if self._bound_editor is not None:
            self._bound_editor.clear_inline_log_annotations()

    def apply_inline_log_annotations(self, output: dict[str, Any]) -> None:
        """Show grouped console output on the bound editor after a run."""
        if self._bound_editor is None:
            return
        logs = output.get("console_logs", [])
        if not isinstance(logs, list):
            return
        self._bound_editor.set_inline_log_annotations(
            inline_log_annotations_from_console_logs(logs)
        )

    def bind_data_run_callback(self, callback: Any) -> None:
        """Wire :class:`DataRunnerPanel` **Run iterations** to *callback*."""
        if self._data_runner is None:
            return
        self._data_runner.run_requested.connect(callback)

    def run_script_iterations(
        self,
        *,
        script: str,
        language: str,
        context: ScriptInput,
        iteration_data: list[dict[str, Any]],
        iteration_count: int,
        run_btn: QPushButton | None = None,
        debug_btn: QPushButton | None = None,
    ) -> None:
        """Launch a background thread to run *script* once per data row."""
        _run_script_iterations_impl(
            self,
            script=script,
            language=language,
            context=context,
            iteration_data=iteration_data,
            iteration_count=iteration_count,
            run_btn=run_btn,
            debug_btn=debug_btn,
        )

    @Slot(int, object, float)
    def _on_iteration_finished(self, index: int, output: dict, elapsed_ms: float) -> None:
        """Stream one iteration result into the matrix tab."""
        if self._iterations_tab is not None:
            self._iterations_tab.update_iteration(index, output)

    @Slot(object, float)
    def _on_iterations_worker_finished(self, _outputs: object, _elapsed_ms: float) -> None:
        """Handle completion of a multi-iteration inline run."""
        self._iteration_run_active = False
        _stop_worker_thread_impl(self)

    def _show_iteration_drilldown(self, index: int) -> None:
        """Switch to Output and show the full result for one iteration."""
        if self._iterations_tab is None:
            return
        output = self._iterations_tab.iteration_result(index)
        if output is None:
            return
        self.focus_output_tab()
        self.show_results(output, 0.0)

    def _rerun_failed_iterations(self, filtered_rows: list[dict[str, Any]]) -> None:
        """Re-run only the failed data rows (handled by the host callback)."""
        if self._data_run_host_callback is not None:
            self._data_run_host_callback(filtered_rows, len(filtered_rows))

    def set_data_rerun_callback(self, callback: Any) -> None:
        """Set ``(iteration_data, count) -> None`` for re-run failed only."""
        self._data_run_host_callback = callback

    def run_script(
        self,
        *,
        script: str,
        language: str,
        context: ScriptInput,
        run_btn: QPushButton | None = None,
        debug_btn: QPushButton | None = None,
        test_name_filter: str | None = None,
    ) -> None:
        """Launch a background thread to execute *script* and show results."""
        _run_script_impl(
            self,
            script=script,
            language=language,
            context=context,
            run_btn=run_btn,
            debug_btn=debug_btn,
            test_name_filter=test_name_filter,
        )

    def run_script_chain(
        self,
        *,
        chain: list[Any],
        script_type: str,
        context: ScriptInput,
        run_btn: QPushButton | None = None,
        debug_btn: QPushButton | None = None,
    ) -> None:
        """Run an inherited script chain inline."""
        _run_script_chain_impl(
            self,
            chain=chain,
            script_type=script_type,
            context=context,
            run_btn=run_btn,
            debug_btn=debug_btn,
        )

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
        _run_script_debug_impl(
            self,
            script=script,
            language=language,
            context=context,
            protocol=protocol,
            script_type=script_type,
            run_btn=run_btn,
            debug_btn=debug_btn,
        )

    @Slot(object, float)
    def _on_debug_worker_finished(self, output: dict, elapsed_ms: float) -> None:
        """Handle successful inline debug run."""
        _on_debug_worker_finished_impl(self, output, elapsed_ms)

    @Slot(str)
    def _on_debug_worker_error(self, msg: str) -> None:
        """Handle inline debug run error."""
        _on_debug_worker_error_impl(self, msg)

    @Slot(object, float)
    def _on_worker_finished(self, output: dict, elapsed_ms: float) -> None:
        """Handle successful script execution on the main thread."""
        _on_worker_finished_impl(self, output, elapsed_ms)

    @Slot(str)
    def _on_worker_error(self, msg: str) -> None:
        """Handle script execution error on the main thread."""
        _on_worker_error_impl(self, msg)

    def cleanup(self) -> None:
        """Tear down any running script/debug worker before the app closes."""
        _cleanup_runner_impl(self)

    @Slot()
    def _on_thread_finished(self) -> None:
        """Clean up worker and thread after completion."""
        _on_thread_finished_impl(self)

    def show_results(
        self,
        output: dict[str, Any],
        elapsed_ms: float,
        *,
        focus_output: bool = True,
    ) -> None:
        """Populate the panel with *output* from a script run."""
        from ui.request.request_editor.scripts.script_output_tab_prefs import (
            output_has_visible_content,
        )

        test_results: list[dict[str, Any]] = output.get("test_results", [])
        filt = self._pending_test_filter
        self._pending_test_filter = None
        if filt and self._last_test_results:
            merged = list(self._last_test_results)
            new_by_name = {str(r.get("name", "")): r for r in test_results}
            merged = [new_by_name.get(str(r.get("name", "")), r) for r in merged]
            known = {str(r.get("name", "")) for r in merged}
            for r in test_results:
                if str(r.get("name", "")) not in known:
                    merged.append(r)
            _refresh_test_rows_impl(self, merged, elapsed_ms=elapsed_ms)
            return

        if focus_output and output_has_visible_content(output):
            self.focus_output_tab()
        self._clear_result_rows()
        apply_run_elapsed_header(self, elapsed_ms, test_results)

        logs = output.get("console_logs", [])
        for log in logs:
            self._add_console_row(log)

        self._last_test_results = list(test_results)
        sync_timing_row(self)  # reveal/hide Export now that results are stored
        self._test_row_widgets.clear()
        for result in test_results:
            self._add_test_row(result)

        if test_results:
            self._add_test_summary(test_results)

        var_changes: dict[str, str] = output.get("variable_changes", {})
        if var_changes:
            self._add_variable_section(var_changes)

        if not logs and not test_results and not var_changes:
            note = QLabel("<span style='font-size:12px;'>Script executed with no output.</span>")
            note.setObjectName("mutedLabel")
            note.setTextFormat(Qt.TextFormat.RichText)
            self._insert_row(note)

        self.apply_inline_log_annotations(output)
        self.setVisible(True)

    def _no_results_to_export_msg(self) -> None:
        """Tell the user why Export has nothing to do, instead of failing silently."""
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(
            self,
            "Nothing to export",
            "There are no test results from the last run.\n\n"
            "Add pm.test(name, fn) calls to the script and run it — "
            "their pass/fail outcome is what Export saves.",
        )

    def _export_results_json(self) -> None:
        """Save last test results as JSON."""
        from PySide6.QtWidgets import QFileDialog

        from ui.request.request_editor.scripts.test_export import export_test_results_json

        if not self._last_test_results:
            self._no_results_to_export_msg()
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export test results",
            f"{self._export_suite_name}.json",
            "JSON (*.json)",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(export_test_results_json(self._last_test_results))

    def _export_results_junit(self) -> None:
        """Save last test results as JUnit XML."""
        from PySide6.QtWidgets import QFileDialog

        from ui.request.request_editor.scripts.test_export import export_test_results_junit

        if not self._last_test_results:
            self._no_results_to_export_msg()
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export test results",
            f"{self._export_suite_name}.xml",
            "JUnit XML (*.xml)",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                export_test_results_junit(
                    self._last_test_results,
                    suite_name=self._export_suite_name,
                )
            )

    def show_error(self, message: str, *, focus_output: bool = True) -> None:
        """Display a single error message."""
        from services.scripting.es_module_rules import strip_ansi

        if focus_output and message.strip():
            self.focus_output_tab()
        self._clear_result_rows()
        self._elapsed_label.setText("")
        self._last_test_results = []
        sync_timing_row(self)

        clean = strip_ansi(message)
        row = QLabel(f"<span style='color:{COLOR_DANGER};'>{html.escape(clean)}</span>")
        row.setWordWrap(True)
        row.setTextFormat(Qt.TextFormat.RichText)
        self._insert_row(row)
        self.setVisible(True)

    def clear_results(self) -> None:
        """Clear all result rows and restore the idle placeholder."""
        self._clear_result_rows()
        self._elapsed_label.setText("")
        self._last_test_results = []
        sync_timing_row(self)
        if self._iterations_tab is not None:
            self._iterations_tab.clear()
        _show_idle_hint_impl(self)

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
        """Remove dynamic result rows; keep debug inspector widgets and stretch."""
        layout = self._results_layout
        while layout.count() > _OUTPUT_DEBUG_ROW_COUNT + 1:
            item = layout.takeAt(_OUTPUT_DEBUG_ROW_COUNT)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

    def _add_console_row(self, log: dict[str, Any]) -> None:
        """Add a single console-log row."""
        add_console_row(self, log)

    def _add_test_row(self, result: dict[str, Any]) -> None:
        """Add a single test-result row."""
        _add_test_row_impl(self, result)

    def _on_rerun_test_clicked(self, test_name: str) -> None:
        """Emit so the script pane can rerun one ``pm.test`` by name."""
        self.rerun_test_requested.emit(test_name)

    def _add_test_summary(self, results: list[dict[str, Any]]) -> None:
        """Add a summary line for test results."""
        _add_test_summary_impl(self, results)

    def _add_variable_section(self, changes: dict[str, str]) -> None:
        """Add a section showing variable changes from the script."""
        _add_variable_section_impl(self, changes)
