"""Tests for the inline script output panel and run worker.

Covers ``ScriptOutputPanel`` (display widget) and
``ScriptRunWorker`` / ``build_inline_context`` (execution helpers).
"""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from PySide6.QtCore import QThread
from shiboken6 import Shiboken
from PySide6.QtWidgets import (
    QLabel,
    QLayout,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
)

from ui.widgets.code_editor import CodeEditorWidget
from ui.request.request_editor.scripts.output_panel import (
    ScriptOutputPanel,
    inline_log_annotations_from_console_logs,
)
from ui.widgets.debug_value_tree import debug_tree_cell_text
from services.scripting.debug import DebugProtocol
from ui.request.request_editor.scripts.script_run_worker import (
    ScriptDebugWorker,
    ScriptRunWorker,
    build_inline_context,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _walk_tree_items(item: QTreeWidgetItem) -> list[str]:
    """Collect column texts from *item* and descendants (depth-first)."""
    out = [debug_tree_cell_text(item, 0), debug_tree_cell_text(item, 1)]
    for i in range(item.childCount()):
        ch = item.child(i)
        if ch is not None:
            out.extend(_walk_tree_items(ch))
    return out


def _debug_variables_tree_text_join(tree: QTreeWidget) -> str:
    """All name/value strings from the unified debug variables tree."""
    parts: list[str] = []
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        if top is not None:
            parts.extend(_walk_tree_items(top))
    return " ".join(parts)


def _qlabel_texts_in_layout(layout: QLayout) -> list[str]:
    out: list[str] = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is None:
            continue
        w = item.widget()
        if w is not None and isinstance(w, QLabel):
            out.append(w.text())
        else:
            sub = item.layout()
            if sub is not None:
                out.extend(_qlabel_texts_in_layout(sub))
    return out


def _make_output(
    *,
    console_logs: list[dict[str, Any]] | None = None,
    test_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal ``ScriptOutput``-shaped dict."""
    return {
        "console_logs": console_logs or [],
        "test_results": test_results or [],
        "variable_changes": {},
        "request_mutations": None,
    }


# ===================================================================
# build_inline_context tests
# ===================================================================


class TestBuildInlineContext:
    """Tests for ``build_inline_context``."""

    def test_pre_request_has_none_response(self) -> None:
        """Pre-request context sets ``response`` to ``None``."""
        ctx = build_inline_context(script_type="pre_request")
        assert ctx["response"] is None
        assert ctx["request"]["method"] == "GET"

    def test_test_uses_response_data(self) -> None:
        """Test context includes supplied response data."""
        resp = {
            "code": 201,
            "status": "201",
            "headers": [],
            "body": '{"ok":true}',
            "responseTime": 0,
            "responseSize": 10,
        }
        ctx = build_inline_context(script_type="test", response_data=resp)
        assert ctx["response"] is not None
        assert ctx["response"]["code"] == 201

    def test_test_default_response(self) -> None:
        """Test context builds a default 200 response when none supplied."""
        ctx = build_inline_context(script_type="test")
        assert ctx["response"] is not None
        assert ctx["response"]["code"] == 200

    def test_environment_vars_injected(self) -> None:
        """Environment variables are passed through."""
        ctx = build_inline_context(
            script_type="pre_request",
            environment_vars={"TOKEN": "abc123"},
        )
        assert ctx["environment_vars"]["TOKEN"] == "abc123"

    def test_collection_vars_injected(self) -> None:
        """Collection variables are passed through."""
        ctx = build_inline_context(
            script_type="pre_request",
            collection_vars={"base_url": "https://api.dev"},
        )
        assert ctx["collection_vars"]["base_url"] == "https://api.dev"


# ===================================================================
# ScriptRunWorker tests
# ===================================================================


class TestScriptRunWorker:
    """Tests for ``ScriptRunWorker``."""

    def test_emits_error_without_context(self, qtbot) -> None:
        """Worker emits error when no context is configured."""
        worker = ScriptRunWorker()

        errors: list[str] = []
        worker.error.connect(errors.append)
        worker.run()
        assert len(errors) == 1
        assert "context" in errors[0].lower()

    def test_empty_script_returns_empty_output(self, qtbot) -> None:
        """Worker returns empty output for blank scripts."""
        worker = ScriptRunWorker()

        results: list[tuple[dict, float]] = []
        worker.finished.connect(lambda out, ms: results.append((out, ms)))

        ctx = build_inline_context(script_type="pre_request")
        worker.set_params(script="   ", language="javascript", context=ctx)
        worker.run()

        assert len(results) == 1
        assert results[0][0]["console_logs"] == []


# ===================================================================
# ScriptDebugWorker tests
# ===================================================================


class TestScriptDebugWorker:
    """Tests for :class:`ScriptDebugWorker` (``protocol.start`` + ``run_debug_chain``)."""

    def test_emits_error_without_protocol(self, qtbot) -> None:
        """Worker emits error when protocol is not configured."""
        worker = ScriptDebugWorker()
        errors: list[str] = []
        worker.error.connect(errors.append)
        worker.run()
        assert len(errors) == 1
        assert "not configured" in errors[0].lower()

    def test_non_empty_script_runs_to_completion(self, qtbot) -> None:
        """Non-empty script completes without error (``protocol.start`` is used)."""
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            pytest.skip("Deno required for JavaScript step-through")
        worker = ScriptDebugWorker()
        errors: list[str] = []
        finished: list[tuple[dict, float]] = []
        worker.error.connect(errors.append)
        worker.finished.connect(lambda o, ms: finished.append((o, ms)))

        ctx = build_inline_context(script_type="pre_request")
        protocol = DebugProtocol()
        protocol.set_breakpoints({})
        worker.set_params(
            script="console.log('debug worker ok')",
            language="javascript",
            context=ctx,
            protocol=protocol,
            script_type="pre_request",
        )
        worker.run()
        assert not errors
        assert len(finished) == 1
        out, _elapsed = finished[0]
        logs = " ".join(log.get("message", "") for log in out.get("console_logs", []))
        assert "debug worker ok" in logs


# ===================================================================
# ScriptOutputPanel — construction tests
# ===================================================================


class TestScriptOutputPanelConstruction:
    """Tests for panel creation and initial visibility."""

    def test_pre_request_panel_created(self, qtbot) -> None:
        """Pre-request panel is created without response input fields."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        assert not hasattr(panel, "_response_body_edit")
        assert not hasattr(panel, "_status_spin")
        tabs = panel.findChild(QTabWidget, "scriptOutputTabs")
        assert tabs is not None
        assert tabs.count() == 3
        assert tabs.tabText(1) == "Debugger"
        # Idle hint + trailing stretch (debugger is on its own tab).
        assert panel._results_layout.count() == 2

    def test_test_panel_has_response_input(self, qtbot) -> None:
        """Test panel includes response-source selector and mock inputs."""
        panel = ScriptOutputPanel(script_type="test")
        qtbot.addWidget(panel)
        tabs = panel.findChild(QTabWidget, "scriptOutputTabs")
        assert tabs is not None
        assert tabs.count() == 5
        assert tabs.tabText(0) == "Output"
        assert tabs.tabText(1) == "Debugger"
        assert tabs.tabText(2).startswith("Problems")
        assert tabs.tabText(3) == "Iterations"
        assert tabs.tabText(4) == "Mock response"
        assert isinstance(panel._response_body_edit, CodeEditorWidget)
        assert hasattr(panel, "_status_spin")
        assert hasattr(panel, "_response_source_combo")
        assert panel.response_source_mode() == "live"
        assert panel._live_response_hint is not None
        assert not panel._live_response_hint.isHidden()
        assert panel._manual_response_container is not None
        assert panel._manual_response_container.isHidden()
        assert panel._status_spin.value() == 200

    def test_folder_host_omits_response_source_row(self, qtbot) -> None:
        """Collection/folder: no live path, but mock status + body remain."""
        panel = ScriptOutputPanel(script_type="test", host_kind="folder")
        qtbot.addWidget(panel)
        assert panel._response_source_combo is None
        assert panel._live_response_hint is None
        assert panel._manual_response_container is not None
        data = panel.get_response_data()
        assert data["code"] == 200
        assert data["body"] == "{}"
        panel._status_spin.setValue(201)
        panel._response_body_edit.setPlainText('{"id": 1}')
        data2 = panel.get_response_data()
        assert data2["code"] == 201
        assert data2["body"] == '{"id": 1}'

    def test_panel_starts_hidden_after_clear(self, qtbot) -> None:
        """Clear restores the panel to a clean state."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show_results(_make_output(), 42.0)
        assert panel.isVisible()
        panel.clear_results()
        # Elapsed label cleared; idle hint restored.
        assert panel._elapsed_label.text() == ""
        assert panel._results_layout.count() == 2

    def test_show_results_preserves_debug_inspector_widgets(self, qtbot) -> None:
        """Clearing result rows must not delete the debugger tab inspector."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show_results(_make_output(), 1.0)
        assert Shiboken.isValid(panel._debug_inspector)
        assert Shiboken.isValid(panel._debug_inspector.scopes_tree)
        panel.hide_debug_controls()


class TestInlineLogAnnotations:
    """Grouping console logs for editor inline decorations."""

    def test_groups_by_source_line(self) -> None:
        logs = [
            {"level": "log", "message": "a", "timestamp": 0.0, "source_line": 1},
            {"level": "log", "message": "b", "timestamp": 0.1, "source_line": 1},
            {"level": "log", "message": "solo", "timestamp": 0.2, "source_line": 3},
        ]
        assert inline_log_annotations_from_console_logs(logs) == {
            1: "a · b",
            3: "solo",
        }

    def test_skips_missing_source_line(self) -> None:
        logs = [
            {"level": "log", "message": "x", "timestamp": 0.0},
            {"level": "log", "message": "y", "timestamp": 0.1, "source_line": 0},
        ]
        assert inline_log_annotations_from_console_logs(logs) == {0: "y"}

    def test_apply_after_show_results(self, qtbot) -> None:
        """``show_results`` pushes annotations onto the bound editor."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("line0\nline1\nline2")
        panel.bind_script_editor(editor)
        panel.show_results(
            _make_output(
                console_logs=[
                    {"level": "log", "message": "hi", "timestamp": 0.0, "source_line": 1},
                ]
            ),
            1.0,
        )
        assert editor._inline_log_annotations == {1: "hi"}

    def test_clear_on_run_start(self, qtbot) -> None:
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        panel.bind_script_editor(editor)
        editor.set_inline_log_annotations({0: "old"})
        panel.clear_inline_log_annotations()
        assert editor._inline_log_annotations == {}


# ===================================================================
# ScriptOutputPanel — result display tests
# ===================================================================


class TestScriptOutputPanelResults:
    """Tests for populating the output panel with results."""

    def test_show_console_logs(self, qtbot) -> None:
        """Console log messages are rendered as rows."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)

        output = _make_output(
            console_logs=[
                {"level": "log", "message": "hello", "timestamp": 0.0},
                {"level": "warn", "message": "careful", "timestamp": 0.1},
                {"level": "error", "message": "boom", "timestamp": 0.2},
            ]
        )
        panel.show_results(output, 10.5)
        # 3 log rows + stretch.
        assert panel._results_layout.count() == 4

    def test_show_test_results(self, qtbot) -> None:
        """Test results are rendered with pass/fail indication."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)

        output = _make_output(
            test_results=[
                {"name": "adds up", "passed": True, "error": None, "duration_ms": 1.0},
                {"name": "fails", "passed": False, "error": "expected 2", "duration_ms": 0.5},
            ]
        )
        panel.show_results(output, 5.0)
        # 2 test rows + 1 summary + stretch.
        assert panel._results_layout.count() == 4

    def test_elapsed_time_displayed(self, qtbot) -> None:
        """Elapsed time is shown in the header when there are no test rows."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show_results(_make_output(), 123.4)
        assert "123" in panel._elapsed_label.text()
        assert panel._timing_row.isVisible()

    def test_elapsed_header_hidden_when_test_rows_present(self, qtbot) -> None:
        """Per-test duration rows replace the duplicate header timing label."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show_results(
            _make_output(
                test_results=[
                    {
                        "name": "(runtime error)",
                        "passed": False,
                        "error": "boom",
                        "duration_ms": 2222.0,
                    }
                ]
            ),
            2222.0,
        )
        assert not panel._timing_row.isVisible()
        assert panel._elapsed_label.text() == ""

    def test_show_error_message(self, qtbot) -> None:
        """Error messages are displayed in red."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show_error("SyntaxError: unexpected token")
        assert panel._results_layout.count() == 2  # error + stretch

    def test_clear_removes_rows(self, qtbot) -> None:
        """Clearing the panel removes all result rows."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)

        panel.show_results(
            _make_output(
                console_logs=[
                    {"level": "log", "message": "x", "timestamp": 0.0},
                ]
            ),
            1.0,
        )
        assert panel._results_layout.count() > 1
        panel.clear_results()
        assert panel._results_layout.count() == 2  # hint + stretch

    def test_show_variable_changes(self, qtbot) -> None:
        """Variable changes are rendered as key=value rows."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)

        output: dict[str, Any] = {
            "console_logs": [],
            "test_results": [],
            "variable_changes": {"token": "abc123", "user": "test"},
            "request_mutations": None,
        }
        panel.show_results(output, 5.0)
        # section header + 2 variable rows + stretch.
        assert panel._results_layout.count() == 4


# ===================================================================
# ScriptOutputPanel — response input tests
# ===================================================================


class TestScriptOutputPanelResponseInput:
    """Tests for the response body/status input on test panels."""

    def test_get_response_data_returns_defaults(self, qtbot) -> None:
        """Default response data has status 200 and ``{}`` body when field is blank."""
        panel = ScriptOutputPanel(script_type="test")
        qtbot.addWidget(panel)
        data = panel.get_response_data()
        assert data["code"] == 200
        assert data["body"] == "{}"
        assert data["headers"] == {}
        assert data["responseSize"] == 2

    def test_get_response_data_reads_user_input(self, qtbot) -> None:
        """Response data reflects user-provided values."""
        panel = ScriptOutputPanel(script_type="test")
        qtbot.addWidget(panel)
        panel.set_response_source_mode("manual")
        panel._status_spin.setValue(404)
        assert panel._mock_headers_table is not None
        panel._mock_headers_table.set_data([{"key": "X-Test", "value": "alpha", "enabled": True}])
        panel._response_body_edit.setPlainText('{"error": "not found"}')
        data = panel.get_response_data()
        assert data["code"] == 404
        assert data["body"] == '{"error": "not found"}'
        assert data["headers"] == {"X-Test": "alpha"}

    def test_response_source_toggle(self, qtbot) -> None:
        """Switching response source toggles hint vs manual mock editor."""
        panel = ScriptOutputPanel(script_type="test")
        qtbot.addWidget(panel)
        assert panel.response_source_mode() == "live"
        assert panel._live_response_hint is not None
        assert not panel._live_response_hint.isHidden()
        assert panel._manual_response_container is not None
        assert panel._manual_response_container.isHidden()

        panel.set_response_source_mode("manual")
        assert panel.response_source_mode() == "manual"
        assert panel._live_response_hint is not None
        assert panel._live_response_hint.isHidden()
        assert panel._manual_response_container is not None
        assert not panel._manual_response_container.isHidden()

    def test_pre_request_panel_response_data(self, qtbot) -> None:
        """Pre-request panel returns a default response (no input fields)."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        data = panel.get_response_data()
        assert data["code"] == 200


# ===================================================================
# ScriptOutputPanel — run_script integration
# ===================================================================


class _InterruptibleHangThread(QThread):
    """Tiny worker thread the tests can end via ``requestInterruption``."""

    def run(self) -> None:
        while not self.isInterruptionRequested():
            self.msleep(20)


class TestScriptOutputPanelRunScript:
    """Tests for the ``run_script`` method that manages worker threads."""

    def test_second_run_while_busy_is_rejected(self, qtbot) -> None:
        """A second script start is ignored while a QThread is still running."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        t = _InterruptibleHangThread()
        t.start()
        qtbot.waitUntil(lambda: t.isRunning(), timeout=2000)
        panel._worker_thread = t

        ctx = build_inline_context(script_type="pre_request")
        panel.run_script(
            script="// not started",
            language="javascript",
            context=ctx,
        )
        # Guard blocked a new thread; the hung thread reference remains.
        assert panel._worker_thread is t
        t.requestInterruption()
        t.wait(2000)

    def test_run_disables_both_buttons(self, qtbot) -> None:
        """Run and debug buttons for the panel are disabled for the run and restored after."""
        from services.scripting.runtime_settings import RuntimeSettings

        if not RuntimeSettings.validate_deno(RuntimeSettings.deno_path())["available"]:
            pytest.skip("Deno is required to run JavaScript; not available in this environment.")

        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        run_b = QPushButton("Run")
        dbg_b = QPushButton("Debug")
        qtbot.addWidget(run_b)
        qtbot.addWidget(dbg_b)
        assert run_b.isEnabled() and dbg_b.isEnabled()
        ctx = build_inline_context(script_type="pre_request")
        panel.run_script(
            script="console.log('x')",
            language="javascript",
            context=ctx,
            run_btn=run_b,
            debug_btn=dbg_b,
        )
        assert not run_b.isEnabled() and not dbg_b.isEnabled()
        qtbot.waitUntil(lambda: panel._elapsed_label.text() != "", timeout=5000)
        qtbot.waitUntil(lambda: run_b.isEnabled() and dbg_b.isEnabled(), timeout=5000)

    def test_run_script_disables_and_reenables_button(self, qtbot) -> None:
        """The run button is disabled during execution and re-enabled after."""
        from services.scripting.runtime_settings import RuntimeSettings

        if not RuntimeSettings.validate_deno(RuntimeSettings.deno_path())["available"]:
            pytest.skip("Deno is required to run JavaScript; not available in this environment.")

        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        btn = QPushButton("Run")
        qtbot.addWidget(btn)

        ctx = build_inline_context(script_type="pre_request")
        panel.run_script(
            script="// empty",
            language="javascript",
            context=ctx,
            run_btn=btn,
        )
        # Worker runs on a thread; wait for results to appear.
        qtbot.waitUntil(lambda: panel._elapsed_label.text() != "", timeout=5000)
        # Button is re-enabled in _on_thread_finished (after thread.quit()),
        # which fires asynchronously after the results are displayed.
        qtbot.waitUntil(lambda: btn.isEnabled(), timeout=5000)

    def test_run_script_shows_results(self, qtbot) -> None:
        """Running a valid script populates the output panel."""
        from services.scripting.runtime_settings import RuntimeSettings

        if not RuntimeSettings.validate_deno(RuntimeSettings.deno_path())["available"]:
            pytest.skip("Deno is required to run JavaScript; not available in this environment.")

        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)

        ctx = build_inline_context(script_type="pre_request")
        panel.run_script(
            script="console.log('hello from test')",
            language="javascript",
            context=ctx,
        )
        qtbot.waitUntil(lambda: panel._elapsed_label.text() != "", timeout=5000)

        # At least the elapsed label should be populated.
        assert panel._elapsed_label.text() != ""

        # Console log must appear as a label in the results layout (may be nested).
        texts = _qlabel_texts_in_layout(panel._results_layout)
        assert any("hello from test" in t for t in texts)


class TestScriptOutputPanelDebugVariables:
    """Debug variable inspector embedded in the output panel.

    Step controls live in the editor toolbar now (see
    :class:`_ScriptsMixin`), so the panel only owns the variable view.
    """

    def test_pause_status_on_editor_status_bar(self, qapp, qtbot) -> None:
        """Pause line is shown on the script editor status bar, not the Debugger tab."""
        from ui.request.request_editor.scripts.script_editor_pane import ScriptEditorPane
        from ui.request.request_editor.scripts.script_editor_pane.options import (
            ScriptEditorPaneOptions,
        )

        pane = ScriptEditorPane(
            ScriptEditorPaneOptions(script_type="pre_request", host_kind="request"),
        )
        qtbot.addWidget(pane)
        pane.show()
        panel = pane.output_panel
        panel.bind_host_pane(pane)
        assert pane._status_debug_lbl.isHidden()
        panel.show_debug_controls(
            {
                "line": 11,
                "source_name": "inline",
                "local_vars": {},
                "script_type": "pre_request",
            }
        )
        assert pane._status_debug_lbl.isVisible()
        assert "line 12" in pane._status_debug_lbl.text()
        assert "pre_request" in pane._status_debug_lbl.text()
        assert panel.debug_controls._position_label is None
        panel.hide_debug_controls()
        assert pane._status_debug_lbl.isHidden()

    def test_debug_breakpoint_toolbar_buttons_present(self, qapp, qtbot) -> None:
        """Debugger toolbar includes view/disable/exception breakpoint actions."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show()
        panel.focus_debugger_tab()
        ctrl = panel.debug_controls
        assert ctrl._view_bp_btn.toolTip() == "View breakpoints"
        assert ctrl._disable_bp_btn.isCheckable()
        assert ctrl._exception_bp_btn.isCheckable()
        assert ctrl._exception_bp_btn.isChecked()

    def test_debug_controls_visible_disabled_until_pause(self, qapp, qtbot) -> None:
        """Debugger tab shows step controls disabled before a pause."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show()
        panel.focus_debugger_tab()
        ctrl = panel.debug_controls
        assert ctrl.isVisible()
        assert not ctrl._continue_btn.isEnabled()
        panel.show_debug_controls(
            {
                "line": 1,
                "source_name": "",
                "local_vars": {},
                "script_type": "pre_request",
            }
        )
        assert ctrl._continue_btn.isEnabled()

    def test_debugger_start_debug_button_starts_host_pane(self, qapp, qtbot) -> None:
        """**Start debug** on the Debugger tab calls :meth:`ScriptEditorPane.debug`."""
        from unittest.mock import MagicMock

        from ui.request.request_editor.scripts.script_editor_pane import ScriptEditorPane
        from ui.request.request_editor.scripts.script_editor_pane.options import (
            ScriptEditorPaneOptions,
        )

        pane = ScriptEditorPane(
            ScriptEditorPaneOptions(script_type="pre_request", host_kind="request"),
        )
        qtbot.addWidget(pane)
        pane.show()
        pane._editor.setPlainText("pm.sendRequest();")
        panel = pane.output_panel
        panel.bind_host_pane(pane)
        pane.debug = MagicMock()  # type: ignore[method-assign]
        panel.focus_debugger_tab()
        ctrl = panel.debug_controls
        assert ctrl._start_debug_btn is not None
        assert ctrl._start_debug_btn.isVisible()
        assert ctrl._start_debug_btn.isEnabled()
        ctrl._start_debug_btn.click()
        pane.debug.assert_called_once()

    def test_debugger_start_debug_hidden_while_paused(self, qapp, qtbot) -> None:
        """Start debug hides while step controls are active."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show()
        panel.focus_debugger_tab()
        ctrl = panel.debug_controls
        panel.show_debug_controls(
            {
                "line": 0,
                "source_name": "",
                "local_vars": {},
                "script_type": "pre_request",
            }
        )
        assert ctrl._start_debug_btn is not None
        assert not ctrl._start_debug_btn.isVisible()
        panel.hide_debug_controls()
        assert ctrl._start_debug_btn.isVisible()

    def test_show_debug_controls_shows_variables(self, qapp, qtbot) -> None:
        from ui.request.request_editor.scripts.script_output_tab_prefs import (
            save_output_sub_tab_slug,
        )

        save_output_sub_tab_slug("pre_request", "output")
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show()
        tabs = panel._script_output_tabs
        assert tabs.currentWidget() is panel._output_tab_page
        panel.show_debug_controls(
            {
                "line": 2,
                "source_name": "x.js",
                "local_vars": {"a": 1},
                "script_type": "pre_request",
            }
        )
        assert tabs.currentWidget() is panel._debugger_tab_page
        assert panel._debug_inspector.isVisible()

    def test_show_debug_controls_renders_variable_rows(self, qapp, qtbot) -> None:
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show_debug_controls(
            {
                "line": 0,
                "source_name": "",
                "local_vars": {"a": 1, "b": "hello"},
                "script_type": "test",
            }
        )
        texts = _debug_variables_tree_text_join(panel._debug_inspector.scopes_tree)
        assert "a" in texts
        assert "hello" in texts

    def test_hide_debug_controls_hides_variables(self, qapp, qtbot) -> None:
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        tabs = panel._script_output_tabs
        panel.show_debug_controls(
            {
                "line": 0,
                "source_name": "",
                "local_vars": {"x": 1},
                "script_type": "test",
            }
        )
        panel.hide_debug_controls()
        assert tabs.currentWidget() is panel._debugger_tab_page


class TestOutputSubTabPersistence:
    """Output vs Debugger tab choice is restored across panel instances."""

    def test_restore_saved_debugger_tab(self, qapp: QApplication, qtbot) -> None:
        from ui.request.request_editor.scripts.script_output_tab_prefs import (
            save_output_sub_tab_slug,
        )

        save_output_sub_tab_slug("pre_request", "debugger")
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        assert panel._script_output_tabs.currentWidget() is panel._debugger_tab_page

    def test_debug_stop_without_output_stays_on_debugger(self, qapp, qtbot) -> None:
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        tabs = panel._script_output_tabs
        panel.focus_debugger_tab()
        panel.show_results({}, 0.0, focus_output=False)
        panel.hide_debug_controls()
        assert tabs.currentWidget() is panel._debugger_tab_page

    def test_debug_stop_with_console_stays_on_debugger(self, qapp, qtbot) -> None:
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        tabs = panel._script_output_tabs
        panel.focus_debugger_tab()
        panel.show_results(
            {"console_logs": [{"message": "hi", "level": "log"}]},
            1.0,
            focus_output=False,
        )
        assert tabs.currentWidget() is panel._debugger_tab_page
