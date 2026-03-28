"""Right sidebar sub-package.

Re-exports :class:`RightSidebar` for use from the main window:

    from ui.sidebar import RightSidebar
"""

from __future__ import annotations

from ui.sidebar.debug_panel import DebugPanel
from ui.sidebar.saved_responses.panel import SavedResponsesPanel
from ui.sidebar.sidebar_widget import RightSidebar

__all__ = ["DebugPanel", "RightSidebar", "SavedResponsesPanel"]
