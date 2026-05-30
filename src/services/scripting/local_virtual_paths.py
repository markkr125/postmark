"""Virtual POSIX paths for local scripts (re-export from database layer)."""

from __future__ import annotations

from database.models.local_scripts.virtual_paths import (
    folder_virtual_prefix,
    script_virtual_rel_path,
)

__all__ = ["folder_virtual_prefix", "script_virtual_rel_path"]
