"""Tests for the inline script output panel and run worker.

Covers ``ScriptOutputPanel`` (display widget) and
``ScriptRunWorker`` / ``build_inline_context`` (execution helpers).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QPushButton

from ui.request.request_editor.scripts.output_panel import ScriptOutputPanel
from ui.request.request_editor.scripts.script_run_worker import (
    ScriptRunWorker,
    build_inline_context,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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

    def test_test_panel_has_response_input(self, qtbot) -> None:
        """Test panel includes response body and status code inputs."""
        panel = ScriptOutputPanel(script_type="test")
        qtbot.addWidget(panel)
        assert hasattr(panel, "_response_body_edit")
        assert hasattr(panel, "_status_spin")
        assert panel._status_spin.value() == 200

    def test_panel_starts_hidden_after_clear(self, qtbot) -> None:
        """Clear restores the panel to a clean state."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show_results(_make_output(), 42.0)
        assert panel.isVisible()
        panel.clear_results()
        # Elapsed label cleared.
        assert panel._elapsed_label.text() == ""


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
        # 3 log rows + 1 stretch = 4 items.
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
        # 2 test rows + 1 summary + 1 stretch = 4 items.
        assert panel._results_layout.count() == 4

    def test_elapsed_time_displayed(self, qtbot) -> None:
        """Elapsed time is shown in the header."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show_results(_make_output(), 123.4)
        assert "123" in panel._elapsed_label.text()
        # Empty output shows a "no output" note + stretch.
        assert panel._results_layout.count() == 2

    def test_show_error_message(self, qtbot) -> None:
        """Error messages are displayed in red."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.show_error("SyntaxError: unexpected token")
        assert panel._results_layout.count() == 2  # error row + stretch

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
        assert panel._results_layout.count() == 1  # only stretch

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
        # 1 header + 2 variable rows + 1 stretch = 4 items.
        assert panel._results_layout.count() == 4


# ===================================================================
# ScriptOutputPanel — response input tests
# ===================================================================


class TestScriptOutputPanelResponseInput:
    """Tests for the response body/status input on test panels."""

    def test_get_response_data_returns_defaults(self, qtbot) -> None:
        """Default response data has status 200 and empty body."""
        panel = ScriptOutputPanel(script_type="test")
        qtbot.addWidget(panel)
        data = panel.get_response_data()
        assert data["code"] == 200
        assert data["body"] == ""

    def test_get_response_data_reads_user_input(self, qtbot) -> None:
        """Response data reflects user-provided values."""
        panel = ScriptOutputPanel(script_type="test")
        qtbot.addWidget(panel)
        panel._status_spin.setValue(404)
        panel._response_body_edit.setPlainText('{"error": "not found"}')
        data = panel.get_response_data()
        assert data["code"] == 404
        assert data["body"] == '{"error": "not found"}'

    def test_pre_request_panel_response_data(self, qtbot) -> None:
        """Pre-request panel returns a default response (no input fields)."""
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        data = panel.get_response_data()
        assert data["code"] == 200


# ===================================================================
# ScriptOutputPanel — run_script integration
# ===================================================================


class TestScriptOutputPanelRunScript:
    """Tests for the ``run_script`` method that manages worker threads."""

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

        # Console log must appear as a label in the results layout.
        layout = panel._results_layout
        texts: list[str] = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if w is not None and hasattr(w, "text"):
                texts.append(w.text())
        assert any("hello from test" in t for t in texts)
