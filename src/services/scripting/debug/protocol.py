"""Debug protocol — state machine and breakpoint management.

Controls the flow of a debug session: pause at breakpoints,
single-step, continue, stop.  The protocol is runtime-agnostic —
both JS and Python debug workers use it.
"""

from __future__ import annotations

import contextlib
import enum
import threading
from typing import Any, TypedDict
from collections.abc import Callable

from PySide6.QtCore import Q_ARG, QCoreApplication, QMetaObject, QObject, Qt, QThread, Signal, Slot


WATCH_VALUE_PLACEHOLDER = "\u2014"
WATCH_EVAL_ERROR_PREFIX = "<error:"
WATCH_EVAL_PLACEHOLDERS = frozenset({"<not paused>", "<unavailable>", "<error>", "<invalid frame>"})

_JS_ERROR_PREFIXES = (
    "ReferenceError:",
    "TypeError:",
    "SyntaxError:",
    "RangeError:",
    "EvalError:",
    "URIError:",
    "Error:",
)


def _first_line(text: str) -> str:
    """Return the first non-empty line of *text*."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return text.strip()


def _looks_like_js_runtime_error(line: str) -> bool:
    return any(line.startswith(prefix) for prefix in _JS_ERROR_PREFIXES)


def normalize_watch_eval_result(raw: str) -> str:
    """Map runtime/CDP evaluate strings to watch display sentinels.

    CDP often returns a multi-line ``description`` (exception + stack) that must
    not be painted in the value column.
    """
    if not raw or raw in WATCH_EVAL_PLACEHOLDERS:
        return raw
    if raw.startswith(WATCH_EVAL_ERROR_PREFIX):
        return raw
    first = _first_line(raw)
    if "\n" in raw or _looks_like_js_runtime_error(first):
        return f"{WATCH_EVAL_ERROR_PREFIX} {first}>"
    return raw


def is_watch_eval_error(raw: str) -> bool:
    """Return whether *raw* is a failed or unavailable watch evaluation result."""
    return raw in WATCH_EVAL_PLACEHOLDERS or raw.startswith(WATCH_EVAL_ERROR_PREFIX)


class StepMode(enum.Enum):
    """Step modes for the debug controller."""

    CONTINUE = "continue"
    STEP_OVER = "step_over"
    STEP_INTO = "step_into"
    STEP_OUT = "step_out"
    STOP = "stop"


class DebugState(enum.Enum):
    """Lifecycle states for a debug session."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class CallFrame(TypedDict):
    """One stack frame shown in the debug call-stack panel."""

    id: str
    name: str
    line: int
    column: int


class DebugPauseInfo(TypedDict):
    """Information emitted when the debugger pauses."""

    line: int
    source_name: str
    local_vars: dict[str, Any]
    script_type: str
    env_changes: dict[str, Any]
    global_changes: dict[str, Any]
    call_stack: list[CallFrame]
    selected_frame_index: int


EvaluateFn = Callable[[str, int], str]
EvaluateBatchFn = Callable[[list[tuple[str, int]]], list[str]]
FrameLocalsFn = Callable[[int], dict[str, Any]]


