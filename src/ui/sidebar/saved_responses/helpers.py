"""Helper functions for formatting saved response data."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def format_body_size(size_bytes: int) -> str:
    """Format response-body byte size as a compact label."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def detect_body_language(body: str) -> str | None:
    """Sniff a response body and guess its language from content."""
    import json

    text = body.strip()
    if not text:
        return None
    if text[0] in ("{", "["):
        try:
            json.loads(text)
            return "json"
        except (json.JSONDecodeError, ValueError):
            pass
    lower = text[:100].lower()
    if lower.startswith("<?xml"):
        return "xml"
    if lower.startswith("<!doctype html") or lower.startswith("<html"):
        return "html"
    return None


def try_pretty_json(text: str) -> str:
    """Attempt to pretty-print JSON; return original text on failure."""
    import json

    try:
        parsed = json.loads(text)
        return json.dumps(parsed, indent=4, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return text


def try_pretty_xml(text: str) -> str:
    """Attempt to pretty-print XML/HTML; return original text on failure."""
    try:
        import xml.dom.minidom

        dom = xml.dom.minidom.parseString(text)
        return dom.toprettyxml(indent="    ")
    except Exception:
        return text


def format_json_text(data: dict[str, Any], *, pretty: bool) -> str:
    """Serialize request snapshot data as compact or pretty JSON."""
    import json

    if pretty:
        return json.dumps(data, indent=4, ensure_ascii=False)
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def format_code_text(text: str, language: str, *, pretty: bool) -> str:
    """Format response text for the read-only code editors."""
    if not pretty or not text:
        return text
    if language == "json":
        return try_pretty_json(text)
    if language in {"xml", "html"}:
        return try_pretty_xml(text)
    pretty_json = try_pretty_json(text)
    if pretty_json != text:
        return pretty_json
    return try_pretty_xml(text)


def build_row_meta(item: Mapping[str, Any]) -> str:
    """Return a metadata summary line for a saved response list row."""
    meta_parts: list[str] = []
    if item["created_at"]:
        meta_parts.append(item["created_at"])
    if item["preview_language"]:
        meta_parts.append(item["preview_language"].upper())
    if item["body_size"]:
        meta_parts.append(format_body_size(item["body_size"]))
    return " \u00b7 ".join(meta_parts)


def format_headers(headers: Any) -> str:
    """Render headers as read-only text, or empty string if absent."""
    if not headers:
        return ""
    if isinstance(headers, dict):
        return "\n".join(f"{key}: {value}" for key, value in headers.items())
    if isinstance(headers, str):
        return headers
    return "\n".join(
        f"{header.get('key', '')}: {header.get('value', '')}"
        for header in headers
        if isinstance(header, dict)
    )
