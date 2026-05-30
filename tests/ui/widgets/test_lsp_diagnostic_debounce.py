"""Tests for debounced LSP diagnostic clearing while typing."""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest
from PySide6.QtWidgets import QApplication

from services.lsp.client import Diagnostic
from services.lsp.js_lsp_preamble import JS_LSP_PREAMBLE_LINE_COUNT
from services.scripting.runtime_settings import RuntimeSettings
from ui.widgets.code_editor import CodeEditorWidget


def _wait_for(predicate: Callable[[], bool], qapp: QApplication, timeout_ms: int = 2000) -> bool:
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


@pytest.fixture(autouse=True)
def _enable_lsp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(RuntimeSettings, "lsp_enabled", staticmethod(lambda: True))


def test_empty_publish_diagnostics_debounced(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty ``publishDiagnostics`` must not wipe the Problems tab immediately."""
    from services.lsp.server_registry import LspRegistry, reset_registry_for_tests

    reset_registry_for_tests()
    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    editor.setPlainText("const x = 1;\n")
    editor.set_language("javascript")
    assert _wait_for(lambda: editor._lsp_adapter is not None, qapp, 20000)
    adapter = editor._lsp_adapter
    assert adapter is not None
    assert _wait_for(lambda: adapter.is_ready, qapp, 20000)
    assert adapter._client is not None
    if adapter._diagnostics_connection is not None:
        adapter._client.diagnostics_published.disconnect(adapter._diagnostics_connection)
        adapter._diagnostics_connection = None

    panel = __import__(
        "ui.request.request_editor.scripts.lsp_problems_tab",
        fromlist=["ScriptLspProblemsTab"],
    ).ScriptLspProblemsTab()
    qtbot.addWidget(panel)
    panel.set_editor(editor)

    fake = Diagnostic(
        line=JS_LSP_PREAMBLE_LINE_COUNT,
        column=0,
        end_line=JS_LSP_PREAMBLE_LINE_COUNT,
        end_column=1,
        severity="error",
        message="test error",
        source="test",
    )
    adapter._on_diagnostics(adapter._uri or "", [fake])
    assert panel.diagnostic_count() == 1

    adapter._on_diagnostics(adapter._uri or "", [])
    qapp.processEvents()
    assert panel.diagnostic_count() == 1, "stale empty publish should keep cached problems"

    assert _wait_for(lambda: panel.diagnostic_count() == 0, qapp, 5000), (
        "problems should clear after idle + deferred clear"
    )

    editor.detach_lsp()
    LspRegistry.instance().shutdown()
    reset_registry_for_tests()


def test_validate_does_not_wipe_lsp_gutter_markers(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Debounced :meth:`_validate` must not replace LSP squiggles with an empty ESM pass."""
    from ui.widgets.code_editor.gutter import SyntaxError_

    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    editor.set_language("javascript")
    editor.setPlainText("const x = ;\n")
    monkeypatch.setattr(editor, "_should_skip_script_validation", lambda: True)
    editor.apply_validation_errors([SyntaxError_(1, 7, "expected", "error")])
    assert len(editor.errors) == 1
    editor._validate()
    assert len(editor.errors) == 1, "_validate must not clear LSP-owned gutter markers"
