"""String-level URL query parsing/building.

These helpers intentionally do NOT percent-encode or decode anything. Values
pass through verbatim so that ``{{variable}}`` placeholders (and any existing
percent-encoding) survive a round trip. Encoding for transport is left to the
HTTP client at send time.

``&``, ``=``, and ``#`` (fragment delimiter) are ignored inside ``{{…}}`` spans
so placeholders may contain those characters without being split.
"""

from __future__ import annotations

# Segment had no ``=`` (flag-style ``?verbose`` not ``?verbose=``).
QueryPair = tuple[str, str | None]


def _find_outside_mustache(text: str, ch: str, start: int = 0) -> int:
    """Return the index of *ch* at/after *start*, or ``-1``, ignoring ``{{…}}``."""
    depth = 0
    i = start
    n = len(text)
    while i < n:
        if i + 1 < n and text[i] == "{" and text[i + 1] == "{":
            depth += 1
            i += 2
            continue
        if i + 1 < n and text[i] == "}" and text[i + 1] == "}":
            depth = max(0, depth - 1)
            i += 2
            continue
        if depth == 0 and text[i] == ch:
            return i
        i += 1
    return -1


def _split_outside_mustache(text: str, ch: str) -> list[str]:
    """Split *text* on *ch* only outside ``{{…}}`` spans."""
    parts: list[str] = []
    start = 0
    while start <= len(text):
        idx = _find_outside_mustache(text, ch, start)
        if idx < 0:
            parts.append(text[start:])
            break
        parts.append(text[start:idx])
        start = idx + 1
    return parts


def split_url(url: str) -> tuple[str, str, str]:
    """Split *url* into ``(base, query, fragment)``.

    ``fragment`` includes its leading ``#`` (or is ``""``). ``query`` is the
    text between the first ``?`` and the fragment WITHOUT the leading ``?``.
    A ``#`` appearing before any ``?`` means there is no query. ``#`` inside
    ``{{…}}`` does not start a fragment.
    """
    frag_idx = _find_outside_mustache(url, "#")
    if frag_idx >= 0:
        before_frag = url[:frag_idx]
        fragment = url[frag_idx:]
    else:
        before_frag = url
        fragment = ""
    q_idx = _find_outside_mustache(before_frag, "?")
    if q_idx >= 0:
        base = before_frag[:q_idx]
        query = before_frag[q_idx + 1 :]
    else:
        base = before_frag
        query = ""
    return base, query, fragment


def url_has_query(url: str) -> bool:
    """Return True if *url* contains a ``?`` query segment (even if empty)."""
    frag_idx = _find_outside_mustache(url, "#")
    before_frag = url[:frag_idx] if frag_idx >= 0 else url
    return _find_outside_mustache(before_frag, "?") >= 0


def parse_query(url: str) -> list[QueryPair]:
    """Parse the query segment into ordered ``(key, value)`` pairs. No decoding.

    Empty ``&`` segments are dropped. The first ``=`` outside ``{{…}}`` splits
    key and value. A segment with no ``=`` yields ``(key, None)`` (flag-style).
    Empty-key segments are dropped.
    """
    _, query, _ = split_url(url)
    pairs: list[QueryPair] = []
    for segment in _split_outside_mustache(query, "&"):
        if segment == "":
            continue
        eq = _find_outside_mustache(segment, "=")
        if eq < 0:
            key = segment
            value: str | None = None
        else:
            key = segment[:eq]
            value = segment[eq + 1 :]
        if key == "":
            continue
        pairs.append((key, value))
    return pairs


def build_query(rows: list[dict]) -> str:
    """Join ENABLED, non-empty-key rows into a query string. No encoding.

    Rows with ``flag`` set emit the key only (no ``=``). Otherwise
    ``key=value`` is used; an empty value still emits the trailing ``=``.
    Returns ``""`` when no rows qualify.
    """
    parts: list[str] = []
    for row in rows:
        if not row.get("enabled", True):
            continue
        key = row.get("key", "")
        if key == "":
            continue
        if row.get("flag"):
            parts.append(key)
        else:
            parts.append(f"{key}={row.get('value', '')}")
    return "&".join(parts)


def build_url_with_query(url: str, rows: list[dict]) -> str:
    """Return *url* with its query rebuilt from *rows*; base + fragment kept verbatim.

    The ``?`` is added only when there is at least one enabled, non-empty row.
    """
    base, _, fragment = split_url(url)
    query = build_query(rows)
    if query:
        return f"{base}?{query}{fragment}"
    return f"{base}{fragment}"
