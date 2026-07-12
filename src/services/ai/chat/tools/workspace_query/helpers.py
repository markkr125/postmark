"""Shared helpers for workspace query rendering."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from typing import Any, cast

from services.scripting.context import _SENSITIVE_KEYS, mask_sensitive_value, normalize_events

from .constants import (
    REDACTED_PLACEHOLDER,
    SECRET_PLACEHOLDER,
    _BODY_PREVIEW_MAX,
    _ENV_KEY_CAP,
    _HEADER_VALUE_MAX,
    _MAX_RESULT_ROWS,
    _QS_PARAM_RE,
    _SECRET_BODY_KEYS,
    _SENSITIVE_HEADERS,
    _SENSITIVE_QS_PARAMS,
    _URL_PREVIEW_MAX,
)

_CANON_SECRET_BODY_KEYS = frozenset(k.replace("_", "").replace("-", "") for k in _SECRET_BODY_KEYS)

_PLAIN_FORM_BODY_RE = re.compile(r"^[^=&\s]+=[^&]*(&[^=&\s]+=[^&]*)*$")
_FORM_KV_RE = re.compile(r"(^|&)([^=&#]+)=([^&#]*)")
_CONSOLE_KV_RE = re.compile(r"(^|[\s&;])([^=&#\s]+)=([^&#\s;,}\"']+)")
_XML_SECRET_TAG_RE = re.compile(
    r"(<([\w:-]*(?:password|secret|token|api_key|apikey))\b[^>]*>)(.*?)(</\2>)",
    re.IGNORECASE | re.DOTALL,
)
_URL_USERINFO_RE = re.compile(r"^([a-z][a-z0-9+.\-]*://)([^/@?#]+)@")

# OAuth / metadata keys that contain sensitive substrings but are not secrets.
_NON_SECRET_KEY_NAMES = frozenset(
    {
        "token_type",
        "token-type",
        "expires_in",
        "expires_at",
        "expiry",
        "scope",
        "grant_type",
        "grant-type",
        "token_endpoint",
        "token-endpoint",
    }
)


def _key_is_sensitive(name: str) -> bool:
    """Return True when a form/env/header-ish *name* should have its value redacted."""
    folded = name.casefold()
    if folded in _NON_SECRET_KEY_NAMES:
        return False
    if folded in _SENSITIVE_QS_PARAMS or folded in _SECRET_BODY_KEYS:
        return True
    canon = folded.replace("_", "").replace("-", "")
    if canon in _CANON_SECRET_BODY_KEYS:
        return True
    if canon.endswith(("token", "secret", "password", "passwd", "apikey", "credential")):
        return True
    return bool(_SENSITIVE_KEYS.search(name))


def _lang_from_content_type(headers: list[Any] | None) -> str | None:
    """Map a stored Content-Type header to a preview/redaction language."""
    if not headers:
        return None
    for row in headers:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key", "")).casefold()
        if key != "content-type":
            continue
        ct = str(row.get("value", "")).casefold()
        if "xml" in ct:
            return "xml"
        if "html" in ct:
            return "html"
        if "json" in ct:
            return "json"
        if "x-www-form-urlencoded" in ct or "form-urlencoded" in ct:
            return "x-www-form-urlencoded"
    return None


def _resolve_response_body_lang(
    body: str,
    lang: str,
    *,
    headers: list[Any] | None = None,
) -> str:
    """Infer how to redact a response body from headers, hint, and markup."""
    from_ct = _lang_from_content_type(headers)
    if from_ct:
        return from_ct
    preview_lang = (lang or "").casefold()
    stripped = body.lstrip()
    if preview_lang in ("xml", "html"):
        return preview_lang
    if stripped.startswith("<"):
        return "html" if preview_lang == "html" else "xml"
    if preview_lang == "json" or (stripped and stripped[0] in "{["):
        return "json"
    return preview_lang or "text"


def _link(kind: str, entity_id: int, label: str, *, focus: str | None = None) -> str:
    """Build a markdown deep-link to open a workspace item."""
    url = f"postmark://{kind}/{entity_id}"
    if focus:
        url = f"{url}?focus={focus}"
    safe = label.replace("[", "\\[").replace("]", "\\]")
    return f"[{safe}]({url})"


_FOLLOW_UP_IDS_HEADER = (
    "Ids for follow-up calls (tool arguments only — never paste into the user message):"
)


def _follow_up_ids_block(entries: list[tuple[str, int]]) -> list[str]:
    """Format machine-only ``target_id`` lines for subsequent tool calls.

    List rows meant for the model to copy into the user message must stay free of
    bare ``[id=N]`` tags; put numeric ids here instead.
    """
    if not entries:
        return []
    lines = [_FOLLOW_UP_IDS_HEADER]
    for label, tid in entries:
        lines.append(f"  {label} → target_id={tid}")
    return lines


def _with_leading_markers(body: str, markers: list[str]) -> str:
    """Put partial/capped/authoritative markers above the body so truncation keeps them."""
    cleaned = [m.strip() for m in markers if m and m.strip()]
    if not cleaned:
        return body
    return "\n".join(cleaned) + ("\n\n" + body if body else "")


def _truncate_text(text: str, *, max_len: int = _BODY_PREVIEW_MAX) -> str:
    """Truncate *text* with an explicit marker."""
    if len(text) <= max_len:
        return text
    return f"{text[:max_len]}… (truncated, {len(text)} chars)"


def _redact_url(url: str) -> str:
    """Redact sensitive URL userinfo and query-string parameter values for display."""
    userinfo_match = _URL_USERINFO_RE.match(url)
    if userinfo_match:
        scheme, userinfo = userinfo_match.group(1), userinfo_match.group(2)
        if "{{" not in userinfo:
            url = f"{scheme}{REDACTED_PLACEHOLDER}@{url[userinfo_match.end() :]}"

    def _replace(match: re.Match[str]) -> str:
        sep, name, value = match.group(1), match.group(2), match.group(3)
        if value and "{{" not in value and name.casefold() in _SENSITIVE_QS_PARAMS:
            return f"{sep}{name}={REDACTED_PLACEHOLDER}"
        return match.group(0)

    return _QS_PARAM_RE.sub(_replace, url)


def _truncate_url(url: str, *, max_len: int = _URL_PREVIEW_MAX) -> str:
    """Shorten a URL for display; matching still uses the full value."""
    url = _redact_url(url)
    return url if len(url) <= max_len else f"{url[:max_len]}…"


def _cap_rows(
    rows: list[str],
    *,
    label: str,
    limit: int | None = None,
    hint: str = "narrow with a more specific scope",
) -> list[str]:
    """Cap a result list, putting a partial marker first when truncated."""
    row_limit = _MAX_RESULT_ROWS if limit is None else limit
    if len(rows) <= row_limit:
        return rows
    extra = len(rows) - row_limit
    marker = f"[partial] Showing first {row_limit} of {row_limit + extra} {label} ({hint})."
    return [marker, *rows[:row_limit]]


def _request_label_link(
    request_id: int | None,
    name: str,
    *,
    focus: str | None = None,
) -> str:
    """Return a named request deep-link, or plain *name* when no id is available."""
    if isinstance(request_id, int) and request_id > 0:
        return _link("request", request_id, name, focus=focus)
    return name


def _mask_param_value(key: str, value: str) -> str:
    """Redact sensitive query-parameter literals unless they use {{var}} placeholders."""
    if "{{" in value:
        return _truncate_text(value, max_len=_HEADER_VALUE_MAX)
    if _key_is_sensitive(key):
        return REDACTED_PLACEHOLDER
    return _truncate_text(value, max_len=_HEADER_VALUE_MAX)


def _request_body_lang(data: dict[str, Any]) -> str:
    """Infer preview language for request-body secret redaction."""
    mode = str(data.get("body_mode") or "").casefold()
    if mode == "raw":
        opts = data.get("body_options")
        if isinstance(opts, dict):
            raw_sub = opts.get("raw")
            if isinstance(raw_sub, dict):
                return str(raw_sub.get("language", "text"))
    if mode in ("raw", "graphql"):
        return "json"
    return mode or "text"


def _redact_request_body(body: Any, data: dict[str, Any]) -> str:
    """Redact secrets in a request body without truncating."""
    text = str(body)
    mode = str(data.get("body_mode") or "").casefold()
    if mode in ("form-data", "x-www-form-urlencoded"):
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            pass
        else:
            if isinstance(parsed, list) and all(isinstance(row, dict) for row in parsed):
                new_list: list[dict[str, Any]] = []
                for row in parsed:
                    new_row = dict(row)
                    raw_value = str(row.get("value", ""))
                    key = str(row.get("key", ""))
                    if "{{" in raw_value:
                        new_row["value"] = raw_value
                    elif _key_is_sensitive(key):
                        new_row["value"] = REDACTED_PLACEHOLDER
                    else:
                        new_row["value"] = raw_value
                    new_list.append(new_row)
                return json.dumps(new_list, ensure_ascii=False)
    return _redact_response_body(text, _request_body_lang(data))


def _format_request_body_preview(body: Any, data: dict[str, Any]) -> str:
    """Redact secrets and truncate a request body for LLM display."""
    return _truncate_text(_redact_request_body(body, data))


def _mask_header_value(key: str, value: str) -> str:
    """Redact sensitive header literals unless they use {{var}} placeholders."""
    if "{{" in value:
        return _truncate_text(value, max_len=_HEADER_VALUE_MAX)
    if key.lower() in _SENSITIVE_HEADERS or _SENSITIVE_KEYS.search(key):
        return REDACTED_PLACEHOLDER
    return _truncate_text(value, max_len=_HEADER_VALUE_MAX)


def _redact_body_secrets(value: Any) -> Any:
    """Recursively mask dict values whose keys look like secrets."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            canon = key.casefold().replace("_", "").replace("-", "")
            secret_key = isinstance(key, str) and (
                canon in _CANON_SECRET_BODY_KEYS
                or canon.endswith(("token", "secret", "password", "apikey"))
            )
            if secret_key:
                if isinstance(item, dict | list):
                    out[key] = _redact_body_secrets(item)
                elif item is not None and str(item) and "{{" not in str(item):
                    out[key] = SECRET_PLACEHOLDER
                else:
                    out[key] = item
            else:
                out[key] = _redact_body_secrets(item)
        return out
    if isinstance(value, list):
        return [_redact_body_secrets(item) for item in value]
    return value


