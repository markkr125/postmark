"""Folder editor sub-package.

Re-exports the public API so that ``from ui.request.folder_editor import
FolderEditorWidget`` continues to work after the split.
"""

from __future__ import annotations

# Re-export for backward compatibility (used by tests).
from services.scripting.context import normalize_events as _normalize_events
from ui.request.folder_editor.editor_widget import FolderEditorWidget

__all__ = ["FolderEditorWidget", "_normalize_events"]
