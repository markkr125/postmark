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
FrameLocalsFn = Callable[[int], dict[str, Any]]


class DebugProtocol:
    """State machine that coordinates pause/resume between runtime and UI.

    Thread-safe: the debug worker calls :meth:`checkpoint` from a
    background thread, and UI calls :meth:`resume` / :meth:`stop` from
    the main thread.
    """

    def __init__(self) -> None:
        """Initialise the debug protocol in IDLE state."""
        self._state = DebugState.IDLE
        self._breakpoints: dict[int, str | None] = {}
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
        self._frame_locals_cb: FrameLocalsFn | None = None

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
        """Register a thread-safe evaluator used while :attr:`state` is PAUSED."""
        with self._lock:
            self._evaluate_cb = cb

    def set_frame_locals_callback(self, cb: FrameLocalsFn | None) -> None:
        """Register a callback that returns ``local_vars`` for a stack frame index."""
        with self._lock:
            self._frame_locals_cb = cb

    def evaluate(self, expr: str, *, frame_index: int | None = None) -> str:
        """Evaluate *expr* in the paused runtime; return a display string.

        Thread-safe.  When not paused or no adapter is registered, returns a
        short placeholder string instead of raising.
        """
        with self._lock:
            if self._state != DebugState.PAUSED:
                return "<not paused>"
            cb = self._evaluate_cb
            idx = self._selected_frame_index if frame_index is None else frame_index
        if cb is None:
            return "<unavailable>"
        try:
            return cb(expr, idx)
        except Exception as exc:
            return f"<error: {exc}>"

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
            self._evaluate_cb = None
            self._frame_locals_cb = None

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
            self._frame_locals_cb = None

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
    ) -> bool:
        """Called at each statement boundary by the debug worker.

        Returns ``True`` to continue execution, ``False`` to stop.
        Blocks if the debugger should pause at this line.
        """
        with self._lock:
            if self._stop_requested:
                return False

            should_pause = (
                self._step_mode
                in (
                    StepMode.STEP_OVER,
                    StepMode.STEP_INTO,
                )
                or line in self._breakpoints
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