def _redact_form_urlencoded_body(body: str) -> str:
    """Redact sensitive name=value pairs in urlencoded or plain-form bodies."""

    def _replace(match: re.Match[str]) -> str:
        prefix, name, value = match.group(1), match.group(2), match.group(3)
        if value and "{{" not in value and _key_is_sensitive(name):
            return f"{prefix}{name}={REDACTED_PLACEHOLDER}"
        return match.group(0)

    return _FORM_KV_RE.sub(_replace, body)


def _redact_xml_secret_elements(body: str) -> str:
    """Redact inner text of XML/HTML elements whose tag names look like secrets."""

    def _replace(match: re.Match[str]) -> str:
        open_tag, _tag_name, inner, close_tag = (
            match.group(1),
            match.group(2),
            match.group(3),
            match.group(4),
        )
        if "{{" in inner:
            return match.group(0)
        return f"{open_tag}{SECRET_PLACEHOLDER}{close_tag}"

    return _XML_SECRET_TAG_RE.sub(_replace, body)


def _redact_response_body(body: str, lang: str, *, headers: list[Any] | None = None) -> str:
    """Redact secrets in JSON, XML/HTML, form-shaped, or opaque key=value bodies."""
    resolved = _resolve_response_body_lang(body, lang, headers=headers)
    stripped = body.lstrip()
    if resolved == "json" or (stripped and stripped[0] in "{["):
        try:
            parsed = json.loads(body)
        except (ValueError, TypeError):
            pass
        else:
            redacted = _redact_body_secrets(parsed)
            return json.dumps(redacted, ensure_ascii=False)
    if resolved in ("xml", "html") or stripped.startswith("<"):
        return _redact_xml_secret_elements(body)
    if resolved in ("x-www-form-urlencoded", "urlencoded", "form") or (
        stripped and _PLAIN_FORM_BODY_RE.match(stripped)
    ):
        return _redact_form_urlencoded_body(body)
    # Opaque text: still mask key=value pairs that look like credentials.
    return _mask_opaque_kv_text(body)


