"""Editor + LSP adapter integration with the scenario-driven fake server."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtGui import QTextCharFormat
from PySide6.QtWidgets import QApplication

from services.lsp.client import LspClient
from services.lsp.transport import LspTransport
from services.scripting.runtime_settings import RuntimeSettings
from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.code_editor.gutter import (
    SyntaxError_,
    line_worst_validation_severity,
    normalize_validation_severity,
)

FAKE_SERVER = Path(__file__).parents[2] / "services" / "lsp" / "fake_server.py"


def _scenario(tmp_path: Path, content: dict) -> str:
    p = tmp_path / "scenario.json"
    p.write_text(json.dumps(content), encoding="utf-8")
    return str(p)


def _make_fake_client(scenario_path: str) -> LspClient:
    transport = LspTransport(
        [sys.executable, str(FAKE_SERVER), "--scenario", scenario_path],
        cwd=str(Path.cwd()),
    )
    client = LspClient(transport, root_uri="file:///tmp/lsp-editor-test")
    client.start()
    return client


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
    """Default-on for these tests; individual tests override to False."""
    monkeypatch.setattr(RuntimeSettings, "lsp_enabled", staticmethod(lambda: True))


def test_normalize_validation_severity_and_line_worst() -> None:
    """Unknown severities fall back to error; same line picks highest rank."""
    assert normalize_validation_severity("hint") == "hint"
    assert normalize_validation_severity("INFO") == "info"
    assert normalize_validation_severity("bogus") == "error"
    merged = line_worst_validation_severity(
        [
            SyntaxError_(1, 1, "h", "hint"),
            SyntaxError_(1, 1, "e", "error"),
        ]
    )
    assert merged[1] == "error"


def _wave_underline_colors(editor: CodeEditorWidget) -> list:
    editor._refresh_extra_selections()
    return [
        s.format.underlineColor()
        for s in editor.extraSelections()
        if s.format.underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline
    ]


def test_validation_wave_underline_colors_differ_by_severity(
    qapp: QApplication,
    qtbot,
) -> None:
    """Hint/info/error use distinct palette wave-underline colours."""
    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    editor.setPlainText("one\ntwo\nthree\n")
    editor.apply_validation_errors([SyntaxError_(1, 1, "h", "hint")])
    hint_c = _wave_underline_colors(editor)
    assert hint_c, "expected wave underline for hint"
    editor.apply_validation_errors([SyntaxError_(2, 1, "i", "info")])
    info_c = _wave_underline_colors(editor)
    assert info_c
    editor.apply_validation_errors([SyntaxError_(3, 1, "e", "error")])
    err_c = _wave_underline_colors(editor)
    assert err_c
    assert hint_c[0] != err_c[0]
    assert info_c[0] != err_c[0]
    assert hint_c[0] != info_c[0]


def test_lsp_diagnostic_renders_squiggle(
    qapp: QApplication, qtbot, tmp_path: Path, monkeypatch
) -> None:
    """LSP publishDiagnostics → editor.apply_validation_errors with mapped error."""
    scenario = _scenario(
        tmp_path,
        {
            "responses": [
                {"match": {"method": "initialize"}, "result": {"capabilities": {}}},
            ],
            "notifications": [
                {
                    "after": {"method": "textDocument/didOpen"},
                    "method": "textDocument/publishDiagnostics",
                    "params": {
                        "uri": "<replaced>",
                        "diagnostics": [
                            {
                                "range": {
                                    "start": {"line": 1, "character": 0},
                                    "end": {"line": 1, "character": 5},
                                },
                                "severity": 1,
                                "message": "boom",
                                "source": "fake",
                            }
                        ],
                    },
                }
            ],
        },
    )
    client = _make_fake_client(scenario)

    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    editor.setPlainText("function f() {}\n")

    # Patch the registry to hand back our fake client and short-circuit attach
    # to use the editor's own URI in the scenario notification.
    from services.lsp.server_registry import LspRegistry

    monkeypatch.setattr(LspRegistry, "for_language", lambda self, lang: client)

    # Patch the scenario's diagnostics URI to match whatever the adapter generates
    # by reaching into the adapter after attach.
    editor.attach_lsp("javascript")
    adapter = editor._lsp_adapter
    assert adapter is not None
    expected_uri = adapter._uri
    # Re-emit a publishDiagnostics targeted at the real URI so the editor accepts it.
    client._on_notification(
        "textDocument/publishDiagnostics",
        {
            "uri": expected_uri,
            "diagnostics": [
                {
                    "range": {
                        "start": {"line": 1, "character": 0},
                        "end": {"line": 1, "character": 5},
                    },
                    "severity": 1,
                    "message": "boom",
                    "source": "fake",
                }
            ],
        },
    )
    qapp.processEvents()
    assert any(e.message.endswith("boom") for e in editor._errors), editor._errors
    editor.detach_lsp()
    client.stop()


def test_lsp_hint_diagnostic_preserves_severity(
    qapp: QApplication, qtbot, tmp_path: Path, monkeypatch
) -> None:
    """Severity 4 (hint) maps to SyntaxError_.severity hint, not error."""
    scenario = _scenario(
        tmp_path,
        {
            "responses": [
                {"match": {"method": "initialize"}, "result": {"capabilities": {}}},
            ],
            "notifications": [],
        },
    )
    client = _make_fake_client(scenario)
    from services.lsp.server_registry import LspRegistry

    monkeypatch.setattr(LspRegistry, "for_language", lambda self, lang: client)

    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    editor.setPlainText("function f() {}\n")
    editor.attach_lsp("javascript")
    adapter = editor._lsp_adapter
    assert adapter is not None
    uri = adapter._uri
    client._on_notification(
        "textDocument/publishDiagnostics",
        {
            "uri": uri,
            "diagnostics": [
                {
                    "range": {
                        "start": {"line": 1, "character": 0},
                        "end": {"line": 1, "character": 5},
                    },
                    "severity": 4,
                    "message": "nudge",
                    "source": "fake",
                }
            ],
        },
    )
    qapp.processEvents()
    assert editor._errors and editor._errors[0].severity == "hint"
    assert "nudge" in editor._errors[0].message
    editor.detach_lsp()
    client.stop()


def test_lsp_disabled_falls_back_to_legacy_validation(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``lsp_enabled() is False`` no adapter attaches; legacy esprima/ast runs."""
    monkeypatch.setattr(RuntimeSettings, "lsp_enabled", staticmethod(lambda: False))
    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    editor.set_language("javascript")
    editor.setPlainText("const x = 1;\n")
    qapp.processEvents()
    assert editor._lsp_adapter is None


