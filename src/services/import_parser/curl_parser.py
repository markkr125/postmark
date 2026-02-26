"""Parser for cURL commands.

Extracts HTTP method, URL, headers, body, and auth from cURL command
strings.  Handles common flags: ``-X``, ``-H``, ``-d``, ``--data``,
``--data-raw``, ``--data-binary``, ``-u``, ``-A``, ``--compressed``.

Exotic flags are silently ignored.
"""

from __future__ import annotations

import json
import logging
import re
import shlex
from typing import Any

from .models import ImportResult, ParsedCollection, ParsedRequest

logger = logging.getLogger(__name__)

# Regex to detect one or more cURL commands in pasted text.
_CURL_RE = re.compile(r"(?:^|\n)\s*curl\s", re.IGNORECASE)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def is_curl(text: str) -> bool:
    """Return ``True`` if *text* looks like it contains a cURL command."""
    return bool(_CURL_RE.search(text))


def parse_curl(text: str) -> ImportResult:
    """Parse one or more cURL commands from *text*.

    Returns an ``ImportResult`` with a single collection containing the
    parsed requests, or errors.
    """
    commands = _split_curl_commands(text)
    if not commands:
        return ImportResult(
            collections=[],
            environments=[],
            errors=["No cURL commands found in the provided text"],
        )

    requests: list[ParsedRequest] = []
    errors: list[str] = []

    for idx, cmd in enumerate(commands, 1):
        try:
            req = _parse_single_curl(cmd)
            requests.append(req)
        except Exception as exc:
            errors.append(f"cURL command #{idx}: {exc}")

    if not requests:
        return ImportResult(collections=[], environments=[], errors=errors)

    # Wrap requests in a collection so they have a parent folder.
    name = requests[0].get("name", "cURL Import") if len(requests) == 1 else "cURL Import"
    collection = ParsedCollection(
        name=name,
        items=list(requests),
    )
    return ImportResult(collections=[collection], environments=[], errors=errors)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _split_curl_commands(text: str) -> list[str]:
    """Split a block of text into individual cURL command strings.

    Handles line-continuation backslashes and semicolon-separated
    commands.
    """
    # Normalise line continuations
    text = text.replace("\\\n", " ").replace("\\\r\n", " ")

    # Split on lines that start with "curl"
    chunks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^curl\s", stripped, re.IGNORECASE):
            if current:
                chunks.append(" ".join(current))
            current = [stripped]
        elif current:
            current.append(stripped)
    if current:
        chunks.append(" ".join(current))

    return [c for c in chunks if c.strip()]


def _parse_single_curl(cmd: str) -> ParsedRequest:
    """Parse a single cURL command string into a ``ParsedRequest``."""
    try:
        tokens = shlex.split(cmd)
    except ValueError as exc:
        raise ValueError(f"Malformed cURL command: {exc}") from exc

    if not tokens or tokens[0].lower() != "curl":
        raise ValueError("Not a cURL command")

    method: str | None = None
    url: str | None = None
    headers: list[dict[str, Any]] = []
    body: str | None = None
    auth_user: str | None = None
    user_agent: str | None = None

    i = 1
    while i < len(tokens):
        token = tokens[i]

        if token in ("-X", "--request"):
            i += 1
            method = tokens[i].upper() if i < len(tokens) else None
        elif token in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                hdr = _parse_header(tokens[i])
                if hdr:
                    headers.append(hdr)
        elif token in ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii"):
            i += 1
            if i < len(tokens):
                body = tokens[i]
        elif token in ("-u", "--user"):
            i += 1
            if i < len(tokens):
                auth_user = tokens[i]
        elif token in ("-A", "--user-agent"):
            i += 1
            if i < len(tokens):
                user_agent = tokens[i]
        elif (
            token == "--compressed"
            or token in ("-k", "--insecure")
            or token in ("-L", "--location")
            or token in ("-s", "--silent")
            or token in ("-v", "--verbose")
            or token in ("-i", "--include")
        ):
            pass  # Silently ignore
        elif not token.startswith("-") and url is None:
            url = token
        else:
            # Unknown flag — skip its argument if it looks like it takes one
            logger.debug("Ignoring unknown cURL flag: %s", token)

        i += 1

    if not url:
        raise ValueError("No URL found in cURL command")

    # Infer method from body presence
    if method is None:
        method = "POST" if body else "GET"

    # Add User-Agent as a header if specified
    if user_agent:
        headers.append(
            {"key": "User-Agent", "value": user_agent, "disabled": False, "type": "text"}
        )

    # Build auth dict
    auth: dict[str, Any] | None = None
    if auth_user:
        parts = auth_user.split(":", 1)
        auth = {
            "type": "basic",
            "basic": [
                {"key": "username", "value": parts[0], "type": "string"},
                {"key": "password", "value": parts[1] if len(parts) > 1 else "", "type": "string"},
            ],
        }

    # Detect body mode
    body_mode: str | None = None
    body_options: dict[str, Any] | None = None
    if body is not None:
        body_mode = "raw"
        # Try to detect JSON
        try:
            json.loads(body)
            body_options = {"raw": {"language": "json"}}
        except (json.JSONDecodeError, ValueError):
            body_options = {"raw": {"language": "text"}}

    # Derive a name from the URL
    name = _derive_name(url, method)

    return ParsedRequest(
        type="request",
        name=name,
        method=method,
        url=url,
        headers=headers if headers else None,
        body=body,
        body_mode=body_mode,
        body_options=body_options,
        auth=auth,
    )


def _parse_header(header_str: str) -> dict[str, Any] | None:
    """Parse a ``Key: Value`` header string."""
    if ":" not in header_str:
        return None
    key, _, value = header_str.partition(":")
    return {
        "key": key.strip(),
        "value": value.strip(),
        "disabled": False,
        "type": "text",
    }


def _derive_name(url: str, method: str) -> str:
    """Derive a human-friendly request name from the URL and method.

    Extracts the last non-empty path segment and combines it with the
    method, e.g. ``"GET /users"`` or ``"POST /login"``.
    """
    # Strip protocol and query string
    clean = re.sub(r"^https?://[^/]*", "", url)
    clean = clean.split("?")[0].rstrip("/")

    if clean:
        # Take last two path segments for context
        segments = [s for s in clean.split("/") if s]
        path = (
            "/" + "/".join(segments[-2:])
            if len(segments) > 1
            else "/" + segments[-1]
            if segments
            else "/"
        )
    else:
        path = "/"

    return f"{method} {path}"
