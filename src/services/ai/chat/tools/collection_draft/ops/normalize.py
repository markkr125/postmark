"""Soft-normalize helpers for collection-draft field payloads."""

from __future__ import annotations

import json
import re
from typing import Any

from services.ai.chat.tools.collection_draft.ops.limits import (
    MAX_AUTH_CHARS,
    MAX_PARAM_DESCRIPTION_CHARS,
    MAX_SAVED_RESPONSE_BODY,
    MAX_SAVED_RESPONSES,
    MAX_SIGNATURE_CHARS,
    MAX_VARIABLES,
)
from services.ai.chat.tools.collection_draft.recipes import (
    known_recipe_kinds,
    recipe_for_kind,
    validate_signature_overrides,
)
from services.ai.chat.tools.collection_draft.state import DraftSavedResponse


def err(code: str, hint: str) -> str:
    """Return a machine- and human-readable failure body."""
    return f"ok: false\nerror: {code}\nhint: {hint}\n"


def unwrap_err(block: str) -> tuple[str, str]:
    """Return the ``(error, hint)`` from an :func:`err` block."""
    fields = {
        key.strip(): value.strip()
        for key, _, value in (line.partition(": ") for line in block.strip().splitlines())
        if key.strip() in ("error", "hint")
    }
    return fields.get("error", "invalid"), fields.get("hint", block.strip())


def folder_path(raw: str) -> tuple[str, ...]:
    """Split a ``A/B`` folder path into cleaned segments."""
    return tuple(segment.strip() for segment in raw.split("/") if segment.strip())


def truncate(text: str, limit: int) -> tuple[str, bool]:
    """Return ``(text, truncated)`` capped at *limit* characters."""
    value = text or ""
    if len(value) <= limit:
        return value, False
    return value[:limit], True


# Methods that normally carry a documented request example in API specs.
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
# Prefer tagged fences (json/xml), then untagged JSON-looking or XML-looking blocks.
_FENCED_BODY_RE = re.compile(
    r"```(json|xml|text)?\s*\n([\s\S]*?)\n```",
    re.IGNORECASE,
)


def coerce_request_body(
    raw: Any,
    *,
    description: str = "",
) -> tuple[str, list[str]]:
    """Serialize a request body, recovering a fenced example from *description* if needed.

    Models sometimes put only a parameter table in ``description`` and omit
    ``body``. When the description still contains a fenced JSON or XML example,
    reuse it so POST/PUT/PATCH requests are not saved empty.
    """
    warnings: list[str] = []
    if isinstance(raw, dict | list):
        return json.dumps(raw, indent=2, ensure_ascii=False), warnings
    text = str(raw or "").strip()
    if text:
        return text, warnings
    for match in _FENCED_BODY_RE.finditer(description or ""):
        lang = (match.group(1) or "").lower()
        candidate = (match.group(2) or "").strip()
        if not candidate:
            continue
        if lang == "json" or (not lang and candidate[0] in "{["):
            try:
                parsed = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                if lang == "json":
                    continue
            else:
                warnings.append("body recovered from description JSON example")
                if isinstance(parsed, dict | list):
                    return json.dumps(parsed, indent=2, ensure_ascii=False), warnings
                return candidate, warnings
        if lang == "xml" or (not lang and candidate.lstrip().startswith("<")):
            # Prefer real XML payloads over incidental HTML fragments in prose.
            lower = candidate[:80].lower()
            if (
                lang == "xml"
                or lower.startswith("<?xml")
                or re.match(
                    r"<[A-Za-z_][\w:.-]*(\s|>|/)",
                    candidate.lstrip(),
                )
            ):
                warnings.append("body recovered from description XML example")
                return candidate, warnings
    return "", warnings


def missing_body_warning(name: str, method: str) -> str | None:
    """Return a loud warning when a POST/PUT/PATCH has no body or query input.

    We keep the request (and its saved responses) instead of skipping: skipping
    on this path previously wiped out whole batches — the model would re-issue
    the same table-only batch and finish with an empty collection. A warning is
    visible on the tool card and guides the next call without losing work.
    """
    if method not in _BODY_METHODS:
        return None
    return (
        f"NO request body/params for {method} {name!r} — the request will save "
        "EMPTY and its saved-response Request Body tab will be empty. If the "
        "document shows a request example, re-add this endpoint with ``body`` "
        "(JSON object/array or XML/text) and/or ``params``; if the endpoint is "
        "documented with no request body (query/header only), ignore this."
    )


