"""Request editor sub-package.

Re-exports the public API so external code continues to use::

    from ui.request.request_editor import RequestEditorWidget
"""

from __future__ import annotations

from ui.request.request_editor.editor_widget import RequestEditorWidget

__all__ = ["RequestEditorWidget"]
