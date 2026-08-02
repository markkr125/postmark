"""Extract OpenAPI examples into saved-response rows for imported requests.

OpenAPI 3 documents commonly carry named examples on request and response
media types (``content.<mime>.examples.Ex1.value``). The first request example
fills the request body (see ``mapping._request_body``); everything here maps
the *rest* of the document's examples onto ``ParsedSavedResponse`` rows so
imported collections keep the spec's documented request/response examples.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

from services.import_parser.models import ParsedSavedResponse
from services.import_parser.openapi.resolve import resolve_ref


def _iter_named_examples(
    doc: dict[str, Any],
    media: dict[str, Any],
    warnings: list[str],
) -> list[tuple[str, str | None, Any]]:
    """Return ``(name, summary, value)`` for a media type object's examples."""
    if "example" in media:
        return [("Example", None, media.get("example"))]
    examples = media.get("examples")
    if not isinstance(examples, dict):
        return []
    out: list[tuple[str, str | None, Any]] = []
    for raw_name, raw in examples.items():
        ex = resolve_ref(doc, raw, warnings) if isinstance(raw, dict) else raw
        if isinstance(ex, dict) and "value" in ex:
            summary = ex.get("summary")
            out.append(
                (
                    str(raw_name),
                    str(summary).strip() if summary else None,
                    ex.get("value"),
                )
            )
    return out


def _example_body_text(value: Any, mime: str) -> str:
    """Serialize an example value for storage (YAML dates → ISO strings)."""
    if isinstance(value, str):
        return value
    if "json" in mime:
        return json.dumps(value, indent=2, default=str)
    return str(value)


def _mime_language(mime: str) -> str:
    """Map a media type to a preview language."""
    if "json" in mime:
        return "json"
    if "xml" in mime:
        return "xml"
    if "html" in mime:
        return "html"
    return "text"


def _sniff_body_language(body: str) -> str:
    """Guess syntax-highlight language from stored body text."""
    text = (body or "").strip()
    if not text:
        return "text"
    if text[0] in ("{", "["):
        try:
            json.loads(text)
            return "json"
        except (json.JSONDecodeError, ValueError):
            pass
    if text.startswith("<"):
        return "xml"
    return "text"


def request_snapshot(
    method: str,
    url: str,
    headers: list[dict[str, Any]],
    body: str | None,
    body_mode: str | None,
) -> dict[str, Any]:
    """Build a Postman-shaped request snapshot for saved-response examples."""
    snapshot: dict[str, Any] = {
        "method": method,
        "url": {"raw": url},
        "header": [
            {"key": str(h.get("key") or ""), "value": str(h.get("value") or "")}
            for h in headers
            if isinstance(h, dict) and str(h.get("key") or "").strip()
        ],
    }
    if body:
        body_obj: dict[str, Any] = {"mode": body_mode or "raw", "raw": body}
        body_obj["options"] = {"raw": {"language": _sniff_body_language(body)}}
        snapshot["body"] = body_obj
    return snapshot


def _status_phrase(code: int | None) -> str | None:
    """Return the HTTP reason phrase for *code*, when known."""
    if code is None:
        return None
    try:
        return HTTPStatus(code).phrase
    except ValueError:
        return None


def _unique_name(
    base: str,
    code_key: str,
    mime: str,
    seen: set[str],
) -> str:
    """Return a collision-free example name within one operation."""
    if base not in seen:
        seen.add(base)
        return base
    with_code = f"{base} ({code_key})"
    if with_code not in seen:
        seen.add(with_code)
        return with_code
    short = "json" if "json" in mime else ("xml" if "xml" in mime else mime.rsplit("/", 1)[-1][:10])
    name = f"{base} ({code_key}, {short})"
    counter = 2
    while name in seen:
        name = f"{base} ({code_key}, {short} {counter})"
        counter += 1
    seen.add(name)
    return name


