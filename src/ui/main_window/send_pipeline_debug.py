"""Debug-hover value-merging utilities for the send pipeline.

Pure functions (no Qt state). Used by:
- :mod:`ui.main_window.send_pipeline`
- ``tests/unit/services/test_script_debug_cdp.py`` (re-exported from send_pipeline)
"""

from __future__ import annotations

from typing import Any


def _merge_debug_hover_values(pause_info: dict) -> dict[str, Any]:
    """Merge values for ``set_debug_locals`` hover. Later sources override on name clash.

    Precedence: ``globals`` snapshot, then ``pm`` snapshot, then CDP ``locals``,
    then env/workspace changes (last wins on name clash for the latter two).
    """
    merged: dict[str, Any] = {}
    lv = pause_info.get("local_vars") or {}
    if (
        "globals" in lv
        and "pm" in lv
        and isinstance(lv.get("pm"), dict)
        and isinstance(lv.get("globals"), dict)
    ):
        merged.update(lv.get("globals", {}))
        merged.update(lv.get("pm", {}))
    else:
        flat = {k: v for k, v in lv.items() if k not in {"locals", "scopes"}}
        merged.update(flat)
    locals_ = lv.get("locals")
    if isinstance(locals_, dict):
        merged.update(locals_)
    merged.update(pause_info.get("env_changes") or {})
    merged.update(pause_info.get("global_changes") or {})
    return merged


def _debug_hover_root_objects(pause_info: dict) -> dict[str, Any]:
    """Whole-object snapshots for hover when the flat merge omits the root name.

    When ``globals`` and ``pm`` dicts are present, :func:`_merge_debug_hover_values`
    flattens ``pm`` keys, so the identifier ``pm`` is not in the merged map.
    """
    roots: dict[str, Any] = {}
    lv = pause_info.get("local_vars") or {}
    pm = lv.get("pm")
    if isinstance(pm, dict):
        roots["pm"] = pm
    gl = lv.get("globals")
    if isinstance(gl, dict):
        con = gl.get("console")
        if isinstance(con, dict):
            roots["console"] = con
    return roots


def _ensure_script_host_materialized(host: Any) -> None:
    """Build lazy script panes on request editors before debug UI touches them."""
    ensure = getattr(host, "_ensure_scripts_editors", None)
    if callable(ensure):
        ensure()
