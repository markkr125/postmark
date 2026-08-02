"""Human-readable formatting for expandable tool-activity observation text."""

from __future__ import annotations

import ast

_ERROR_TITLES: dict[str, str] = {
    "bad_request": "Bad request",
    "too_many_responses": "Too many saved responses",
    "too_many_params": "Too many parameters",
    "too_many_variables": "Too many variables",
    "body_too_large": "Request body too large",
    "no_draft": "No draft in progress",
}

# Leading observation keys that are metadata, not freeform body.
_HEADER_KEYS = frozenset(
    {
        "ok",
        "error",
        "hint",
        "message",
        "summary",
        "added",
        "skipped",
        "warnings",
        "note",
        "requests",
        "document",
        "uri",
        "chunk",
        "pages",
        "screenshots",
        "screenshots_omitted",
        "next_step",
    }
)


def _parse_list_field(raw: str | None) -> list[str] | None:
    """Parse a Python-list-repr observation field into strings, if possible."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return []
    try:
        value = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return [text]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _humanize_code(code: str) -> str:
    """Return a short readable label for a snake_case error code."""
    cleaned = (code or "").strip()
    if not cleaned:
        return "failed"
    known = _ERROR_TITLES.get(cleaned)
    if known:
        return known
    return cleaned.replace("_", " ")


def _bullet_block(title: str, items: list[str]) -> list[str]:
    """Return a titled bullet list, or empty when *items* is empty."""
    if not items:
        return []
    lines = ["", title]
    lines.extend(f"• {item}" for item in items)
    return lines


def _split_observation(text: str) -> tuple[dict[str, str], str]:
    """Split leading ``key: value`` metadata from the freeform body.

    Document-import observations are ``header kv lines``, a blank line, then the
    chunk body, then a trailing ``next_step:`` line. Draft observations are
    almost entirely kv lines with no freeform body.
    """
    fields: dict[str, str] = {}
    body_lines: list[str] = []
    in_body = False
    for line in text.splitlines():
        if not in_body:
            if not line.strip():
                in_body = True
                continue
            key, sep, value = line.partition(": ")
            cleaned = key.strip()
            if sep and cleaned and (" " not in cleaned) and cleaned not in fields:
                fields[cleaned] = value.strip()
                continue
            in_body = True
            body_lines.append(line)
            continue
        body_lines.append(line)

    # Pull a trailing next_step out of the freeform block into fields.
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()
    if body_lines:
        key, sep, value = body_lines[-1].partition(": ")
        if sep and key.strip() == "next_step":
            fields.setdefault("next_step", value.strip())
            body_lines.pop()
            while body_lines and not body_lines[-1].strip():
                body_lines.pop()

    return fields, "\n".join(body_lines).strip()


def format_tool_activity_output(raw: str) -> str:
    """Turn machine observation bodies into readable expand-panel prose.

    Preserves freeform chunk bodies (document import) under a short status
    header. Falls back to the stripped raw text when the body is not structured.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    fields, body = _split_observation(text)
    if "ok" not in fields and "error" not in fields and "hint" not in fields:
        return text

    lines: list[str] = []
    ok = fields.get("ok", "").lower()
    err = fields.get("error")
    hint = fields.get("hint") or fields.get("message") or ""
    summary = fields.get("summary") or ""

    if ok == "false" or err:
        lines.append(f"Failed — {_humanize_code(err or 'failed')}")
        if hint:
            lines.extend(["", hint])
        elif summary:
            lines.extend(["", summary])
    elif ok == "true":
        added = _parse_list_field(fields.get("added"))
        note = fields.get("note") or ""
        if added is not None and not added:
            lines.append(note or "No endpoints in this chunk")
        elif added is not None:
            n = len(added)
            lines.append(f"Added {n} request" + ("" if n == 1 else "s"))
            if note:
                lines.extend(["", note])
        elif summary:
            lines.append(summary)
        else:
            lines.append("Succeeded")
        if hint:
            lines.extend(["", hint])
    elif summary:
        lines.append(summary)
    elif hint:
        lines.append(hint)

    meta_order = ("document", "uri", "chunk", "pages", "screenshots", "screenshots_omitted")
    meta = [f"{key}: {fields[key]}" for key in meta_order if fields.get(key)]
    if meta:
        lines.extend(["", *meta])

    skipped = _parse_list_field(fields.get("skipped")) or []
    warnings = _parse_list_field(fields.get("warnings")) or []
    lines.extend(_bullet_block("Skipped", skipped))
    lines.extend(_bullet_block("Warnings", warnings))

    if body:
        lines.extend(["", body])

    next_step = fields.get("next_step")
    if next_step:
        lines.extend(["", f"Next: {next_step}"])

    shown = _HEADER_KEYS | {"ok", "error"}
    extras = [f"{key}: {value}" for key, value in fields.items() if key not in shown and value]
    if extras:
        lines.extend(["", *extras])

    return "\n".join(lines).strip() or text


__all__ = ["format_tool_activity_output"]
