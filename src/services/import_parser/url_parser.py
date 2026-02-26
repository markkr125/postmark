"""Parser for raw text and URL imports.

Attempts to auto-detect the content type (Postman JSON, cURL, or plain
URL) and delegates to the appropriate specialised parser.
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


def parse_raw_text(text: str) -> ImportResult:
    """Auto-detect and parse raw text input.

    Detection order:
    1. If it looks like a cURL command, parse with the cURL parser.
    2. If it parses as JSON, treat as a Postman collection/environment.
    3. If it looks like a URL, create a single GET request.
    4. Otherwise, return an error.
    """
    stripped = text.strip()
    if not stripped:
        return ImportResult(collections=[], environments=[], errors=["Empty input"])

    # 1. cURL
    if is_curl(stripped):
        return parse_curl(stripped)

    # 2. JSON
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(stripped)
            return parse_json_text(stripped)
        except json.JSONDecodeError:
            pass  # Fall through to URL check

    # 3. URL
    if _URL_RE.match(stripped):
        return _url_to_request(stripped)

    return ImportResult(
        collections=[],
        environments=[],
        errors=["Could not detect format — expected cURL, JSON, or URL"],
    )


def fetch_and_parse_url(url: str) -> ImportResult:
    """HTTP GET the *url* and parse the response body.

    If the response is JSON containing a Postman collection or
    environment, it is parsed accordingly.  Otherwise the URL is
    imported as a single GET request.
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

    # Try to parse as Postman JSON
    try:
        json.loads(body)
        result = parse_json_text(body)
        if result.get("collections") or result.get("environments"):
            return result
    except json.JSONDecodeError:
        pass

    # Fall back to importing the URL as a simple GET request
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
