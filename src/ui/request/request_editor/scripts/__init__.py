"""Scripts tab sub-package — script editing, version history, and undo.

Re-exports:

- :class:`_ScriptsMixin` — dual-editor scripts tab (pre-request + test).
"""

from __future__ import annotations

from ui.request.request_editor.scripts.scripts_mixin import _ScriptsMixin

__all__ = ["_ScriptsMixin"]
