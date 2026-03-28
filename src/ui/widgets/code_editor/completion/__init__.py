"""Code completion sub-package.

Re-exports the public API for autocomplete features::

    from ui.widgets.code_editor.completion import CompletionEngine, CompletionPopup
"""

from __future__ import annotations

from ui.widgets.code_editor.completion.engine import CompletionEngine
from ui.widgets.code_editor.completion.popup import CompletionPopup

__all__ = ["CompletionEngine", "CompletionPopup"]
