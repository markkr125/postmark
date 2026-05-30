"""Tests for Python sandbox debug execute (IPC stop semantics)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.scripting.debug import py_debug
from services.scripting.debug.protocol import DebugProtocol
from ui.request.request_editor.scripts.script_run_worker import build_inline_context


def test_none_ipc_when_stopped_shows_info_not_error() -> None:
    """When IPC returns nothing because stop() killed the sandbox, no (debug error) row."""
    ctx = build_inline_context(script_type="pre_request")
    protocol = DebugProtocol()
    protocol.start()
    protocol.stop()

    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdout = MagicMock()
    mock_proc.stderr = MagicMock()
    mock_proc.poll = lambda: 0
    mock_proc.wait = MagicMock()

    mock_timer = MagicMock()
    with (
        patch.object(py_debug, "_debug_ipc_loop", return_value=None),
        patch("services.scripting.debug.py_debug.subprocess.Popen", return_value=mock_proc),
        patch("services.scripting.debug.py_debug.threading.Timer", return_value=mock_timer),
    ):
        out = py_debug.debug_execute("x=1", ctx, protocol, script_type="pre_request")
    assert not any(t.get("name") == "(debug error)" for t in out["test_results"])
    assert any(
        "[Debug] Session stopped by user" in c.get("message", "")
        for c in out.get("console_logs", [])
    )
