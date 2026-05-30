"""UI construction helpers for :class:`ScriptOutputPanel`."""

from __future__ import annotations

import html
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.request.request_editor.data_runner.panel import DataRunnerPanel
from ui.styling.theme import SCRIPT_OUTPUT_TAB_PANE_BOTTOM_PAD_PX
from ui.request.request_editor.scripts.lsp_problems_tab import ScriptLspProblemsTab
from ui.request.request_editor.scripts.mock_response_tab import ScriptMockResponseTab
from ui.request.request_editor.scripts.output_debug_bar import build_debug_variables
from ui.request.request_editor.scripts.output_iterations_tab import ScriptOutputIterationsTab


def build_ui(panel: Any) -> None:
    """Build the panel layout."""
    root = QVBoxLayout(panel)
    root.setContentsMargins(0, 4, 0, SCRIPT_OUTPUT_TAB_PANE_BOTTOM_PAD_PX)
    root.setSpacing(4)

    build_output_section(panel, root)
    show_idle_hint(panel)

    if panel._script_type == "test":
        panel.setMinimumHeight(280)
    else:
        panel.setMinimumHeight(240)


def build_output_section(panel: Any, parent_layout: QVBoxLayout) -> None:
    """Tab strip: Output, Debugger, Problems, and Mock response (post-response only)."""
    tabs = QTabWidget()
    tabs.setObjectName("scriptOutputTabs")
    tabs.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)

    output_page = QWidget()
    output_page.setObjectName("scriptOutputSection")
    col = QVBoxLayout(output_page)
    col.setContentsMargins(0, 2, 0, 0)
    col.setSpacing(2)

    build_output_timing_row(panel, col)
    build_results_area(panel, col)

    tabs.addTab(output_page, "Output")
    panel._output_tab_page = output_page

    debugger_page = QWidget()
    debugger_page.setObjectName("scriptOutputDebuggerPage")
    debugger_col = QVBoxLayout(debugger_page)
    debugger_col.setContentsMargins(0, 2, 0, 0)
    debugger_col.setSpacing(0)
    debugger_frame = QFrame()
    debugger_frame.setObjectName("scriptOutputDebuggerFrame")
    debugger_frame.setFrameShape(QFrame.Shape.NoFrame)
    frame_lay = QVBoxLayout(debugger_frame)
    frame_lay.setContentsMargins(0, 0, 0, 0)
    frame_lay.setSpacing(0)
    build_debug_variables(panel, frame_lay)
    debugger_col.addWidget(debugger_frame, 1)
    tabs.addTab(debugger_page, "Debugger")
    panel._debugger_tab_page = debugger_page

    panel._problems_tab = ScriptLspProblemsTab(tabs)
    tabs.addTab(panel._problems_tab, "Problems (0)")

    if panel._script_type == "test":
        panel._data_runner = DataRunnerPanel()
        iterations_page = QWidget()
        iterations_page.setObjectName("scriptOutputIterationsPage")
        iterations_page.setCursor(Qt.CursorShape.ArrowCursor)
        iter_col = QVBoxLayout(iterations_page)
        iter_col.setContentsMargins(0, 4, 0, 0)
        iter_col.setSpacing(6)
        iter_col.addWidget(panel._data_runner)
        panel._iterations_tab = ScriptOutputIterationsTab(iterations_page)
        iter_col.addWidget(panel._iterations_tab, 1)
        tabs.addTab(iterations_page, "Iterations")
        panel._iterations_tab_page = iterations_page
        panel._iterations_tab.iteration_selected.connect(panel._show_iteration_drilldown)
        panel._iterations_tab.rerun_failed_requested.connect(panel._rerun_failed_iterations)

        panel._mock_response_tab = ScriptMockResponseTab(host_kind=panel._host_kind, parent=tabs)
        tabs.addTab(panel._mock_response_tab, "Mock response")
        panel._response_source_combo = panel._mock_response_tab.response_source_combo
        panel._live_response_hint = panel._mock_response_tab.live_response_hint
        panel._manual_response_container = panel._mock_response_tab.manual_response_container
        panel._status_spin = panel._mock_response_tab.status_spin
        panel._mock_headers_table = panel._mock_response_tab.headers_table
        panel._response_body_edit = panel._mock_response_tab.response_body_edit

    panel._script_output_tabs = tabs
    panel._problems_tab.problem_count_changed.connect(
        lambda count: update_problems_tab_label(panel, count)
    )
    update_problems_tab_label(panel, panel._problems_tab.diagnostic_count())

    parent_layout.addWidget(tabs, 1)

    from ui.request.request_editor.scripts.script_output_tab_prefs import (
        wire_output_sub_tab_persistence,
    )

    wire_output_sub_tab_persistence(panel)


def update_problems_tab_label(panel: Any, count: int) -> None:
    """Keep the Problems tab title in sync with the LSP diagnostic count."""
    tabs = getattr(panel, "_script_output_tabs", None)
    if tabs is None:
        return
    idx = tabs.indexOf(panel._problems_tab)
    if idx < 0:
        return
    tabs.setTabText(idx, f"Problems ({count})")


def build_output_timing_row(panel: Any, parent_layout: QVBoxLayout) -> None:
    """Right-aligned run timing — hidden until a run supplies elapsed ms."""
    panel._timing_row = QWidget()
    row = QHBoxLayout(panel._timing_row)
    row.setContentsMargins(0, 0, 0, 0)

    panel._export_btn = None
    if panel._script_type == "test":
        from ui.request.request_editor.scripts.test_results_ui import build_test_export_toolbar

        panel._export_btn = build_test_export_toolbar(
            on_export_json=panel._export_results_json,
            on_export_junit=panel._export_results_junit,
            parent=panel._timing_row,
        )
        panel._export_btn.hide()  # revealed by sync_timing_row when results exist
        row.addWidget(panel._export_btn, 0, Qt.AlignmentFlag.AlignLeft)

    row.addStretch()

    panel._elapsed_label = QLabel()
    panel._elapsed_label.setObjectName("mutedLabel")
    row.addWidget(panel._elapsed_label)

    parent_layout.addWidget(panel._timing_row)
    panel._timing_row.hide()


def build_results_area(panel: Any, parent_layout: QVBoxLayout) -> None:
    """Build the scrollable body: variable inspector, dynamic rows, stretch."""
    scroll = QScrollArea()
    scroll.setObjectName("scriptOutputScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setMinimumHeight(180)
    scroll.setSizePolicy(
        QSizePolicy.Policy.Preferred,
        QSizePolicy.Policy.Expanding,
    )
    panel._results_scroll = scroll

    container = QWidget()
    container.setObjectName("scriptOutputInner")
    panel._results_layout = QVBoxLayout(container)
    panel._results_layout.setContentsMargins(4, 0, 4, 0)
    panel._results_layout.setSpacing(2)

    panel._results_layout.addStretch(1)

    scroll.setWidget(container)
    parent_layout.addWidget(scroll, 1)


def show_idle_hint(panel: Any) -> None:
    """Show placeholder text when there is no output yet (or after clear)."""
    if panel._script_type == "pre_request":
        msg = "Execute the script with the Run button or Ctrl+Enter to see output here."
    elif panel._host_kind == "request":
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
    panel._insert_row(hint)
