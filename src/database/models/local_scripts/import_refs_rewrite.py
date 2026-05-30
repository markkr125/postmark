"""Rewrite static relative ``import`` / ``export … from`` paths in local script storage."""

from __future__ import annotations

import posixpath
import re
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.scripting.local_script_modules import lookup_rel_path_by_script_id
from services.scripting.local_scripts_project.import_graph import (
    _IMPORT_FROM_RE,
    _EXPORT_FROM_RE,
    _resolve_specifier,
)

from .model.local_script_model import LocalScriptModel

_SPEC_PATTERNS = (_IMPORT_FROM_RE, _EXPORT_FROM_RE)


def _resolved_matches(resolved: str, old: str, *, prefix: bool) -> bool:
    if prefix:
        return resolved == old or resolved.startswith(f"{old}/")
    return resolved == old


def _relative_spec(from_rel: str, target_rel: str) -> str:
    base_dir = PurePosixPath(from_rel).parent
    rel = posixpath.relpath(target_rel, base_dir.as_posix())
    if not rel.startswith("."):
        rel = f"./{rel}"
    return rel


def _rewrite_spec(
    from_rel: str,
    spec: str,
    old: str,
    new: str,
    *,
    prefix: bool,
) -> str:
    try:
        resolved = _resolve_specifier(from_rel, spec)
    except ValueError:
        return spec
    if not _resolved_matches(resolved, old, prefix=prefix):
        return spec
    new_resolved = new + resolved[len(old) :] if prefix else new
    return _relative_spec(from_rel, new_resolved)


def rewrite_relative_imports_in_text(
    text: str,
    from_rel: str,
    old: str,
    new: str,
    *,
    prefix: bool,
) -> str:
    """Rewrite relative import specifiers in *text* when they resolve under *old*."""
    if not text or ("./" not in text and "../" not in text):
        return text

    def _sub_one(pattern: re.Pattern[str], source: str) -> str:
        def _repl(match: re.Match[str]) -> str:
            spec = match.group("spec")
            updated = _rewrite_spec(from_rel, spec, old, new, prefix=prefix)
            if updated == spec:
                return match.group(0)
            return match.group(0).replace(spec, updated, 1)

        return pattern.sub(_repl, source)

    out = text
    for pattern in _SPEC_PATTERNS:
        out = _sub_one(pattern, out)
    return out


def rewrite_relative_imports_in_db_session(
    session: Session,
    old: str,
    new: str,
    *,
    prefix: bool,
) -> int:
    """Rewrite import specifiers in all local scripts; return rows touched."""
    updates = 0
    stmt = select(LocalScriptModel)
    for script in session.scalars(stmt):
        rel = lookup_rel_path_by_script_id(script.id)
        if rel is None:
            continue
        content = script.content or ""
        updated = rewrite_relative_imports_in_text(
            content,
            rel,
            old,
            new,
            prefix=prefix,
        )
        if updated != content:
            script.content = updated
            updates += 1
    return updates


def rewrite_relative_imports_in_db(old: str, new: str, *, prefix: bool) -> int:
    """Rewrite import specifiers in all local scripts (standalone session)."""
    from database.database import get_session

    with get_session() as session:
        return rewrite_relative_imports_in_db_session(session, old, new, prefix=prefix)
