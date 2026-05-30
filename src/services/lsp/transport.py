"""JSON-RPC LSP framing over a subprocess stdin/stdout pipe."""

from __future__ import annotations

import contextlib
import itertools
import json
import logging
import subprocess
import threading
from collections import deque
from collections.abc import Callable, Mapping
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)


class LspFuture:
    """Resolves when a JSON-RPC *response* with matching ``id`` arrives."""

    def __init__(self) -> None:
        """Initialise mutex and completion state for one JSON-RPC response."""
        self._lock = threading.Lock()
        self._done = False
        self._cancelled = False
        self._result: dict[str, Any] | None = None
        self._callbacks: list[Callable[[LspFuture], None]] = []
        self._evt = threading.Event()

    def add_done_callback(self, cb: Callable[[LspFuture], None]) -> None:
        """Invoke *cb* on this future when completed (any thread)."""
        run = False
        with self._lock:
            if self._done:
                run = True
            else:
                self._callbacks.append(cb)
        if run:
            cb(self)

    def result(self, timeout_s: float | None = None) -> Any:
        """Block until the response is available. Raises on JSON-RPC *error*."""
        ok = self._evt.wait(timeout_s)
        if not ok:
            raise TimeoutError("LspFuture.result timeout")
        with self._lock:
            if self._cancelled:
                raise RuntimeError("LSP request cancelled")
            if self._result is None:
                return None
            err = self._result.get("error")
            if err is not None:
                raise RuntimeError(str(err))
            return self._result.get("result")

    def cancelled(self) -> bool:
        """Return True if :meth:`cancel` was called."""
        with self._lock:
            return self._cancelled

    def cancel(self) -> None:
        """Mark cancelled (caller should also send ``$/cancelRequest``)."""
        with self._lock:
            self._cancelled = True

    def _set_result_payload(self, payload: dict[str, Any]) -> None:
        """Called from transport when response arrives."""
        cbs: list[Callable[[LspFuture], None]] = []
        with self._lock:
            self._done = True
            self._result = payload
            cbs = self._callbacks
            self._callbacks = []
        self._evt.set()
        for cb in cbs:
            cb(self)


