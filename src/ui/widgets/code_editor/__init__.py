"""Code editor sub-package.

Re-exports the public API so external code continues to use::

    from ui.widgets.code_editor import CodeEditorWidget, SyntaxError_
"""

from __future__ import annotations

from ui.widgets.code_editor.editor_widget import CodeEditorWidget
from ui.widgets.code_editor.gutter import SyntaxError_

__all__ = ["CodeEditorWidget", "SyntaxError_"]