def _sorted_media(content: dict[str, Any]) -> list[tuple[str, Any]]:
    """Return content entries, JSON first, so one example per name wins."""

    def rank(item: tuple[str, Any]) -> int:
        mime = str(item[0])
        if "json" in mime:
            return 0
        if "xml" in mime:
            return 1
        return 2

    return sorted(content.items(), key=rank)


def saved_responses_from_operation(
    doc: dict[str, Any],
    operation: dict[str, Any],
    snapshot: dict[str, Any],
    warnings: list[str],
) -> list[ParsedSavedResponse]:
    """Map an operation's response examples to saved responses."""
    out: list[ParsedSavedResponse] = []
    seen_names: set[str] = set()
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return out
    for code_key, raw_resp in responses.items():
        resp = resolve_ref(doc, raw_resp, warnings) if isinstance(raw_resp, dict) else raw_resp
        if not isinstance(resp, dict):
            continue
        code = int(code_key) if str(code_key).isdigit() else None
        status = _status_phrase(code)
        # OpenAPI 3: content → media → example(s). One row per example name —
        # specs repeat the same named example on JSON and XML media.
        emitted_bases: set[str] = set()
        content = resp.get("content")
        if isinstance(content, dict):
            for mime, media in _sorted_media(content):
                if not isinstance(media, dict):
                    continue
                for ex_name, summary, value in _iter_named_examples(doc, media, warnings):
                    if value is None:
                        continue
                    base = summary or ex_name or f"Response {code or code_key}"
                    if base in emitted_bases:
                        continue
                    emitted_bases.add(base)
                    out.append(
                        ParsedSavedResponse(
                            name=_unique_name(base, str(code_key), str(mime), seen_names),
                            status=status,
                            code=code,
                            headers=[{"key": "Content-Type", "value": str(mime)}],
                            body=_example_body_text(value, str(mime)),
                            preview_language=_mime_language(str(mime)),
                            original_request=snapshot,
                        )
                    )
        # Swagger 2: examples: {<mime>: <payload>}
        s2_examples = resp.get("examples")
        if isinstance(s2_examples, dict):
            for mime, value in s2_examples.items():
                if value is None:
                    continue
                base = f"Response {code or code_key}"
                out.append(
                    ParsedSavedResponse(
                        name=_unique_name(base, str(mime), str(mime), seen_names),
                        status=status,
                        code=code,
                        headers=[{"key": "Content-Type", "value": str(mime)}],
                        body=_example_body_text(value, str(mime)),
                        preview_language=_mime_language(str(mime)),
                        original_request=snapshot,
                    )
                )
    return out


def extra_request_examples(
    doc: dict[str, Any],
    operation: dict[str, Any],
    method: str,
    url: str,
    headers: list[dict[str, Any]],
    warnings: list[str],
) -> list[ParsedSavedResponse]:
    """Keep named request examples beyond the first as saved request variants.

    The first example already fills the request body; additional named examples
    (``Ex2``, …) become saved responses with an empty response body whose
    ``original_request`` snapshot carries that variant's payload.
    """
    body = operation.get("requestBody")
    body = resolve_ref(doc, body, warnings) if isinstance(body, dict) else body
    if not isinstance(body, dict):
        return []
    content = body.get("content")
    if not isinstance(content, dict):
        return []
    out: list[ParsedSavedResponse] = []
    for mime in ("application/json", "application/xml", "text/plain"):
        media = content.get(mime)
        if not isinstance(media, dict):
            continue
        examples = _iter_named_examples(doc, media, warnings)
        for ex_name, summary, value in examples[1:]:
            if value is None:
                continue
            body_text = _example_body_text(value, mime)
            variant_snapshot = request_snapshot(method, url, headers, body_text, "raw")
            out.append(
                ParsedSavedResponse(
                    name=f"{summary or ex_name} — request",
                    status=None,
                    code=None,
                    headers=[{"key": "Content-Type", "value": mime}],
                    body=None,
                    preview_language=None,
                    original_request=variant_snapshot,
                )
            )
        break
    return out


__all__ = ["extra_request_examples", "request_snapshot", "saved_responses_from_operation"]