class _ReaderThread(QThread):
    """Reads LSP ``Content-Length`` frames from *read_fn* (binary chunks)."""

    frame_parsed = Signal(object)  # dict payload for transport
    finished_reading = Signal()

    def __init__(
        self,
        read_fn: Callable[[int], bytes],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._read_fn = read_fn
        self._running = True

    def stop(self) -> None:
        """Request thread exit."""
        self._running = False

    def run(self) -> None:
        """Parse frames until EOF or stop."""
        buf = b""
        while self._running:
            try:
                chunk = self._read_fn(65536)
            except Exception as exc:
                logger.debug("LSP reader read error: %s", exc)
                break
            if not chunk:
                break
            buf += chunk
            while True:
                sep = buf.find(b"\r\n\r\n")
                if sep < 0:
                    break
                header_blob = buf[:sep].decode("ascii", errors="replace")
                rest = buf[sep + 4 :]
                length = 0
                for line in header_blob.split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        try:
                            length = int(line.split(":", 1)[1].strip())
                        except ValueError:
                            length = -1
                if length < 0 or len(rest) < length:
                    break
                body = rest[:length]
                buf = rest[length:]
                try:
                    msg = json.loads(body.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    logger.warning("LSP malformed JSON frame skipped: %s", exc)
                    continue
                self.frame_parsed.emit(msg)


class _StderrDrainThread(QThread):
    """Drain stderr into a fixed-size ring buffer."""

    def __init__(
        self,
        stderr: Any,
        ring: deque[str],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._stderr = stderr
        self._ring = ring

    def run(self) -> None:
        with contextlib.suppress(Exception):
            for line in iter(self._stderr.readline, b""):
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                self._ring.append(text)
                while len(self._ring) > 200:
                    self._ring.popleft()


class LspTransport(QObject):
    """Spawn an LSP server and exchange JSON-RPC messages over stdio."""

    notification_received = Signal(str, dict)
    request_received = Signal(int, str, dict)
    server_exited = Signal(int)

    def __init__(
        self,
        argv: list[str],
        cwd: str,
        parent: QObject | None = None,
        *,
        _read_fn: Callable[[int], bytes] | None = None,
        _proc: subprocess.Popen[bytes] | None = None,
        _write_capture: list[bytes] | None = None,
    ) -> None:
        """Start a real subprocess unless *_read_fn* is set (tests).

        When *_read_fn* is provided, *argv* / *cwd* are ignored for spawning;
        optional *_proc* can supply a dummy process for :meth:`stop`.
        """
        super().__init__(parent)
        self._argv = argv
        self._cwd = cwd
        self._test_read_fn = _read_fn
        self._external_proc = _proc
        self._proc: subprocess.Popen[bytes] | None = None
        self._stdin_lock = threading.Lock()
        self._pending: dict[int, LspFuture] = {}
        self._ids = itertools.count(1)
        self._reader: _ReaderThread | None = None
        self._stderr_thread: _StderrDrainThread | None = None
        self._stderr_ring: deque[str] = deque(maxlen=200)
        self._running = False
        self._write_capture = _write_capture

    def start(self) -> None:
        """Launch subprocess (unless test mode) and reader thread."""
        if self._running:
            return
        if self._test_read_fn is not None:
            self._proc = self._external_proc
            read_fn = self._test_read_fn
        elif self._external_proc is not None:
            self._proc = self._external_proc
            proc = self._proc
            assert proc.stdout is not None

            def read_fn(n: int) -> bytes:
                return proc.stdout.read(n)  # type: ignore[union-attr]

            assert proc.stderr is not None
            self._stderr_thread = _StderrDrainThread(proc.stderr, self._stderr_ring, self)
            self._stderr_thread.start()
        else:
            self._proc = subprocess.Popen(
                self._argv,
                cwd=self._cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                text=False,
                close_fds=True,
            )
            proc = self._proc
            assert proc.stdout is not None

            def read_fn(n: int) -> bytes:
                return proc.stdout.read(n)  # type: ignore[union-attr]

            assert proc.stderr is not None
            self._stderr_thread = _StderrDrainThread(proc.stderr, self._stderr_ring, self)
            self._stderr_thread.start()

        self._reader = _ReaderThread(read_fn, self)
        from PySide6.QtCore import Qt as _Qt

        # ``DirectConnection`` lets futures resolve on the reader thread
        # so synchronous ``LspFuture.result()`` callers (tests, internal
        # bookkeeping) wake immediately. Callbacks that touch QObjects
        # must dispatch back to the GUI thread themselves — see
        # :class:`services.lsp.client.LspClient`.
        self._reader.frame_parsed.connect(
            self._on_frame_parsed, _Qt.ConnectionType.DirectConnection
        )
        self._reader.finished.connect(self._on_reader_finished)
        self._reader.start()
        self._running = True

    def _on_reader_finished(self) -> None:
        """Propagate exit when reader ends."""
        code = -1
        if self._proc is not None and self._proc.poll() is not None:
            code = self._proc.returncode or 0
        self.server_exited.emit(code)

    def stop(self, timeout_s: float = 2.0) -> None:
        """Terminate subprocess and join helper threads.

        The reader / stderr threads block on ``read(...)`` of the
        subprocess pipes; setting ``_running = False`` does not unblock
        them. The subprocess **must** be terminated first so its
        stdout / stderr close and the blocked reads return EOF, letting
        the threads exit before we ``wait`` on them. Otherwise the
        ``QThread`` is still running when the transport drops its
        reference, producing ``QThread: Destroyed while thread '' is
        still running`` and an abort at app shutdown.
        """
        self._running = False
        if self._reader is not None:
            self._reader.stop()
        if self._proc is not None and self._test_read_fn is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=timeout_s)
            except Exception:
                with contextlib.suppress(Exception):
                    self._proc.kill()
            self._proc = None
        if self._reader is not None:
            self._reader.wait(int(timeout_s * 1000))
            self._reader = None
        if self._stderr_thread is not None:
            self._stderr_thread.wait(int(timeout_s * 1000))
            self._stderr_thread = None

    def send_request(self, method: str, params: dict[str, Any]) -> LspFuture:
        """Send a request and return a future for the ``result`` object."""
        req_id = next(self._ids)
        fut = LspFuture()
        self._pending[req_id] = fut
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        self._write_message(msg)
        return fut

    def send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Fire-and-forget notification."""
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        self._write_message(msg)

    def cancel_request(self, future: LspFuture) -> None:
        """Cancel a pending future and emit ``$/cancelRequest``."""
        rid: int | None = None
        for k, v in list(self._pending.items()):
            if v is future:
                rid = k
                break
        if rid is None:
            future.cancel()
            return
        future.cancel()
        self._pending.pop(rid, None)
        self.send_notification("$/cancelRequest", {"id": rid})

    def is_running(self) -> bool:
        """Return True after :meth:`start` until :meth:`stop` completes."""
        return self._running

    def stderr_tail(self) -> list[str]:
        """Return the last stderr lines (for diagnostics)."""
        return list(self._stderr_ring)

    def _write_message(self, obj: Mapping[str, Any]) -> None:
        body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        data = header + body
        with self._stdin_lock:
            if self._write_capture is not None:
                self._write_capture.append(data)
                return
            if self._proc is None or self._proc.stdin is None:
                logger.warning("LSP transport: no stdin for write")
                return
            self._proc.stdin.write(data)
            self._proc.stdin.flush()

    def _on_frame_parsed(self, msg: dict[str, Any]) -> None:
        """Dispatch JSON-RPC message on the GUI thread."""
        if "method" in msg and "id" not in msg:
            method = str(msg["method"])
            params = msg.get("params")
            if not isinstance(params, dict):
                params = {}
            self.notification_received.emit(method, params)
            return
        if "method" in msg and "id" in msg:
            mid = msg["id"]
            method = str(msg["method"])
            params = msg.get("params")
            if not isinstance(params, dict):
                params = {}
            self.request_received.emit(int(mid), method, params)
            return
        if "id" in msg:
            rid = msg["id"]
            fut = self._pending.pop(rid, None)
            if fut is None:
                return
            fut._set_result_payload(msg)
            return
        logger.debug("LSP ignored frame: %s", msg)
