"""Persisted breakpoints and watch expressions for script editors."""

from __future__ import annotations

from typing import Any, TypedDict

SCRIPT_TYPE_PRE = "pre_request"
SCRIPT_TYPE_TEST = "test"
SCRIPT_TYPES = (SCRIPT_TYPE_PRE, SCRIPT_TYPE_TEST)

DEBUG_METADATA_KEY = "debug"
MAX_CONDITION_BYTES = 1024


class BreakpointRecord(TypedDict, total=False):
    """One persisted line breakpoint (0-based line)."""

    line: int
    condition: str | None


class DebugScriptSlice(TypedDict, total=False):
    """Breakpoints and watches for one script pane."""

    breakpoints: list[BreakpointRecord]
    watches: list[str]


class DebugPerTypeBlob(TypedDict, total=False):
    """Host A: nested under ``scripts`` / ``events``."""

    pre_request: DebugScriptSlice
    test: DebugScriptSlice


def truncate_condition(condition: str | None) -> str | None:
    """Truncate *condition* to :data:`MAX_CONDITION_BYTES` (UTF-8), never drop the breakpoint."""
    if condition is None:
        return None
    text = condition.strip()
    if not text:
        return None
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_CONDITION_BYTES:
        return text
    truncated = encoded[:MAX_CONDITION_BYTES]
    while truncated and (truncated[-1] & 0xC0) == 0x80:
        truncated = truncated[:-1]
    return truncated.decode("utf-8", errors="ignore") or None


def _parse_breakpoint_list(raw: Any) -> list[BreakpointRecord]:
    """Normalize a JSON breakpoint list."""
    if not isinstance(raw, list):
        return []
    out: list[BreakpointRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        line = item.get("line")
        if not isinstance(line, int) or line < 0:
            continue
        cond_raw = item.get("condition")
        cond: str | None = None
        if isinstance(cond_raw, str) and cond_raw.strip():
            cond = truncate_condition(cond_raw)
        out.append(BreakpointRecord(line=line, condition=cond))
    return out


def _parse_watch_list(raw: Any) -> list[str]:
    """Normalize a JSON watch expression list."""
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _parse_slice(raw: Any) -> DebugScriptSlice:
    """Parse one per-type or flat slice dict."""
    if not isinstance(raw, dict):
        return DebugScriptSlice(breakpoints=[], watches=[])
    bps = _parse_breakpoint_list(raw.get("breakpoints"))
    watches = _parse_watch_list(raw.get("watches"))
    return DebugScriptSlice(breakpoints=bps, watches=watches)


def slice_is_empty(slice_data: DebugScriptSlice | None) -> bool:
    """Return whether *slice_data* has no breakpoints or watches."""
    if not slice_data:
        return True
    return not (slice_data.get("breakpoints") or slice_data.get("watches"))


def parse_from_scripts_dict(scripts_or_events: Any) -> dict[str, DebugScriptSlice]:
    """Read Host A debug metadata from a ``scripts`` or ``events`` dict."""
    result: dict[str, DebugScriptSlice] = {
        SCRIPT_TYPE_PRE: DebugScriptSlice(breakpoints=[], watches=[]),
        SCRIPT_TYPE_TEST: DebugScriptSlice(breakpoints=[], watches=[]),
    }
    if not isinstance(scripts_or_events, dict):
        return result
    debug = scripts_or_events.get(DEBUG_METADATA_KEY)
    if not isinstance(debug, dict):
        return result
    for st in SCRIPT_TYPES:
        if st in debug:
            result[st] = _parse_slice(debug.get(st))
    return result


def parse_from_local_metadata(blob: Any) -> DebugScriptSlice:
    """Read Host B flat debug metadata from ``local_scripts.debug_metadata``."""
    return _parse_slice(blob)


def slice_to_local_metadata(slice_data: DebugScriptSlice) -> dict[str, Any]:
    """Serialize a flat slice for ``local_scripts.debug_metadata``."""
    return _slice_to_json_dict(slice_data)


def merge_debug_into_scripts_dict(
    existing: dict[str, Any] | None,
    per_type: dict[str, DebugScriptSlice],
) -> dict[str, Any]:
    """Merge Host A debug blobs into *existing* scripts/events dict (shallow copy)."""
    base: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    debug_out: dict[str, Any] = {}
    for st in SCRIPT_TYPES:
        sl = per_type.get(st) or DebugScriptSlice(breakpoints=[], watches=[])
        if not slice_is_empty(sl):
            debug_out[st] = _slice_to_json_dict(sl)
    if debug_out:
        base[DEBUG_METADATA_KEY] = debug_out
    elif DEBUG_METADATA_KEY in base:
        del base[DEBUG_METADATA_KEY]
    return base


def debug_blob_from_scripts_dict(scripts_or_events: Any) -> dict[str, Any] | None:
    """Return the raw ``debug`` subtree if present."""
    if not isinstance(scripts_or_events, dict):
        return None
    debug = scripts_or_events.get(DEBUG_METADATA_KEY)
    return debug if isinstance(debug, dict) else None


def scripts_dict_has_debug(scripts_or_events: Any) -> bool:
    """Return whether *scripts_or_events* carries non-empty persisted debug metadata."""
    per_type = parse_from_scripts_dict(scripts_or_events)
    return not slice_is_empty(per_type.get(SCRIPT_TYPE_PRE)) or not slice_is_empty(
        per_type.get(SCRIPT_TYPE_TEST)
    )


def slice_from_editor(
    breakpoints: dict[int, str | None],
    watches: list[str],
) -> DebugScriptSlice:
    """Build a slice from live editor / scopes panel state."""
    bps: list[BreakpointRecord] = []
    for line in sorted(breakpoints):
        cond = truncate_condition(breakpoints[line])
        bps.append(BreakpointRecord(line=line, condition=cond))
    return DebugScriptSlice(
        breakpoints=bps,
        watches=[w.strip() for w in watches if w.strip()],
    )


def breakpoints_dict_from_slice(slice_data: DebugScriptSlice) -> dict[int, str | None]:
    """Convert a slice to editor ``line → condition`` map."""
    out: dict[int, str | None] = {}
    for rec in slice_data.get("breakpoints") or []:
        line = rec.get("line")
        if not isinstance(line, int) or line < 0:
            continue
        cond = rec.get("condition")
        out[line] = cond if isinstance(cond, str) and cond.strip() else None
    return out


def _slice_to_json_dict(slice_data: DebugScriptSlice) -> dict[str, Any]:
    """JSON-serializable flat or nested slice body."""
    bps: list[dict[str, Any]] = []
    for rec in slice_data.get("breakpoints") or []:
        line = rec.get("line")
        if not isinstance(line, int):
            continue
        cond = rec.get("condition")
        entry: dict[str, Any] = {"line": line}
        if isinstance(cond, str) and cond.strip():
            entry["condition"] = truncate_condition(cond)
        else:
            entry["condition"] = None
        bps.append(entry)
    return {
        "breakpoints": bps,
        "watches": list(slice_data.get("watches") or []),
    }


def per_type_blob_to_db_dict(per_type: dict[str, DebugScriptSlice]) -> dict[str, Any]:
    """Build the ``debug`` value for repository merge (Host A)."""
    out: dict[str, Any] = {}
    for st in SCRIPT_TYPES:
        sl = per_type.get(st) or DebugScriptSlice(breakpoints=[], watches=[])
        if not slice_is_empty(sl):
            out[st] = _slice_to_json_dict(sl)
    return out
