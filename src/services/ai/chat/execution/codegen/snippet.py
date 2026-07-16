"""Generate code snippets with secrets kept as ``{{var}}`` placeholders."""

from __future__ import annotations

from typing import Any


def _auth_with_placeholders_only(auth: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return auth with secret fields forced to ``{{var}}`` or empty placeholders.

    Never resolves environment values into secret auth fields for codegen.
    """
    if not isinstance(auth, dict):
        return None
    from services.ai.chat.tools.workspace_mutate.common import (
        _AUTH_SECRET_KEYS,
        _PLACEHOLDER_RE,
    )

    out = dict(auth)
    auth_type = str(out.get("type") or "").strip().lower()
    if not auth_type or auth_type in {"noauth", "inherit"}:
        return out

    def _scrub_entries(entries: Any) -> list[dict[str, Any]]:
        if not isinstance(entries, list):
            return []
        cleaned: list[dict[str, Any]] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            key = str(row.get("key") or "")
            val = str(row.get("value") or "")
            if (
                key in _AUTH_SECRET_KEYS
                or key.casefold() in {k.casefold() for k in _AUTH_SECRET_KEYS}
            ) and not _PLACEHOLDER_RE.match(val.strip()):
                row["value"] = f"{{{{{key}}}}}"
            cleaned.append(row)
        return cleaned

    # Nested per-type entry lists (bearer, apikey, oauth2, …).
    for nest_key, nest_val in list(out.items()):
        if nest_key == "type":
            continue
        if isinstance(nest_val, list):
            out[nest_key] = _scrub_entries(nest_val)
        elif isinstance(nest_val, dict):
            nested = dict(nest_val)
            for sk in list(nested.keys()):
                if sk in _AUTH_SECRET_KEYS or sk.casefold() in {
                    k.casefold() for k in _AUTH_SECRET_KEYS
                }:
                    sv = str(nested.get(sk) or "")
                    if not _PLACEHOLDER_RE.match(sv.strip()):
                        nested[sk] = f"{{{{{sk}}}}}"
            out[nest_key] = nested
    return out


def run_generate_snippet(
    *,
    request_id: int | None = None,
    language: str | None = None,
    draft: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a code snippet; secret auth fields stay as ``{{var}}``."""
    from services.collection_service import CollectionService
    from services.http.snippet_generator.generator import SnippetGenerator

    lang = (language or "").strip()
    if not lang:
        return {"ok": False, "error": "language_required", "message": "language is required"}

    method = "GET"
    url = ""
    headers: str | None = None
    body: str | None = None
    auth: dict[str, Any] | None = None
    ids: dict[str, int] = {}

    if request_id is not None:
        req = CollectionService.get_request(request_id)
        if req is None:
            return {"ok": False, "error": "request_not_found", "message": f"id={request_id}"}
        method = str(req.method or "GET")
        url = str(req.url or "")
        headers = str(req.headers) if req.headers else None
        body = str(req.body) if req.body is not None else None
        auth = CollectionService.get_request_auth_chain(request_id)
        ids["request_id"] = int(request_id)
    elif isinstance(draft, dict):
        method = str(draft.get("method") or "GET")
        url = str(draft.get("url") or "")
        headers = str(draft["headers"]) if draft.get("headers") is not None else None
        body = str(draft["body"]) if draft.get("body") is not None else None
        auth = draft.get("auth") if isinstance(draft.get("auth"), dict) else None
    else:
        return {
            "ok": False,
            "error": "request_id_or_draft_required",
            "message": "Provide request_id or draft",
        }

    safe_auth = _auth_with_placeholders_only(auth)
    # Avoid resolving secrets via apply_auth — pass placeholder-scrubbed auth only.
    try:
        snippet = SnippetGenerator.generate(
            lang,
            method=method,
            url=url,
            headers=headers,
            body=body,
            auth=safe_auth,
        )
    except Exception as exc:
        return {"ok": False, "error": "snippet_failed", "message": str(exc)}

    if len(snippet) > 12_000:
        snippet = snippet[:12_000] + "\n… (truncated)"

    return {
        "ok": True,
        "summary": f"Generated {lang} snippet",
        "snippet": snippet,
        "language": lang,
        "ids": ids,
        "url": url,
    }
