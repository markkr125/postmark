"""Tests for the inline script output panel and run worker.

Covers ``ScriptOutputPanel`` (display widget) and
``ScriptRunWorker`` / ``build_inline_context`` (execution helpers).
"""

from __future__ import annotations

from typing import Any

import pytest

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QLabel,
    QLayout,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
)

from ui.widgets.code_editor import CodeEditorWidget
from ui.request.request_editor.scripts.output_panel import ScriptOutputPanel
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
        protocol.set_breakpoints(set())
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
        assert tabs.count() == 2
        # Hidden variable inspector + idle hint + trailing stretch.
        assert panel._results_layout.count() == 3

    def test_test_panel_has_response_input(self, qtbot) -> None:
        """Test panel includes response-source selector and mock inputs."""
        panel = ScriptOutputPanel(script_type="test")
        qtbot.addWidget(panel)
        tabs = panel.findChild(QTabWidget, "scriptOutputTabs")
        assert tabs is not None
        assert tabs.count() == 3
        assert tabs.tabText(0) == "Output"
        assert tabs.tabText(1).startswith("Problems")
        assert tabs.tabText(2) == "Mock response"
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
        assert panel._results_layout.count() == 3


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
        # 1 fixed debug row + 3 log rows + stretch = 5 items.
        assert panel._results_layout.count() == 5

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
        # 1 fixed + 2 test rows + 1 summary + stretch = 5 items.
        assert panel._results_layout.count() == 5

    def test_elapsed_time_displayed(self, qtbot) -> None:
        """Elapsed time is shown next to the output tab content (right-aligned)."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show_results(_make_output(), 123.4)
        assert "123" in panel._elapsed_label.text()
        # Empty output shows a "no output" note + stretch.
        assert panel._results_layout.count() == 3

    def test_show_error_message(self, qtbot) -> None:
        """Error messages are displayed in red."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show_error("SyntaxError: unexpected token")
        assert panel._results_layout.count() == 3  # fixed 1 + error + stretch

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
        assert panel._results_layout.count() == 3  # fixed 1 + hint + stretch

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
        # 1 fixed + section header + 2 variable rows + stretch = 5 items.
        assert panel._results_layout.count() == 5


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

    def test_show_debug_controls_shows_variables(self, qapp, qtbot) -> None:
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show()
        assert not panel._debug_variables.isVisible()
        panel.show_debug_controls(
            {
                "line": 2,
                "source_name": "x.js",
                "local_vars": {"a": 1},
                "script_type": "pre_request",
            }
        )
        assert panel._debug_variables.isVisible()

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
        texts = _debug_variables_tree_text_join(panel._debug_variables._tree)
        assert "a" in texts
        assert "hello" in texts

    def test_hide_debug_controls_hides_variables(self, qapp, qtbot) -> None:
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show_debug_controls(
            {
                "line": 0,
                "source_name": "",
                "local_vars": {"x": 1},
                "script_type": "test",
            }
        )
        panel.hide_debug_controls()
        assert not panel._debug_variables.isVisible()
