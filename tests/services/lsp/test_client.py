"""Drive :class:`LspClient` against ``fake_server.py``."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from services.lsp.client import (
    CompletionItem,
    Diagnostic,
    Location,
    LspClient,
    SignatureInfo,
)
from services.lsp.transport import LspTransport

FAKE_SERVER = Path(__file__).parent / "fake_server.py"


def _scenario_file(tmp_path: Path, content: dict[str, Any]) -> str:
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    return str(path)


def _build_client(scenario_path: str) -> tuple[LspTransport, LspClient]:
    import sys

    transport = LspTransport(
        [sys.executable, str(FAKE_SERVER), "--scenario", scenario_path], cwd=str(Path.cwd())
    )
    client = LspClient(transport, root_uri="file:///tmp/lsp-test")
    return transport, client


def _start_client(scenario_path: str) -> tuple[LspTransport, LspClient]:
    transport, client = _build_client(scenario_path)
    client.start()
    qapp = QApplication.instance()
    if qapp is not None:
        _wait_for(lambda: client.is_ready or client._disabled, qapp, timeout_ms=5000)
    return transport, client


def _wait_for(
    predicate: Callable[[], bool], qapp: QCoreApplication, timeout_ms: int = 2000
) -> bool:
    elapsed = 0
    step = 25
    while elapsed < timeout_ms:
        qapp.processEvents()
        if predicate():
            return True
        QApplication.processEvents()
        from PySide6.QtCore import QThread

        QThread.msleep(step)
        elapsed += step
    return predicate()


@pytest.fixture
def base_init_scenario(tmp_path: Path) -> str:
    """Scenario that responds to ``initialize`` with empty capabilities."""
    return _scenario_file(
        tmp_path,
        {
            "responses": [
                {"match": {"method": "initialize"}, "result": {"capabilities": {}}},
            ],
            "notifications": [],
        },
    )


def test_initialize_emits_ready(qapp: QApplication, base_init_scenario: str) -> None:
    """Handshake completes and ``state_changed`` emits ``ready``."""
    transport, client = _build_client(base_init_scenario)
    states: list[str] = []
    client.state_changed.connect(states.append)
    client.start()
    _wait_for(lambda: "ready" in states, qapp, timeout_ms=5000)
    assert "ready" in states
    client.stop()


def test_publish_diagnostics_after_did_open(qapp: QApplication, tmp_path: Path) -> None:
    """``didOpen`` triggers fake ``publishDiagnostics`` and maps to ``Diagnostic``."""
    scenario = _scenario_file(
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
                        "uri": "file:///tmp/x.js",
                        "diagnostics": [
                            {
                                "range": {
                                    "start": {"line": 2, "character": 4},
                                    "end": {"line": 2, "character": 9},
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
    transport, client = _start_client(scenario)
    received: list[tuple[str, list[Diagnostic]]] = []
    client.diagnostics_published.connect(lambda u, d: received.append((u, d)))
    client.did_open("file:///tmp/x.js", "javascript", 1, "function f() {}\n")
    _wait_for(lambda: len(received) > 0, qapp)
    assert received, "no diagnostics"
    uri, diags = received[0]
    assert uri == "file:///tmp/x.js"
    assert len(diags) == 1
    d = diags[0]
    assert d.line == 2 and d.column == 4
    assert d.severity == "error"
    assert d.message == "boom"
    client.stop()


def test_completion_returns_items(qapp: QApplication, tmp_path: Path) -> None:
    """``textDocument/completion`` returns parsed ``CompletionItem`` rows."""
    scenario = _scenario_file(
        tmp_path,
        {
            "responses": [
                {"match": {"method": "initialize"}, "result": {"capabilities": {}}},
                {
                    "match": {"method": "textDocument/completion"},
                    "result": {
                        "isIncomplete": False,
                        "items": [
                            {"label": "test", "kind": 3, "detail": "(name, fn)"},
                            {"label": "expect", "kind": 3},
                        ],
                    },
                },
            ],
            "notifications": [],
        },
    )
    transport, client = _start_client(scenario)
    fut = client.completion("file:///tmp/x.js", 0, 0)
    items: list[CompletionItem] = fut.result(timeout_s=2.0)
    labels = [i.label for i in items]
    assert labels == ["test", "expect"]
    client.stop()


def test_hover_returns_text(qapp: QApplication, tmp_path: Path) -> None:
    """``textDocument/hover`` returns markdown/plain contents."""
    scenario = _scenario_file(
        tmp_path,
        {
            "responses": [
                {"match": {"method": "initialize"}, "result": {"capabilities": {}}},
                {
                    "match": {"method": "textDocument/hover"},
                    "result": {"contents": {"kind": "markdown", "value": "the answer"}},
                },
            ],
            "notifications": [],
        },
    )
    transport, client = _start_client(scenario)
    text = client.hover("file:///tmp/x.js", 1, 2).result(timeout_s=2.0)
    assert text == "the answer"
    client.stop()


def test_signature_help_active_param(qapp: QApplication, tmp_path: Path) -> None:
    """Signature help preserves ``activeParameter`` index."""
    scenario = _scenario_file(
        tmp_path,
        {
            "responses": [
                {"match": {"method": "initialize"}, "result": {"capabilities": {}}},
                {
                    "match": {"method": "textDocument/signatureHelp"},
                    "result": {
                        "signatures": [
                            {
                                "label": "test(name: string, fn: () => void)",
                                "parameters": [
                                    {"label": "name: string"},
                                    {"label": "fn: () => void"},
                                ],
                            }
                        ],
                        "activeSignature": 0,
                        "activeParameter": 1,
                    },
                },
            ],
            "notifications": [],
        },
    )
    transport, client = _start_client(scenario)
    info: SignatureInfo | None = client.signature_help("file:///tmp/x.js", 0, 0).result(
        timeout_s=2.0
    )
    assert info is not None
    assert info.parameters == ["name: string", "fn: () => void"]
    assert info.active_parameter == 1
    client.stop()


def test_definition_returns_locations(qapp: QApplication, tmp_path: Path) -> None:
    """``textDocument/definition`` maps to ``Location`` list."""
    scenario = _scenario_file(
        tmp_path,
        {
            "responses": [
                {"match": {"method": "initialize"}, "result": {"capabilities": {}}},
                {
                    "match": {"method": "textDocument/definition"},
                    "result": [
                        {
                            "uri": "file:///tmp/x.js",
                            "range": {
                                "start": {"line": 5, "character": 7},
                                "end": {"line": 5, "character": 11},
                            },
                        }
                    ],
                },
            ],
            "notifications": [],
        },
    )
    transport, client = _start_client(scenario)
    locs: list[Location] = client.definition("file:///tmp/x.js", 0, 0).result(timeout_s=2.0)
    assert len(locs) == 1
    assert locs[0].line == 5 and locs[0].column == 7
    client.stop()


def test_formatting_returns_text_edit(qapp: QApplication, tmp_path: Path) -> None:
    """Document formatting merges ``TextEdit`` payloads into one string."""
    scenario = _scenario_file(
        tmp_path,
        {
            "responses": [
                {"match": {"method": "initialize"}, "result": {"capabilities": {}}},
                {
                    "match": {"method": "textDocument/formatting"},
                    "result": [
                        {
                            "range": {
                                "start": {"line": 0, "character": 0},
                                "end": {"line": 99, "character": 0},
                            },
                            "newText": "let x = 1;\n",
                        }
                    ],
                },
            ],
            "notifications": [],
        },
    )
    transport, client = _start_client(scenario)
    edits = client.formatting("file:///tmp/x.js", 2).result(timeout_s=2.0)
    assert edits is not None
    assert edits[0]["newText"] == "let x = 1;\n"
    client.stop()


def test_initialize_timeout_disables_client(qapp: QApplication, tmp_path: Path) -> None:
    """Server that never replies to initialize → client transitions to 'disabled'."""
    scenario = _scenario_file(
        tmp_path,
        {"responses": [], "notifications": []},
    )
    transport, client = _build_client(scenario)
    states: list[str] = []
    client.state_changed.connect(states.append)
    client.start()
    _wait_for(lambda: "disabled" in states, qapp, timeout_ms=7000)
    assert "disabled" in states
    client.stop()
