"""Multi-goal batching for postmark_workspace_query."""

from __future__ import annotations

from typing import Any

from .constants import _MAX_OUTPUT_CHARS

_MAX_GOALS = 4
_GOAL_SOFT_CHARS = _MAX_OUTPUT_CHARS // 2


def _normalize_goals(raw: list[dict[str, Any]] | None) -> list[dict[str, Any]] | str:
    """Validate and normalize a goals list; return error string on failure."""
    if not raw:
        return []
    if len(raw) > _MAX_GOALS:
        return f"At most {_MAX_GOALS} goals allowed per call (got {len(raw)})."
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return f"goals[{i}] must be an object."
        gid = str(item.get("id") or f"g{i}").strip()
        if not gid or gid in seen:
            return f"goals[{i}] needs a unique non-empty id."
        seen.add(gid)
        scope = str(item.get("scope") or "").strip()
        if not scope:
            return f"goals[{i}] ({gid}) requires scope."
        within_ref = item.get("within")
        within_ids = item.get("within_ids")
        sections = item.get("sections")
        if sections is not None and not isinstance(sections, list):
            return f"goals[{i}] sections must be a list of strings."
        out.append(
            {
                "id": gid,
                "scope": scope,
                "search": str(item.get("search") or ""),
                "target_id": item.get("target_id"),
                "within": str(within_ref) if within_ref else None,
                "within_ids": within_ids if isinstance(within_ids, list) else None,
                "sections": [str(s) for s in sections] if isinstance(sections, list) else None,
            }
        )
    # Dependency order: goals that reference within must come after that id.
    ordered: list[dict[str, Any]] = []
    pending = list(out)
    resolved_ids: set[str] = set()
    while pending:
        progress = False
        for goal in list(pending):
            dep = goal.get("within")
            if dep and dep not in resolved_ids:
                continue
            ordered.append(goal)
            pending.remove(goal)
            resolved_ids.add(str(goal["id"]))
            progress = True
        if not progress:
            return (
                "goals within= references form a cycle or point at unknown ids. "
                "Reference earlier goal ids only."
            )
    return ordered


def execute_goals(
    goals: list[dict[str, Any]],
    *,
    session_id: str,
    dispatch: Any,
) -> str:
    """Run batched goals via *dispatch* and return one labeled observation."""
    normalized = _normalize_goals(goals)
    if isinstance(normalized, str):
        return normalized
    if not normalized:
        return "Provide a non-empty goals list."

    hit_sets: dict[str, list[int]] = {}
    sections_out: list[str] = ["Multi-goal exploration:"]
    markers: list[str] = []
    total_chars = 0
    truncated_goals: list[str] = []

    from services.ai.chat.workspace_snapshot import get_last_search_hits
    from .helpers import _with_leading_markers
    from .render.search.within import REQUEST_LINK_RE

    for goal in normalized:
        gid = str(goal["id"])
        within_ids = goal.get("within_ids")
        within_ref = goal.get("within")
        if within_ref:
            prior = hit_sets.get(str(within_ref))
            if prior is None:
                # Fall back to last search hits when the prior goal stored none.
                prior = get_last_search_hits(session_id) or []
            within_ids = prior if prior else [-1]

        sections = goal.get("sections")
        search = str(goal.get("search") or "")
        if goal["scope"] == "insights" and sections:
            search = ",".join(sections)

        body = dispatch(
            str(goal["scope"]),
            session_id=session_id,
            target_id=goal.get("target_id"),
            search=search,
            within_ids=within_ids,
        )
        # Capture hit ids for downstream within= chaining.
        ids = [int(m.group(1)) for m in REQUEST_LINK_RE.finditer(body)]
        if ids:
            hit_sets[gid] = sorted(set(ids))

        block = f"\n### Goal `{gid}` (scope={goal['scope']})\n{body}"
        if total_chars + len(block) > _GOAL_SOFT_CHARS:
            truncated_goals.append(gid)
            remain = max(_GOAL_SOFT_CHARS - total_chars, 200)
            block = block[:remain] + f"\n… (goal `{gid}` truncated by shared budget)"
            sections_out.append(block)
            total_chars += len(block)
            break
        sections_out.append(block)
        total_chars += len(block)

    if truncated_goals:
        markers.append(
            "[partial] Shared multi-goal output budget truncated: "
            + ", ".join(truncated_goals)
            + (" and skipped later goals" if len(normalized) > len(hit_sets) else "")
            + "."
        )
    sections_out.append(
        "\nRelated next steps (assistant only — plain English to the user; "
        "never quote operators):\n"
        "- Offer to refine among these hits or run a health check on them.\n"
        "- Open deeplinks with focus= when pointing at scripts/body/assertions.\n"
        "- Product how-to for a finding → postmark_wiki_query."
    )
    text = "\n".join(sections_out)
    return _with_leading_markers(text, markers) if markers else text
