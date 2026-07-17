"""Parser for raw text and URL imports.

Attempts to auto-detect the content type (OpenAPI, WSDL, Postman JSON,
cURL, or plain URL) and delegates to the appropriate specialised parser.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from urllib.error import URLError

from .curl_parser import is_curl, parse_curl
from .models import ImportResult, ParsedCollection, ParsedRequest
from .postman_parser import parse_json_text

logger = logging.getLogger(__name__)

# Simple heuristic: looks like a URL?
_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


def try_parse_spec_text(text: str) -> ImportResult | None:
    """Try OpenAPI then WSDL parsers; return None when neither matches."""
    from services.import_parser.openapi import load_openapi_text
    from services.import_parser.wsdl import load_wsdl_text

    result = load_openapi_text(text)
    if result is not None:
        return result
    return load_wsdl_text(text)


def parse_raw_text(text: str) -> ImportResult:
    """Auto-detect and parse raw text input.

    Detection order:
    1. cURL command
    2. Lone URL → fetch and parse (OpenAPI / WSDL / Postman / fallback GET)
    3. OpenAPI or WSDL document body
    4. Postman JSON
    5. Error
    """
    stripped = text.strip()
    if not stripped:
        return ImportResult(collections=[], environments=[], errors=["Empty input"])

    # 1. cURL
    if is_curl(stripped):
        return parse_curl(stripped)

    # 2. Lone URL — fetch (do not wrap as a bare GET without fetching)
    if _URL_RE.match(stripped):
        return fetch_and_parse_url(stripped)

    # 3. OpenAPI / WSDL
    spec = try_parse_spec_text(stripped)
    if spec is not None:
        return spec

    # 4. JSON (Postman)
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(stripped)
            return parse_json_text(stripped)
        except json.JSONDecodeError:
            pass

    return ImportResult(
        collections=[],
        environments=[],
        errors=["Could not detect format — expected cURL, OpenAPI, WSDL, JSON, or URL"],
    )


def fetch_and_parse_url(url: str) -> ImportResult:
    """HTTP GET the *url* and parse the response body.

    Tries OpenAPI, WSDL, then Postman JSON. Falls back to importing the
    URL as a single GET request when no structured format is detected.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Postmark/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except (URLError, OSError, ValueError) as exc:
        return ImportResult(
            collections=[],
            environments=[],
            errors=[f"Failed to fetch URL: {exc}"],
        )

    spec = try_parse_spec_text(body)
    if spec is not None:
        if spec.get("collections") or spec.get("environments"):
            return spec
        if spec.get("errors"):
            return spec

    try:
        json.loads(body)
        result = parse_json_text(body)
        if result.get("collections") or result.get("environments"):
            return result
    except json.JSONDecodeError:
        pass

    return _url_to_request(url)


def _url_to_request(url: str) -> ImportResult:
    """Wrap a plain URL as a single GET request inside a collection."""
    request = ParsedRequest(
        type="request",
        name=f"GET {url}",
        method="GET",
        url=url,
    )
    collection = ParsedCollection(
        name="URL Import",
        items=[request],
    )
    return ImportResult(collections=[collection], environments=[], errors=[])
