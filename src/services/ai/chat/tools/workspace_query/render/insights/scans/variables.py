"""Variable-related insights scans."""

from __future__ import annotations

from typing import Any

from services.environment_service import EnvironmentService

from ....helpers import _link, _script_assigned_variable_keys
from .common import (
    _active_disabled_keys,
    _defined_keys,
    _extract_var_refs,
    _request_field_texts,
)


def scan_variable_issues(
    request_rows: list[tuple[int, str, str, str]],
    *,
    env_id: int | None,
    fields_by_id: dict[int, Any],
    scripts_by_id: dict[int, Any],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return unresolved, unused, case-mismatch, and disabled-ref rows."""
    defined = _defined_keys()
    defined_cf: dict[str, list[str]] = {}
    for key in defined:
        defined_cf.setdefault(key.casefold(), []).append(key)
    disabled = _active_disabled_keys(env_id)
    used_exact: set[str] = set()
    assigned: set[str] = set()
    unresolved_lines: list[str] = []
    mismatch_lines: list[str] = []
    disabled_lines: list[str] = []

    for rid, name, _method, url in request_rows:
        texts, pre, test = _request_field_texts(rid, url, fields_by_id, scripts_by_id)
        assigned |= _script_assigned_variable_keys(pre, test)
        refs = _extract_var_refs(*texts)
        used_exact |= refs
        variables = EnvironmentService.build_combined_variable_map(env_id, rid)
        unresolved_keys: list[str] = []
        for key in sorted(refs):
            token = "{{" + key + "}}"
            substituted = EnvironmentService.substitute(token, variables)
            if substituted == token and key not in assigned:
                unresolved_keys.append(key)
            if key not in defined and key.casefold() in defined_cf:
                exact = defined_cf[key.casefold()][0]
                mismatch_lines.append(
                    f"- {_link('request', rid, name)} — `{{{{{key}}}}}` (defined as `{exact}`)"
                )
            if key in disabled:
                disabled_lines.append(
                    f"- {_link('request', rid, name)} — `{{{{{key}}}}}` "
                    "(disabled in active environment)"
                )
        if unresolved_keys:
            unresolved_lines.append(
                f"- {_link('request', rid, name)} — "
                + ", ".join(f"`{{{{{k}}}}}`" for k in unresolved_keys)
            )

    unused_lines: list[str] = []
    for key, labels in sorted(defined.items(), key=lambda kv: kv[0].casefold()):
        if key in used_exact or key in assigned:
            continue
        unused_lines.append(f"- `{key}` ({', '.join(labels[:3])})")
    return unresolved_lines, unused_lines, mismatch_lines, disabled_lines
