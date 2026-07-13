"""Missing-tests, duplicate, and script-regression insights scans."""

from __future__ import annotations

import re
from typing import Any

from services.script_version_service import ScriptVersionService

from ....helpers import _link, _scripts_from_data, _truncate_url


def scan_missing_tests(
    request_rows: list[tuple[int, str, str, str]],
    scripts_by_id: dict[int, Any],
    assertion_counts: dict[int, tuple[int, int]],
) -> list[str]:
    """Rows for requests with neither test script nor enabled assertions."""
    lines: list[str] = []
    for rid, name, _method, _url in request_rows:
        row = scripts_by_id.get(rid)
        scripts = _scripts_from_data(
            {"scripts": row[1], "events": row[2]} if row is not None else None
        )
        _total, enabled = assertion_counts.get(rid, (0, 0))
        if scripts.get("test") or enabled > 0:
            continue
        lines.append(f"- {_link('request', rid, name)} (no test script or assertions)")
    return lines


def scan_duplicates(
    dup_groups: dict[tuple[str, str], list[tuple[int, str, str]]],
) -> list[str]:
    """Rows for duplicate method+URL groups."""
    lines: list[str] = []
    for (method, _key), group in sorted(dup_groups.items(), key=lambda kv: (-len(kv[1]), kv[0][0])):
        if len(group) < 2:
            continue
        names = ", ".join(_link("request", rid, name) for rid, name, _raw in group)
        lines.append(f"- {method} {_truncate_url(group[0][2])}: {names}")
    return lines


def scan_script_regressions(
    request_rows: list[tuple[int, str, str, str]],
    scripts_by_id: dict[int, Any],
) -> list[str]:
    """Test script previously had content / pm.test but current is empty."""
    lines: list[str] = []
    for rid, name, _method, _url in request_rows:
        row = scripts_by_id.get(rid)
        current = ""
        if row is not None:
            norm = _scripts_from_data({"scripts": row[1], "events": row[2]})
            current = str(norm.get("test") or "")
        versions = ScriptVersionService.list_versions(request_id=rid, script_type="test", limit=2)
        if len(versions) < 2:
            continue
        previous = str(versions[1].get("content") or "")
        if not previous.strip():
            continue
        prev_has_test = bool(re.search(r"\bpm\.test\b", previous)) or bool(previous.strip())
        curr_has_test = bool(re.search(r"\bpm\.test\b", current)) or bool(current.strip())
        if prev_has_test and not curr_has_test:
            lines.append(f"- {_link('request', rid, name)} — test script emptied vs prior version")
    return lines