def _mask_opaque_kv_text(text: str) -> str:
    """Mask sensitive ``key=value`` pairs in free-form / opaque body text."""

    def _replace(match: re.Match[str]) -> str:
        prefix, key, value = match.group(1), match.group(2), match.group(3)
        if "{{" in value:
            return match.group(0)
        if _key_is_sensitive(key) or mask_sensitive_value(key, value) != value:
            return f"{prefix}{key}={REDACTED_PLACEHOLDER}"
        return match.group(0)

    return _CONSOLE_KV_RE.sub(_replace, text)


def _redact_auth_value(value: str) -> str:
    """Redact a single auth field value unless it is a variable placeholder."""
    if not value or "{{" in value:
        return value
    return REDACTED_PLACEHOLDER


def _redact_auth(auth: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a copy of *auth* with secret values redacted."""
    if not auth:
        return auth
    out = dict(auth)
    auth_type = out.get("type")
    if isinstance(auth_type, str) and auth_type not in ("inherit", "noauth"):
        entries = out.get(auth_type)
        if isinstance(entries, list):
            out[auth_type] = [
                (
                    {**entry, "value": _redact_auth_value(str(entry.get("value", "")))}
                    if isinstance(entry, dict)
                    else entry
                )
                for entry in entries
            ]
        elif isinstance(entries, dict):
            redacted_entries: dict[str, Any] = {}
            for entry_key, entry_val in entries.items():
                if isinstance(entry_val, str):
                    redacted_entries[entry_key] = _redact_auth_value(entry_val)
                elif isinstance(entry_val, dict):
                    nested = _redact_auth(entry_val)
                    redacted_entries[entry_key] = nested if nested is not None else entry_val
                else:
                    redacted_entries[entry_key] = entry_val
            out[auth_type] = redacted_entries
    for key, val in list(out.items()):
        if key in ("type", "inherit") or key == auth_type:
            continue
        if isinstance(val, str) and val:
            out[key] = _redact_auth_value(val)
        elif isinstance(val, dict):
            out[key] = _redact_auth(val)
    return out


def _redact_env_values(values: list[Any] | None) -> list[dict[str, Any]]:
    """Mask secret-typed and sensitive-key environment variable values."""
    if not isinstance(values, list):
        return []
    rows: list[dict[str, Any]] = []
    for row in values:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        key = str(item.get("key", ""))
        raw = str(item.get("value", ""))
        if str(item.get("type", "")).lower() == "secret" or (
            raw and "{{" not in raw and _key_is_sensitive(key)
        ):
            item["value"] = SECRET_PLACEHOLDER
        rows.append(item)
    return rows


def _secret_keys_from_variable_rows(values: list[Any] | None) -> set[str]:
    """Return enabled secret-typed keys from a collection/env variable list."""
    if not isinstance(values, list):
        return set()
    keys: set[str] = set()
    for row in values:
        if not isinstance(row, dict):
            continue
        if str(row.get("type", "")).lower() == "secret" and row.get("enabled", True):
            keys.add(str(row.get("key", "")))
    return keys


def _collection_secret_keys_by_id(details: dict[str, Any]) -> dict[int, set[str]]:
    """Build per-collection secret key sets for variables in *details*."""
    from services.collection_service import CollectionService

    coll_ids: set[int] = set()
    for detail in details.values():
        if not isinstance(detail, dict):
            continue
        if detail.get("source") != "collection":
            continue
        source_id = detail.get("source_id")
        if isinstance(source_id, int):
            coll_ids.add(source_id)
    secret_by_id: dict[int, set[str]] = {}
    for cid in coll_ids:
        row = CollectionService.get_collection(cid)
        if row is None:
            continue
        keys = _secret_keys_from_variable_rows(
            row.variables if isinstance(row.variables, list) else None
        )
        if keys:
            secret_by_id[cid] = keys
    return secret_by_id


def _active_tab(snap: dict[str, Any]) -> dict[str, Any] | None:
    """Return the active tab snapshot dict, if any."""
    tabs = snap.get("tabs") or []
    for tab in tabs:
        if tab.get("is_active"):
            return cast(dict[str, Any], tab)
    idx = snap.get("active_tab_index")
    if isinstance(idx, int) and 0 <= idx < len(tabs):
        return cast(dict[str, Any], tabs[idx])
    return None


def _default_request_id(snap: dict[str, Any]) -> int | None:
    """Resolve default request id from the active tab."""
    tab = _active_tab(snap)
    if tab is None:
        return None
    rid = tab.get("request_id")
    return int(rid) if isinstance(rid, int) else None


def _default_collection_id(snap: dict[str, Any]) -> int | None:
    """Resolve default collection id from snapshot or active tab."""
    cid = snap.get("active_collection_id")
    if isinstance(cid, int):
        return cid
    tab = _active_tab(snap)
    if tab is None:
        return None
    tc = tab.get("collection_id")
    return int(tc) if isinstance(tc, int) else None


def _default_script_id(snap: dict[str, Any]) -> int | None:
    """Resolve default local script id from the active tab."""
    tab = _active_tab(snap)
    if tab is None:
        return None
    sid = tab.get("local_script_id")
    return int(sid) if isinstance(sid, int) else None


def _format_ts(value: Any) -> str:
    """Format a timestamp for display in the user's local timezone."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return text
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    else:
        return str(value) if value is not None else ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def _search_tokens(needle: str) -> list[str]:
    """Split a search needle into casefolded whitespace tokens."""
    return needle.casefold().split()


def _matches_tokens(hay: str, tokens: list[str]) -> bool:
    """Return True when every token is a substring of *hay* (case-insensitive)."""
    if not tokens:
        return True
    folded = hay.casefold()
    return all(t in folded for t in tokens)


def _env_global_search_matches(tokens: list[str]) -> list[str]:
    """Build environment/global hit rows for unrestricted workspace search."""
    from services.environment_service import EnvironmentService
    from services.scripting.context import load_globals, mask_sensitive_value

    rows: list[str] = []
    for env in EnvironmentService.fetch_all():
        eid = env.get("id")
        ename = str(env.get("name", ""))
        if not isinstance(eid, int):
            continue
        raw_values = env.get("values")
        redacted = _redact_env_values(raw_values if isinstance(raw_values, list) else None)
        hay_parts = [ename]
        for item in redacted:
            if item.get("enabled") is False:
                continue
            key = str(item.get("key", ""))
            value = str(item.get("value", ""))
            if value == SECRET_PLACEHOLDER:
                hay_parts.append(key)
            else:
                hay_parts.append(f"{key}={value}")
        if _matches_tokens(" ".join(hay_parts), tokens):
            rows.append(f"- {_link('environment', eid, ename)} (environment name/variable match)")
    globals_map = load_globals()
    for gkey in sorted(globals_map):
        raw = str(globals_map[gkey])
        masked = mask_sensitive_value(gkey, raw)
        hay_parts = [gkey]
        if masked == raw:
            hay_parts.append(raw)
        if _matches_tokens(" ".join(hay_parts), tokens):
            rows.append(f"- Globals · {gkey} (global variable match)")
    return rows


def _walk_tree(
    nodes: dict[str, Any],
    *,
    prefix: str = "",
    search: str = "",
    lines: list[str] | None = None,
    depth: int = 0,
) -> list[str]:
    """Depth-first walk of collection tree, optional case-insensitive filter."""
    if lines is None:
        lines = []
    tokens = _search_tokens(search) if search else []
    indent = "  " * depth
    for _key, node in sorted(nodes.items(), key=lambda kv: str(kv[1].get("name", "")).casefold()):
        ntype = node.get("type")
        name = str(node.get("name", ""))
        nid = node.get("id")
        path = f"{prefix}/{name}" if prefix else name
        if ntype == "folder" and isinstance(nid, int):
            if not search or _matches_tokens(path, tokens):
                suffix = "" if not search else f" · in {path}"
                lines.append(f"{indent}- {_link('collection', nid, name)} (folder){suffix}")
            _walk_tree(
                node.get("children") or {},
                prefix=path,
                search=search,
                lines=lines,
                depth=depth + 1,
            )
        elif ntype == "request" and isinstance(nid, int):
            method = str(node.get("method", "GET"))
            url = str(node.get("url", ""))
            hay = f"{name} {method} {url} {path}"
            if not search or _matches_tokens(hay, tokens):
                suffix = "" if not search else f" · in {path}"
                lines.append(
                    f"{indent}- {_link('request', nid, name)} — {method} "
                    f"{_truncate_url(url)}{suffix}"
                )
    return lines


def _walk_local_tree(
    nodes: dict[str, Any],
    *,
    prefix: str = "",
    search: str = "",
    lines: list[str] | None = None,
    depth: int = 0,
) -> list[str]:
    """Depth-first walk of the local-script tree with optional filter."""
    if lines is None:
        lines = []
    tokens = _search_tokens(search) if search else []
    indent = "  " * depth
    for _key, node in sorted(nodes.items(), key=lambda kv: str(kv[1].get("name", "")).casefold()):
        ntype = node.get("type")
        name = str(node.get("name", ""))
        if ntype == "folder" and isinstance(node.get("id"), int):
            path = f"{prefix}/{name}" if prefix else name
            if not search or _matches_tokens(path, tokens):
                lines.append(f"{indent}- {name} (folder)")
            _walk_local_tree(
                node.get("children") or {},
                prefix=path,
                search=search,
                lines=lines,
                depth=depth + 1,
            )
        elif ntype == "script" and isinstance(node.get("id"), int):
            sid = node["id"]
            lang = str(node.get("language", "javascript"))
            mod = str(node.get("module_format", "esm"))
            hay = f"{name} {lang} {mod}"
            if not search or _matches_tokens(hay, tokens):
                lines.append(f"{indent}- {_link('script', sid, name)} — {lang}/{mod}")
    return lines


def _scripts_from_data(data: dict[str, Any] | None) -> dict[str, str]:
    """Extract pre-request and test script source from request data."""
    if not data:
        return {}
    norm = normalize_events(data.get("scripts"))
    if not (norm.get("pre_request") or norm.get("test")):
        ev = normalize_events(data.get("events"))
        if ev:
            norm = ev
    return {
        k: v.strip() for k, v in norm.items() if k in ("pre_request", "test") and v and v.strip()
    }


def _format_env_pairs(values: list[dict[str, Any]]) -> list[str]:
    """Build display pairs for environment variables with key cap."""
    pairs = [
        f"{v.get('key', '')} = {_truncate_text(str(v.get('value', '')), max_len=_HEADER_VALUE_MAX)}"
        for v in values
        if v.get("enabled", True)
    ]
    if len(pairs) > _ENV_KEY_CAP:
        extra = len(pairs) - _ENV_KEY_CAP
        pairs = pairs[:_ENV_KEY_CAP]
        pairs.append(f"…and {extra} more")
    return pairs


_TIMING_PHASES: tuple[tuple[str, str], ...] = (
    ("dns", "dns_ms"),
    ("tcp", "tcp_ms"),
    ("tls", "tls_ms"),
    ("ttfb", "ttfb_ms"),
    ("download", "download_ms"),
    ("process", "process_ms"),
)


def _format_timing_compact(timing: dict[str, Any]) -> str:
    """Render non-zero timing phases as one compact line."""
    parts: list[str] = []
    for label, key in _TIMING_PHASES:
        raw = timing.get(key)
        if raw is None:
            continue
        ms = float(raw)
        if ms > 0:
            parts.append(f"{label} {int(ms)} ms")
    return " · ".join(parts)


def _format_network_compact(network: dict[str, Any]) -> str:
    """Render network metadata as one compact line."""
    parts: list[str] = []
    http_version = network.get("http_version")
    if http_version:
        parts.append(str(http_version))
    remote = network.get("remote_address")
    if remote:
        parts.append(str(remote))
    tls = network.get("tls_protocol")
    if tls:
        cipher = network.get("cipher_name")
        tls_bit = f"TLS {tls}"
        if cipher:
            tls_bit += f" ({cipher})"
        parts.append(tls_bit)
    return " · ".join(parts)


def _format_size_breakdown(data: dict[str, Any]) -> str:
    """Render request/response size ints when present on a live response."""
    parts: list[str] = []
    mapping = (
        ("req hdr", "request_headers_size"),
        ("req body", "request_body_size"),
        ("resp hdr", "response_headers_size"),
        ("resp body", "response_uncompressed_size"),
    )
    for label, key in mapping:
        val = data.get(key)
        if isinstance(val, int) and val > 0:
            parts.append(f"{label} {val} B")
    size_bytes = data.get("size_bytes")
    if isinstance(size_bytes, int) and size_bytes > 0 and "response_uncompressed_size" not in data:
        parts.append(f"resp {size_bytes} B")
    return " · ".join(parts)


_SCRIPT_SET_VAR_RE = re.compile(
    r"pm\.(?:environment|variables|globals|collectionVariables)\.set\s*\(\s*"
    r"(?P<q>['\"])(?P<key>[^'\"]+)(?P=q)",
    re.IGNORECASE,
)
_POSTMAN_SET_VAR_RE = re.compile(
    r"postman\.set(?:Environment|Global)Variable\s*\(\s*"
    r"(?P<q>['\"])(?P<key>[^'\"]+)(?P=q)",
    re.IGNORECASE,
)


def _script_assigned_variable_keys(*script_sources: str | None) -> set[str]:
    """Return variable keys assigned statically in pre-request/test script source."""
    keys: set[str] = set()
    for src in script_sources:
        if not src:
            continue
        for pattern in (_SCRIPT_SET_VAR_RE, _POSTMAN_SET_VAR_RE):
            keys.update(match.group("key") for match in pattern.finditer(src))
    return keys


def _format_variable_changes(changes: dict[str, Any]) -> list[str]:
    """Render variable change rows with sensitive-value masking."""
    lines: list[str] = []
    for key in sorted(changes):
        raw = str(changes[key])
        masked = mask_sensitive_value(str(key), raw)
        display = masked if masked != raw else _truncate_text(raw, max_len=_HEADER_VALUE_MAX)
        lines.append(f"    {key} → {display}")
    return lines


def _mask_console_log_message(message: str) -> str:
    """Redact secrets in one console log line (JSON, form, or key=value text)."""
    text = _redact_response_body(message, "text")
    text = _redact_form_urlencoded_body(text)

    def _replace(match: re.Match[str]) -> str:
        prefix, key, value = match.group(1), match.group(2), match.group(3)
        masked = mask_sensitive_value(key, value)
        if masked != value:
            return f"{prefix}{key}={REDACTED_PLACEHOLDER}"
        return match.group(0)

    return _CONSOLE_KV_RE.sub(_replace, text)


def _unresolved_variable_lines(
    *,
    env_id: int | None,
    request_id: int,
    url: str,
    headers: list[Any] | None,
    body: str | None,
    params: list[Any] | None,
    pre_request_script: str | None = None,
    variables: dict[str, str] | None = None,
) -> list[str]:
    """List ``{{var}}`` placeholders that remain after substitution."""
    import services.environment_service as environment_service_module
    from services.environment_service import EnvironmentService

    if variables is None:
        variables = EnvironmentService.build_combined_variable_map(env_id, request_id)
    texts: list[str] = [url]
    if body:
        texts.append(body)
    if isinstance(headers, list):
        for row in headers:
            if isinstance(row, dict):
                texts.append(str(row.get("key", "")))
                texts.append(str(row.get("value", "")))
    if isinstance(params, list):
        for row in params:
            if isinstance(row, dict):
                texts.append(str(row.get("key", "")))
                texts.append(str(row.get("value", "")))
    script_keys = _script_assigned_variable_keys(pre_request_script)
    unresolved: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if "{{" not in text:
            continue
        for match in environment_service_module._VAR_PATTERN.finditer(text):
            token = match.group(0)
            key = match.group(1).strip()
            if key in seen:
                continue
            substituted = EnvironmentService.substitute(token, variables)
            if substituted == token and key not in script_keys:
                seen.add(key)
                unresolved.append(key)
    if not unresolved:
        return []
    return [f"  Unresolved: {', '.join(unresolved)}"]


def _scope_variable_lines(
    env_id: int | None,
    request_id: int,
    *,
    details: dict[str, Any] | None = None,
) -> list[str]:
    """Build resolved in-scope variable rows for request/active_tab scopes."""
    from services.environment_service import EnvironmentService

    if details is None:
        details = EnvironmentService.build_combined_variable_detail_map(env_id, request_id)
    if not details:
        return []
    env_secret_keys: set[str] = set()
    if env_id is not None:
        env_row = EnvironmentService.get_environment(env_id)
        if env_row is not None:
            env_secret_keys = _secret_keys_from_variable_rows(
                env_row.values if isinstance(env_row.values, list) else None
            )
    coll_secret_by_id = _collection_secret_keys_by_id(details)
    lines: list[str] = []
    for key in sorted(details):
        detail = details[key]
        if not isinstance(detail, dict):
            continue
        value = str(detail.get("value", ""))
        source = str(detail.get("source", ""))
        source_id = detail.get("source_id")
        if "{{" in value:
            display = value
        elif (
            (source == "environment" and key in env_secret_keys)
            or (
                source == "collection"
                and isinstance(source_id, int)
                and key in coll_secret_by_id.get(source_id, set())
            )
            or _key_is_sensitive(key)
        ):
            display = SECRET_PLACEHOLDER
        else:
            display = _truncate_text(value, max_len=_HEADER_VALUE_MAX)
        lines.append(f"  {key} = {display} ({source})")
    return lines


_HISTORY_DATE_RE = re.compile(r"\b(since|until):(\d{4}-\d{2}-\d{2})\b")


def _parse_history_search(search: str) -> tuple[str, date | None, date | None]:
    """Split ``since:`` / ``until:`` date tokens from a history search string."""
    since: date | None = None
    until: date | None = None
    remainder = search

    def _replace(match: re.Match[str]) -> str:
        nonlocal since, until
        kind = match.group(1)
        raw = match.group(2)
        try:
            parsed = date.fromisoformat(raw)
        except ValueError:
            return match.group(0)
        if kind == "since":
            since = parsed
        else:
            until = parsed
        return ""

    remainder = _HISTORY_DATE_RE.sub(_replace, remainder)
    return remainder.strip(), since, until
