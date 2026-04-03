"""Version history sub-package.

Re-exports public symbols so callers can still use::

    from ui.request.request_editor.scripts.version_history import (
        VersionHistoryDialog,
    )
"""

from __future__ import annotations

from ui.request.request_editor.scripts.version_history.dialog import (
    _SCREEN_FRACTION,
    VersionHistoryDialog,
)
from ui.request.request_editor.scripts.version_history.diff_viewer import _DiffViewer
from ui.request.request_editor.scripts.version_history.helpers import (
    _format_timestamp,
    compute_fold_ranges,
)

__all__ = [
    "_SCREEN_FRACTION",
    "VersionHistoryDialog",
    "_DiffViewer",
    "_format_timestamp",
    "compute_fold_ranges",
]
