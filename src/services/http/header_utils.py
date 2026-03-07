"""Shared header-parsing utilities for the HTTP service layer.

Provides a single ``parse_header_dict`` function used by
:mod:`http_service`, :mod:`snippet_generator`, and the import parser.
"""

from __future__ import annotations


def parse_header_dict(raw: str | None) -> dict[str, str]:
    """Parse a newline-separated ``Key: Value`` header string into a mapping.

    Each line should contain at least one colon.  Malformed lines
    (no colon) are silently skipped.  Leading/trailing whitespace on
    both key and value is stripped.

    Returns an empty dict when *raw* is ``None`` or empty.
    """
    if not raw:
        return {}

    headers: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip()] = value.strip()
    return headers
