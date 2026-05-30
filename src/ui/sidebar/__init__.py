"""Sidebar rails and flyout panels.

Re-exports :class:`LeftSidebar`, :class:`LocalScriptsSidebarPanel`, and
:class:`RightSidebar` for the main window:

    from ui.sidebar import LeftSidebar, LocalScriptsSidebarPanel, RightSidebar
"""

from __future__ import annotations

from ui.sidebar.debug_inspector_split import DebugInspectorSplit
from ui.sidebar.debug_panel import (
    DEBUG_VARIABLES_PAGE_MESSAGE,
    DEBUG_VARIABLES_PAGE_TREE,
    DebugControls,
    DebugPanel,
    DebugVariablesPanel,
)
from ui.sidebar.debug_call_stack_panel import CallStackPanel
from ui.sidebar.saved_responses.panel import SavedResponsesPanel
from ui.sidebar.left_sidebar import LeftSidebar
from ui.sidebar.local_scripts_sidebar_panel import LocalScriptsSidebarPanel
from ui.sidebar.snippets_sidebar_panel import SnippetsSidebarPanel
from ui.sidebar.sidebar_widget import RightSidebar

__all__ = [
    "DEBUG_VARIABLES_PAGE_MESSAGE",
    "DEBUG_VARIABLES_PAGE_TREE",
    "CallStackPanel",
    "DebugControls",
    "DebugInspectorSplit",
    "DebugPanel",
    "DebugVariablesPanel",
    "LeftSidebar",
    "LocalScriptsSidebarPanel",
    "RightSidebar",
    "SavedResponsesPanel",
    "SnippetsSidebarPanel",
]
