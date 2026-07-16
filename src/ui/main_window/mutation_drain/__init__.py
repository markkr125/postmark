"""GUI drain for Agent mutate/execute bridge events."""

from __future__ import annotations

from ui.main_window.mutation_drain.drain import drain_mutation_bridge
from ui.main_window.mutation_drain.reload import (
    close_stale_workspace_tabs,
    close_tabs_for_mutation_ids,
    reload_open_folder_from_db,
    reload_open_request_from_db,
)

__all__ = [
    "close_stale_workspace_tabs",
    "close_tabs_for_mutation_ids",
    "drain_mutation_bridge",
    "reload_open_folder_from_db",
    "reload_open_request_from_db",
]