class DebugProtocol(QObject):
    """State machine that coordinates pause/resume between runtime and UI.

    Thread-safe: the debug worker calls :meth:`checkpoint` from a
    background thread, and UI calls :meth:`resume` / :meth:`stop` from
    the main thread.
    """

    evaluated = Signal(str, str)  # (expr, value)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialise the debug protocol in IDLE state."""
        super().__init__(parent)
        self._state = DebugState.IDLE
        self._breakpoints: dict[int, str | None] = {}
        self._breakpoints_enabled = True
        self._pause_on_exceptions = True
        self._pause_on_exceptions_cdp_hook: Callable[[bool], None] | None = None
        self._step_mode = StepMode.CONTINUE
        self._pause_event = threading.Event()
        self._stop_requested = False
        self._last_line = -1
        self._pause_info: DebugPauseInfo | None = None
        self._selected_frame_index = 0
        self._lock = threading.Lock()
        self._on_pause: Any = None  # callback: (DebugPauseInfo) -> None
        self._abort_cb: Callable[[], None] | None = None
        self._evaluate_cb: EvaluateFn | None = None
        self._evaluate_batch_cb: EvaluateBatchFn | None = None
        self._frame_locals_cb: FrameLocalsFn | None = None
        self._eval_cache: dict[str, str] = {}
        self._eval_inflight: set[tuple[str, int]] = set()
        self._eval_queue: list[tuple[str, int]] = []
        self._eval_worker: _EvalWorker | None = None

    # -- State queries --------------------------------------------------

    @property
    def state(self) -> DebugState:
        """Return the current debug state."""
        return self._state

    @property
    def is_stopped(self) -> bool:
        """True after :meth:`stop` was called on this session (before next :meth:`start`)."""
        with self._lock:
            return self._stop_requested

    @property
    def pause_info(self) -> DebugPauseInfo | None:
        """Return the info from the most recent pause."""
        return self._pause_info

    @property
    def selected_frame_index(self) -> int:
        """Return the call-stack frame index used for variable reads."""
        with self._lock:
            return self._selected_frame_index

    # -- Runtime adapters (evaluate / frame locals) ---------------------

    def set_evaluate_callback(self, cb: EvaluateFn | None) -> None:
        """Register a thread-safe evaluator and start the async eval worker."""
        to_join: _EvalWorker | None = None
        to_start: _EvalWorker | None = None
        with self._lock:
            self._evaluate_cb = cb
            if cb is not None and self._eval_worker is None:
                self._eval_worker = _EvalWorker(self)
                to_start = self._eval_worker
            elif cb is None:
                to_join = self._detach_eval_worker_locked()
        if to_start is not None:
            to_start.start()
        self._join_eval_worker(to_join)

    def set_evaluate_callback_sync(self, cb: EvaluateFn | None) -> None:
        """Register an evaluator without starting :class:`_EvalWorker` (tests only)."""
        with self._lock:
            self._evaluate_cb = cb

    def set_evaluate_batch_callback(self, cb: EvaluateBatchFn | None) -> None:
        """Register a batched evaluator (one IPC round-trip per drain)."""
        with self._lock:
            self._evaluate_batch_cb = cb

    def set_frame_locals_callback(self, cb: FrameLocalsFn | None) -> None:
        """Register a callback that returns ``local_vars`` for a stack frame index."""
        with self._lock:
            self._frame_locals_cb = cb

    def submit_evaluate(self, expr: str, *, frame_index: int | None = None) -> None:
        """Queue *expr* for background evaluation; never blocks."""
        with self._lock:
            if self._state != DebugState.PAUSED:
                return
            if self._evaluate_cb is None or self._eval_worker is None:
                return
            frame = self._selected_frame_index if frame_index is None else frame_index
            key = (expr, frame)
            if key in self._eval_inflight:
                return
            self._eval_queue.append(key)
            worker = self._eval_worker
        if worker is not None:
            worker.wake()

    def cached_evaluate(self, expr: str) -> str:
        """Return the last cached watch value for *expr*, or the placeholder."""
        with self._lock:
            return self._eval_cache.get(expr, WATCH_VALUE_PLACEHOLDER)

    def evaluate(self, expr: str, *, frame_index: int | None = None) -> str:
        """Return cached value and schedule a background re-eval when the worker runs.

        Prefer :meth:`submit_evaluate` / :meth:`cached_evaluate` for new code.
        When :class:`_EvalWorker` is not started, evaluates synchronously (tests).
        """
        with self._lock:
            if self._state != DebugState.PAUSED:
                return "<not paused>"
            worker = self._eval_worker
            if worker is not None:
                cached = self._eval_cache.get(expr, WATCH_VALUE_PLACEHOLDER)
            else:
                cb = self._evaluate_cb
                idx = self._selected_frame_index if frame_index is None else frame_index
        if worker is not None:
            self.submit_evaluate(expr, frame_index=frame_index)
            return cached
        if cb is None:
            return "<unavailable>"
        try:
            value = normalize_watch_eval_result(cb(expr, idx))
        except Exception as exc:
            value = f"<error: {exc}>"
        with self._lock:
            self._eval_cache[expr] = value
        return value

    def clear_eval_cache(self) -> None:
        """Drop cached watch values and in-flight eval state."""
        with self._lock:
            self._clear_eval_state_locked()

    def _clear_eval_state_locked(self) -> None:
        """Clear eval cache/queue; caller must hold ``_lock``."""
        self._eval_cache.clear()
        self._eval_inflight.clear()
        self._eval_queue.clear()

    def select_frame(self, index: int) -> DebugPauseInfo | None:
        """Select a call-stack frame and refresh ``local_vars`` when possible."""
        with self._lock:
            info = self._pause_info
            cb = self._frame_locals_cb
            self._selected_frame_index = max(0, index)
            if info is None:
                return None
            info["selected_frame_index"] = self._selected_frame_index
            stack = info.get("call_stack") or []
            if stack and 0 <= self._selected_frame_index < len(stack):
                fr = stack[self._selected_frame_index]
                info["line"] = int(fr.get("line", info["line"]))
        if cb is not None:
            try:
                fresh = cb(self._selected_frame_index)
                if isinstance(fresh, dict):
                    with self._lock:
                        if self._pause_info is not None:
                            self._pause_info["local_vars"] = fresh
                            info = self._pause_info
            except Exception:
                pass
        return info

    # -- Breakpoint management ------------------------------------------

    def set_breakpoints(self, breakpoints: dict[int, str | None]) -> None:
        """Replace breakpoints (0-based line → optional condition expression)."""
        with self._lock:
            self._breakpoints = dict(breakpoints)

    def update_breakpoints(self, breakpoints: dict[int, str | None]) -> None:
        """Replace breakpoints during an active session (same as :meth:`set_breakpoints`).

        Thread-safe. The in-process JS runtime sees the new map at the next
        :meth:`checkpoint`. The Python sandbox receives updates on each
        resume command (see the debug IPC layer).
        """
        with self._lock:
            self._breakpoints = dict(breakpoints)

    def toggle_breakpoint(self, line: int) -> bool:
        """Toggle a breakpoint on *line*. Return new state (True=set)."""
        with self._lock:
            if line in self._breakpoints:
                del self._breakpoints[line]
                return False
            self._breakpoints[line] = None
            return True

    def set_breakpoint_condition(self, line: int, condition: str | None) -> None:
        """Set or clear the condition for an existing breakpoint on *line*."""
        with self._lock:
            if line not in self._breakpoints:
                self._breakpoints[line] = condition
            else:
                self._breakpoints[line] = condition

    def breakpoint_condition(self, line: int) -> str | None:
        """Return the condition for *line*, or ``None`` when unset / no breakpoint."""
        with self._lock:
            return self._breakpoints.get(line)

    @property
    def breakpoints(self) -> dict[int, str | None]:
        """Return a copy of the current breakpoint map."""
        with self._lock:
            return dict(self._breakpoints)

    @property
    def breakpoints_enabled(self) -> bool:
        """When False, line breakpoints do not pause (step commands still work)."""
        with self._lock:
            return self._breakpoints_enabled

    def set_breakpoints_enabled(self, enabled: bool) -> None:
        """Enable or disable pausing on line breakpoints."""
        with self._lock:
            self._breakpoints_enabled = enabled

    def effective_breakpoints(self) -> dict[int, str | None]:
        """Breakpoint map sent to runtimes (empty when breakpoints are disabled)."""
        with self._lock:
            if not self._breakpoints_enabled:
                return {}
            return dict(self._breakpoints)

    @property
    def pause_on_exceptions(self) -> bool:
        """When True, uncaught JS exceptions pause the Deno debugger."""
        with self._lock:
            return self._pause_on_exceptions

    def set_pause_on_exceptions(self, enabled: bool) -> None:
        """Toggle pausing on uncaught exceptions (Deno CDP when a hook is registered)."""
        hook: Callable[[bool], None] | None
        with self._lock:
            self._pause_on_exceptions = enabled
            hook = self._pause_on_exceptions_cdp_hook
        if hook is not None:
            with contextlib.suppress(Exception):
                hook(enabled)

    def set_pause_on_exceptions_cdp_hook(self, cb: Callable[[bool], None] | None) -> None:
        """Register a callback to sync ``Debugger.setPauseOnExceptions`` mid-session."""
        with self._lock:
            self._pause_on_exceptions_cdp_hook = cb

    # -- Session lifecycle ----------------------------------------------

    def start(self, on_pause: Any = None) -> None:
        """Begin a debug session. Reset state to RUNNING."""
        with self._lock:
            self._state = DebugState.RUNNING
            self._stop_requested = False
            self._step_mode = StepMode.CONTINUE
            self._last_line = -1
            self._pause_info = None
            self._selected_frame_index = 0
            self._on_pause = on_pause
            self._pause_event.clear()
            self._breakpoints_enabled = True
            self._pause_on_exceptions = True
            self._pause_on_exceptions_cdp_hook = None
            self._evaluate_cb = None
            self._evaluate_batch_cb = None
            self._frame_locals_cb = None
            stopped_worker = self._detach_eval_worker_locked()
            self._clear_eval_state_locked()
        self._join_eval_worker(stopped_worker)

    def stop(self) -> None:
        """Request a debug session stop. Unblocks any paused checkpoint.

        Also fires an abort callback (if registered) so the worker can
        terminate a runtime that is blocked outside a checkpoint —
        e.g. a sandbox subprocess waiting for a step command, or a V8
        isolate stuck inside ``ctx.eval``.
        """
        with self._lock:
            self._stop_requested = True
            self._state = DebugState.STOPPED
            self._pause_event.set()
            cb = self._abort_cb
        if cb is not None:
            with contextlib.suppress(Exception):
                cb()

    def set_abort_callback(self, cb: Callable[[], None] | None) -> None:
        """Register a callback fired from :meth:`stop`.

        Interrupts a runtime blocked outside :meth:`checkpoint`.
        """
        with self._lock:
            self._abort_cb = cb

    def finish(self) -> None:
        """Mark the session as cleanly finished (IDLE)."""
        with self._lock:
            self._state = DebugState.IDLE
            self._on_pause = None
            self._abort_cb = None
            self._evaluate_cb = None
            self._evaluate_batch_cb = None
            self._frame_locals_cb = None
            stopped_worker = self._detach_eval_worker_locked()
            self._clear_eval_state_locked()
        self._join_eval_worker(stopped_worker)

    def _detach_eval_worker_locked(self) -> _EvalWorker | None:
        """Drop the worker reference; caller must hold ``_lock``.

        The returned worker must be joined via :meth:`_join_eval_worker` **outside**
        the lock — ``QThread.wait()`` while holding ``_lock`` deadlocks when the
        worker is in :meth:`_set_eval_result` or :meth:`_drain_eval_queue`.
        """
        worker = self._eval_worker
        self._eval_worker = None
        return worker

    def _join_eval_worker(self, worker: _EvalWorker | None) -> None:
        """Stop and join a detached eval worker without holding ``_lock``."""
        if worker is None:
            return
        worker.stop()
        worker.join(3.0)

    def _drain_eval_queue(self, limit: int = 16) -> list[tuple[str, int]]:
        """Pop up to *limit* queued evals; caller must hold ``_lock``."""
        batch: list[tuple[str, int]] = []
        while self._eval_queue and len(batch) < limit:
            item = self._eval_queue.pop(0)
            if item not in self._eval_inflight:
                self._eval_inflight.add(item)
                batch.append(item)
        return batch

    @Slot(str, str)
    def _emit_evaluated(self, expr: str, value: str) -> None:
        """Emit :attr:`evaluated` on the GUI thread (slot for queued invoke)."""
        self.evaluated.emit(expr, value)

    def _post_evaluated(self, expr: str, value: str) -> None:
        """Deliver an eval result to UI slots on the Qt main thread."""
        app = QCoreApplication.instance()
        if app is None:
            return
        if QThread.currentThread() is app.thread():
            self.evaluated.emit(expr, value)
            return
        QMetaObject.invokeMethod(  # type: ignore[call-overload]
            self,
            "_emit_evaluated",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, expr),
            Q_ARG(str, value),
        )

    def _set_eval_result(self, expr: str, frame: int, value: str) -> None:
        """Store a watch eval result and emit :attr:`evaluated` when still current."""
        value = normalize_watch_eval_result(value)
        emit = False
        with self._lock:
            self._eval_inflight.discard((expr, frame))
            if frame == self._selected_frame_index:
                self._eval_cache[expr] = value
                emit = True
        if emit:
            self._post_evaluated(expr, value)

    def _evaluate_cb_unlocked(self) -> EvaluateFn | None:
        with self._lock:
            return self._evaluate_cb

    def _evaluate_batch_cb_unlocked(self) -> EvaluateBatchFn | None:
        with self._lock:
            return self._evaluate_batch_cb

    # -- Checkpoint (called from worker thread) -------------------------

    def checkpoint(
        self,
        line: int,
        *,
        source_name: str = "",
        local_vars: dict[str, Any] | None = None,
        script_type: str = "pre_request",
        env_changes: dict[str, Any] | None = None,
        global_changes: dict[str, Any] | None = None,
        call_stack: list[CallFrame] | None = None,
        selected_frame_index: int = 0,
        force_pause: bool = False,
    ) -> bool:
        """Called at each statement boundary by the debug worker.

        Returns ``True`` to continue execution, ``False`` to stop.
        Blocks if the debugger should pause at this line.

        *force_pause* is used for uncaught-exception pauses (Deno CDP).
        """
        with self._lock:
            if self._stop_requested:
                return False

            should_pause = force_pause or (
                self._step_mode
                in (
                    StepMode.STEP_OVER,
                    StepMode.STEP_INTO,
                )
                or (self._breakpoints_enabled and line in self._breakpoints)
            )

            if not should_pause:
                self._last_line = line
                return True

            # Pause execution.
            self._state = DebugState.PAUSED
            self._last_line = line
            self._selected_frame_index = selected_frame_index
            stack = call_stack or []
            info: DebugPauseInfo = {
                "line": line,
                "source_name": source_name,
                "local_vars": local_vars or {},
                "script_type": script_type,
                "env_changes": env_changes or {},
                "global_changes": global_changes or {},
                "call_stack": stack,
                "selected_frame_index": selected_frame_index,
            }
            self._pause_info = info
            callback = self._on_pause
        self.clear_eval_cache()

        # Prepare to block — clear before callback so a resume()
        # called from within the callback is not lost.
        self._pause_event.clear()

        # Notify UI (outside lock to avoid deadlock).
        if callback is not None:
            callback(info)

        # Block until resume or stop.
        self._pause_event.wait()

        with self._lock:
            if self._stop_requested:
                return False
            self._state = DebugState.RUNNING
            return True

    # -- Resume commands (called from UI thread) ------------------------

    def resume(self, mode: StepMode = StepMode.CONTINUE) -> None:
        """Resume execution with the given step mode."""
        with self._lock:
            self._step_mode = mode
            self._pause_event.set()


