"""Session tab restore — batched chips, parallel prefetch, deferred materialisation."""

from ui.main_window.session_restore.prefetch import SessionPrefetchResult, SessionPrefetchWorker
from ui.main_window.session_restore.restore import (
    begin_session_restore,
    flush_session_restore,
    restore_tabs_synchronous,
)

__all__ = [
    "SessionPrefetchResult",
    "SessionPrefetchWorker",
    "begin_session_restore",
    "flush_session_restore",
    "restore_tabs_synchronous",
]
