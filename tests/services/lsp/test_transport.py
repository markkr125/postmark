"""Tests for :mod:`services.lsp.transport`."""

from __future__ import annotations

import json
import os
from io import BytesIO
from typing import Any

from PySide6.QtWidgets import QApplication

from services.lsp.transport import LspFuture, LspTransport


def _frame(obj: dict[str, Any]) -> bytes:
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def test_message_split_across_reads(qapp: QApplication, qtbot) -> None:
    """Framing tolerates partial reads."""
    payload = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    full = _frame(payload)
    bio = BytesIO(full)

    def read_fn(n: int) -> bytes:
        return bio.read(n)

    received: list[Any] = []
    tr = LspTransport([], "/", parent=None, _read_fn=read_fn, _write_capture=[])
    tr.start()

    def on_done(fut: LspFuture) -> None:
        received.append(fut.result(timeout_s=2.0))

    fut = LspFuture()
    tr._pending[1] = fut  # type: ignore[attr-defined]
    fut.add_done_callback(on_done)
    qtbot.waitUntil(lambda: len(received) > 0, timeout=3000)
    assert received[0] == {"ok": True}
    tr.stop()


def test_content_length_zero_then_response(qapp: QApplication, qtbot) -> None:
    """Zero-byte JSON frame followed by a second frame."""
    blob = b"Content-Length: 0\r\n\r\n" + _frame({"jsonrpc": "2.0", "id": 2, "result": {}})
    bio = BytesIO(blob)

    def read_fn(n: int) -> bytes:
        return bio.read(n)

    out: list[Any] = []
    tr = LspTransport([], "/", parent=None, _read_fn=read_fn, _write_capture=[])
    tr.start()

    def on_done(f: LspFuture) -> None:
        out.append(f.result(timeout_s=2.0))

    fut = LspFuture()
    tr._pending[2] = fut  # type: ignore[attr-defined]
    fut.add_done_callback(on_done)
    qtbot.waitUntil(lambda: len(out) > 0, timeout=3000)
    assert out[0] == {}
    tr.stop()


def test_malformed_json_then_good(qapp: QApplication, qtbot) -> None:
    """Malformed frame is skipped; next frame still parses."""
    bad = b"Content-Length: 5\r\n\r\nnot{}"
    good = _frame({"jsonrpc": "2.0", "id": 7, "result": {"x": 1}})
    bio = BytesIO(bad + good)

    def read_fn(n: int) -> bytes:
        return bio.read(n)

    got: list[Any] = []
    tr = LspTransport([], "/", parent=None, _read_fn=read_fn, _write_capture=[])
    tr.start()

    def on_done(f: LspFuture) -> None:
        got.append(f.result(timeout_s=2.0))

    fut = LspFuture()
    tr._pending[7] = fut  # type: ignore[attr-defined]
    fut.add_done_callback(on_done)
    qtbot.waitUntil(lambda: len(got) > 0, timeout=3000)
    assert got[0] == {"x": 1}
    tr.stop()


def test_send_request_roundtrip(qapp: QApplication, qtbot) -> None:
    """Outgoing request gets matching JSON-RPC response."""
    r_fd, w_fd = os.pipe()

    def read_fn(n: int) -> bytes:
        return os.read(r_fd, max(n, 1))

    tr = LspTransport([], "/", parent=None, _read_fn=read_fn, _write_capture=[])
    tr.start()
    fut = tr.send_request("initialize", {})
    os.write(w_fd, _frame({"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}}))
    done: list[Any] = []

    def cb(f: LspFuture) -> None:
        done.append(f.result(2.0))

    fut.add_done_callback(cb)
    qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)
    assert done[0] == {"capabilities": {}}
    os.close(w_fd)
    os.close(r_fd)
    tr.stop()


def test_cancel_request_emits_dollar_cancel(qapp: QApplication) -> None:
    """cancel_request sends ``$/cancelRequest``."""
    writes: list[bytes] = []
    bio = BytesIO()

    def read_fn(_n: int) -> bytes:
        return bio.read()

    tr = LspTransport([], "/", parent=None, _read_fn=read_fn, _write_capture=writes)
    tr.start()
    fut = tr.send_request("textDocument/completion", {})
    tr.cancel_request(fut)
    cancel_found = any(b"$/cancelRequest" in w for w in writes)
    assert cancel_found
    tr.stop()