def normalize_kv_rows(
    raw: list[dict[str, Any]] | dict[str, Any] | None,
    *,
    max_description: int = MAX_PARAM_DESCRIPTION_CHARS,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fold objects into key/value(/description) rows and truncate descriptions."""
    warnings: list[str] = []
    if raw is None:
        return [], warnings
    if isinstance(raw, dict):
        items: list[dict[str, Any]] = [{"key": str(k), "value": str(v)} for k, v in raw.items()]
    elif isinstance(raw, list):
        items = [dict(row) for row in raw if isinstance(row, dict)]
    else:
        return [], warnings
    rows: list[dict[str, Any]] = []
    for item in items:
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        row: dict[str, Any] = {
            "key": key,
            "value": str(item.get("value") or ""),
            "enabled": bool(item.get("enabled", True)),
        }
        description = str(item.get("description") or "").strip()
        if description:
            description, truncated = truncate(description, max_description)
            if truncated:
                warnings.append(f"param description truncated for {key!r}")
            row["description"] = description
        rows.append(row)
    return rows, warnings


def script_flags(pre: str, test: str) -> str:
    """Return a short ``pre,test`` / ``pre`` / ``test`` / ``none`` label."""
    parts: list[str] = []
    if (pre or "").strip():
        parts.append("pre")
    if (test or "").strip():
        parts.append("test")
    return ",".join(parts) if parts else "none"


def parse_signature(raw: Any) -> tuple[Any, str | None]:
    """Validate a signature dict and return ``(recipe|None, error_body|None)``."""
    if raw is None:
        return None, None
    if not isinstance(raw, dict):
        return None, err(
            "bad_signature",
            "signature must be an object with kind (and optional header/var names).",
        )
    try:
        encoded = json.dumps(raw, ensure_ascii=False)
    except (TypeError, ValueError):
        return None, err("bad_signature", "signature must be JSON-serializable.")
    if len(encoded) > MAX_SIGNATURE_CHARS:
        return None, err(
            "signature_too_large",
            f"signature must be under {MAX_SIGNATURE_CHARS} characters when serialized.",
        )
    kind = str(raw.get("kind") or "").strip()
    if not kind:
        return None, err(
            "bad_signature",
            f"signature.kind is required. Known kinds: {', '.join(known_recipe_kinds())}.",
        )
    override_err = validate_signature_overrides(raw)
    if override_err is not None:
        return None, err("bad_signature", override_err)
    recipe = recipe_for_kind(kind, raw)
    if recipe is None:
        return None, err(
            "unknown_signature_kind",
            f"Unknown signature kind {kind!r}. Known kinds: "
            f"{', '.join(known_recipe_kinds())}. For undocumented algorithms, "
            "put a note in the collection description instead of inventing crypto.",
        )
    return recipe, None


def normalize_auth(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(auth|None, error_body|None)`` with a hard size cap."""
    if raw is None:
        return None, None
    if not isinstance(raw, dict):
        return None, err("bad_auth", "auth must be an object with a type field.")
    auth_type = str(raw.get("type") or "").strip()
    if not auth_type:
        return None, None
    auth = dict(raw)
    try:
        encoded = json.dumps(auth, ensure_ascii=False)
    except (TypeError, ValueError):
        return None, err("bad_auth", "auth must be JSON-serializable.")
    if len(encoded) > MAX_AUTH_CHARS:
        return None, err(
            "auth_too_large",
            f"auth must be under {MAX_AUTH_CHARS} characters when serialized.",
        )
    return auth, None


def normalize_variables(
    raw: Any,
) -> tuple[list[dict[str, Any]], list[str], str | None]:
    """Return variable rows; trim oversize lists instead of failing the start."""
    warnings: list[str] = []
    if raw is None:
        return [], warnings, None
    if not isinstance(raw, list):
        return [], warnings, err("bad_variables", "variables must be a list of key/value objects.")
    rows = [dict(var) for var in raw if isinstance(var, dict)]
    if len(rows) > MAX_VARIABLES:
        warnings.append(
            f"variables trimmed to {MAX_VARIABLES} (dropped {len(rows) - MAX_VARIABLES})"
        )
        rows = rows[:MAX_VARIABLES]
    return rows, warnings, None


def normalize_saved_responses(
    raw: Any,
    *,
    request_name: str,
) -> tuple[list[DraftSavedResponse], list[str]]:
    """Cap and soft-skip saved-response examples for one request."""
    warnings: list[str] = []
    if raw is None:
        return [], warnings
    if not isinstance(raw, list):
        warnings.append(f"'{request_name}': ignored non-list responses")
        return [], warnings
    items = list(raw)
    if len(items) > MAX_SAVED_RESPONSES:
        warnings.append(f"'{request_name}': saved responses trimmed to {MAX_SAVED_RESPONSES}")
        items = items[:MAX_SAVED_RESPONSES]
    out: list[DraftSavedResponse] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            warnings.append(f"'{request_name}': skipped non-object response {index}")
            continue
        name = str(item.get("name") or f"Example {index}").strip()
        status = str(item.get("status") or "").strip()
        code_raw = item.get("code")
        code: int | None = None
        if code_raw is not None and str(code_raw).strip() != "":
            try:
                code = int(code_raw)
            except (TypeError, ValueError):
                warnings.append(f"ignored non-integer response code for {name!r}")
        headers, header_warnings = normalize_kv_rows(item.get("headers"))
        warnings.extend(header_warnings)
        body = item.get("body")
        if isinstance(body, dict | list):
            body_text = json.dumps(body, indent=2, ensure_ascii=False)
        else:
            body_text = str(body or "")
        body_text, truncated = truncate(body_text, MAX_SAVED_RESPONSE_BODY)
        if truncated:
            warnings.append(f"saved response body truncated for {name!r}")
        out.append(
            DraftSavedResponse(
                name=name,
                status=status,
                code=code,
                headers=headers,
                body=body_text,
            )
        )
    return out, warnings


__all__ = [
    "coerce_request_body",
    "err",
    "folder_path",
    "missing_body_warning",
    "normalize_auth",
    "normalize_kv_rows",
    "normalize_saved_responses",
    "normalize_variables",
    "parse_signature",
    "script_flags",
    "truncate",
    "unwrap_err",
]
