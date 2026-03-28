"""Debug sub-package for script step-through debugging.

Provides:

- :class:`DebugProtocol` — state machine and breakpoint management.
- :func:`inject_checkpoints` — JS statement-boundary injection.
- :func:`js_debug_execute` — JS debug execution with V8 callbacks.
- :func:`py_debug_execute` — Python debug execution with settrace IPC.

Re-exports for convenience::

    from services.scripting.debug import DebugProtocol, DebugState
"""

from __future__ import annotations

from services.scripting.debug.js_debug import debug_execute as js_debug_execute
from services.scripting.debug.js_debug import inject_checkpoints
from services.scripting.debug.protocol import DebugPauseInfo, DebugProtocol, DebugState, StepMode
from services.scripting.debug.py_debug import debug_execute as py_debug_execute

__all__ = [
    "DebugPauseInfo",
    "DebugProtocol",
    "DebugState",
    "StepMode",
    "inject_checkpoints",
    "js_debug_execute",
    "py_debug_execute",
]
