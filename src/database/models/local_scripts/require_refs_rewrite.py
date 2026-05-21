"""Rewrite ``pm.require("local:…")`` literals in persisted script storage."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from database.database import get_session
from database.models.collections.model.collection_model import CollectionModel
from database.models.collections.model.request_model import RequestModel

from .model.local_script_model import LocalScriptModel

_PM_REQUIRE_LOCAL_CALL_RE = re.compile(
    r"""pm\s*\.\s*require\s*\(\s*(?P<q>['"])local:(?P<path>[^'"]+)(?P=q)\s*\)""",
)


def _rewrite_local_path_in_literal(path: str, old: str, new: str, *, prefix: bool) -> str:
    """Return *path* after applying exact or prefix replacement rules."""
    if prefix:
        needle = f"{old}/"
        if not path.startswith(needle):
            return path
        return new + path[len(old) :]
    if path == old:
        return new
    return path


def rewrite_local_requires_in_text(text: str, old: str, new: str, *, prefix: bool) -> str:
    """Rewrite ``local:`` paths inside ``pm.require`` literals in *text*.

    Preserves the opening quote style (single vs double) of each match.
    When *prefix* is ``True``, *old* / *new* are folder virtual prefixes without
    a trailing slash; only ``local:{old}/…`` continuations are updated.
    When *prefix* is ``False``, *old* / *new* are full virtual file paths.
    """
    if not text or "local:" not in text:
        return text

    def _repl(match: re.Match[str]) -> str:
        quote = match.group("q")
        path = match.group("path")
        updated = _rewrite_local_path_in_literal(path, old, new, prefix=prefix)
        if updated == path:
            return match.group(0)
        return f"pm.require({quote}local:{updated}{quote})"

    return _PM_REQUIRE_LOCAL_CALL_RE.sub(_repl, text)


def _text_matches_filter(text: str, old: str, *, prefix: bool) -> bool:
    """Return whether *text* may contain a rewrite target (pre-filter)."""
    if prefix:
        return f"local:{old}/" in text
    return f"local:{old}" in text


def _rewrite_json_string_values(data: dict[str, Any], old: str, new: str, *, prefix: bool) -> bool:
    """Rewrite string values in a JSON dict; return whether anything changed."""
    changed = False
    for key, value in list(data.items()):
        if isinstance(value, str) and _text_matches_filter(value, old, prefix=prefix):
            updated = rewrite_local_requires_in_text(value, old, new, prefix=prefix)
            if updated != value:
                data[key] = updated
                changed = True
    return changed


def _like_pattern(old: str, *, prefix: bool) -> str:
    """Build a SQL ``LIKE`` pattern for the pre-filter."""
    if prefix:
        return f"%local:{old}/%"
    return f"%local:{old}%"


def _json_dict_may_match(data: dict[str, Any] | None, old: str, *, prefix: bool) -> bool:
    """Return whether any string value in a JSON dict may contain a rewrite target."""
    if not isinstance(data, dict):
        return False
    return any(
        isinstance(value, str) and _text_matches_filter(value, old, prefix=prefix)
        for value in data.values()
    )


def rewrite_local_requires_in_db_session(
    session: Session,
    old: str,
    new: str,
    *,
    prefix: bool,
) -> int:
    """Rewrite matching literals in all persisted stores; return rows/fields touched."""
    pattern = _like_pattern(old, prefix=prefix)
    updates = 0

    script_stmt = select(LocalScriptModel).where(LocalScriptModel.content.like(pattern))
    for script in session.scalars(script_stmt):
        content = script.content or ""
        updated = rewrite_local_requires_in_text(content, old, new, prefix=prefix)
        if updated != content:
            script.content = updated
            updates += 1

    request_stmt = select(RequestModel).where(
        or_(RequestModel.scripts.isnot(None), RequestModel.events.isnot(None))
    )
    for request in session.scalars(request_stmt):
        touched = False
        for attr in ("scripts", "events"):
            data = getattr(request, attr)
            if not _json_dict_may_match(data, old, prefix=prefix):
                continue
            if isinstance(data, dict) and _rewrite_json_string_values(
                data, old, new, prefix=prefix
            ):
                setattr(request, attr, data)
                flag_modified(request, attr)
                touched = True
        if touched:
            updates += 1

    collection_stmt = select(CollectionModel).where(CollectionModel.events.isnot(None))
    for collection in session.scalars(collection_stmt):
        events = collection.events
        if not _json_dict_may_match(events, old, prefix=prefix):
            continue
        if isinstance(events, dict) and _rewrite_json_string_values(
            events, old, new, prefix=prefix
        ):
            collection.events = events
            flag_modified(collection, "events")
            updates += 1

    return updates


def rewrite_local_requires_in_db(old: str, new: str, *, prefix: bool) -> int:
    """Rewrite ``local:`` paths across the workspace in a standalone transaction."""
    with get_session() as session:
        return rewrite_local_requires_in_db_session(session, old, new, prefix=prefix)