class _EvalWorker:
    """Drains the eval queue on a ``threading`` thread (not a ``QThread``).

    Must not be a Qt child of :class:`DebugProtocol`: runtimes register
    evaluate callbacks from the debug worker thread while the protocol
    object lives on the GUI thread.
    """

    def __init__(self, protocol: DebugProtocol) -> None:
        """Bind to *protocol* and prepare the background loop."""
        self._protocol = protocol
        self._wake = threading.Event()
        self._stopping = False
        self._thread = threading.Thread(
            target=self._run,
            name="DebugEvalWorker",
            daemon=True,
        )

    def start(self) -> None:
        """Start the background drain loop."""
        self._thread.start()

    def wake(self) -> None:
        """Wake the worker to drain the queue."""
        self._wake.set()

    def stop(self) -> None:
        """Request shutdown and wake the run loop."""
        self._stopping = True
        self._wake.set()

    def join(self, timeout: float) -> None:
        """Wait for the drain loop to exit."""
        self._thread.join(timeout)

    def _run(self) -> None:
        """Process queued watch expressions until stopped."""
        while not self._stopping:
            self._wake.wait()
            self._wake.clear()
            while True:
                with self._protocol._lock:
                    batch = self._protocol._drain_eval_queue()
                if not batch:
                    break
                self._run_batch(batch)

    def _run_batch(self, batch: list[tuple[str, int]]) -> None:
        batch_cb = self._protocol._evaluate_batch_cb_unlocked()
        if batch_cb is not None:
            try:
                values = batch_cb(batch)
            except Exception as exc:
                values = [f"<error: {exc}>"] * len(batch)
            if len(values) != len(batch):
                values = (values + ["<error>"] * len(batch))[: len(batch)]
            for (expr, frame), value in zip(batch, values, strict=False):
                self._protocol._set_eval_result(expr, frame, value)
            return
        cb = self._protocol._evaluate_cb_unlocked()
        if cb is None:
            for expr, frame in batch:
                self._protocol._set_eval_result(expr, frame, "<unavailable>")
            return
        for expr, frame in batch:
            try:
                value = cb(expr, frame)
            except Exception as exc:
                value = f"<error: {exc}>"
            self._protocol._set_eval_result(expr, frame, value)
