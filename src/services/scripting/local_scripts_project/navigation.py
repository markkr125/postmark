"""Resolve ESM import specifiers to local script ids for editor navigation."""

from __future__ import annotations

from database.database import get_session
from services.local_script_service import LocalScriptService
from services.scripting.local_script_modules import build_module_index
from services.scripting.local_scripts_project.import_graph import (
    _resolve_specifier,
    _resolve_specifier_with_extension,
    import_specifier_at_offset,
)
from services.scripting.local_scripts_project.mirror import rel_path_for_script_id


def resolve_esm_import_target_script_id(
    script_id: int,
    source: str,
    offset: int,
) -> int | None:
    """Return the script id for a relative import under the cursor, or ``None``."""
    from_rel = rel_path_for_script_id(script_id)
    if from_rel is None:
        return None
    hit = import_specifier_at_offset(source, offset)
    if hit is None:
        return None
    spec, _, _ = hit
    try:
        resolved = _resolve_specifier(from_rel, spec)
        with get_session() as session:
            index = build_module_index(session)
        target = _resolve_specifier_with_extension(resolved, index)
        if target is None:
            return None
        return LocalScriptService.resolve_script_id_by_virtual_path(target)
    except ValueError:
        return None