def test_detach_disconnects_document_signal(
    qapp: QApplication, qtbot, tmp_path: Path, monkeypatch
) -> None:
    """After detach the adapter does not flush further did_change traffic."""
    scenario = _scenario(
        tmp_path,
        {
            "responses": [
                {"match": {"method": "initialize"}, "result": {"capabilities": {}}},
            ],
            "notifications": [],
        },
    )
    client = _make_fake_client(scenario)
    from services.lsp.server_registry import LspRegistry

    monkeypatch.setattr(LspRegistry, "for_language", lambda self, lang: client)

    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    editor.attach_lsp("python")
    adapter = editor._lsp_adapter
    assert adapter is not None
    editor.setPlainText("x = 1\n")
    qapp.processEvents()
    editor.detach_lsp()
    assert editor._lsp_adapter is None
    # Subsequent edits do not crash even though the adapter is gone.
    editor.setPlainText("y = 2\n")
    qapp.processEvents()
    client.stop()


def test_attach_lsp_unsupported_language_no_op(qapp: QApplication, qtbot) -> None:
    """``set_language('json')`` does not attach an LSP adapter."""
    editor = CodeEditorWidget()
    qtbot.addWidget(editor)
    editor.set_language("json")
    qapp.processEvents()
    assert editor._lsp_adapter is None
