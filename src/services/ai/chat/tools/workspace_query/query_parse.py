"""Fielded query parser for complex workspace search."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_FIELD_OPS = frozenset({"in", "method", "path", "lang", "format", "has", "missing", "resolved"})
_IN_BUCKETS = frozenset(
    {"url", "body", "header", "script", "auth", "params", "assert", "env", "local", "name"}
)
_HAS_KEYS = frozenset({"test", "assert", "auth", "unresolved"})
_TOKEN_RE = re.compile(
    r'"(?P<phrase>[^"]*)"'
    r"|(?P<op>[a-zA-Z_]+):(?P<val>\S+)"
    r"|(?P<or>\bOR\b)"
    r"|(?P<neg>-(?P<negterm>\S+))"
    r"|(?P<bare>\S+)"
)


def _normalize_in_bucket(raw: str) -> str | None:
    """Map an ``in:`` value to a canonical bucket name."""
    key = raw.casefold()
    if key in {"headers", "header"}:
        return "header"
    if key in {"assertions", "assertion", "assert"}:
        return "assert"
    if key in {"params", "param"}:
        return "params"
    if key in _IN_BUCKETS:
        return key
    return None


@dataclass
class FieldedQuery:
    """Parsed fielded search query."""

    bare_tokens: list[str] = field(default_factory=list)
    or_groups: list[list[str]] = field(default_factory=list)
    exclude_tokens: list[str] = field(default_factory=list)
    in_buckets: set[str] = field(default_factory=set)
    method: str | None = None
    path_prefix: str | None = None
    lang: str | None = None
    module_format: str | None = None
    has: set[str] = field(default_factory=set)
    missing: set[str] = field(default_factory=set)
    resolved: bool = False
    phrases: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def text_tokens(self) -> list[str]:
        """Casefolded tokens used for AND text matching (bare + phrases)."""
        out = [t.casefold() for t in self.bare_tokens]
        out.extend(p.casefold() for p in self.phrases)
        return out

    @property
    def has_field_constraints(self) -> bool:
        """True when any structural operator is present."""
        return bool(
            self.in_buckets
            or self.method
            or self.path_prefix
            or self.lang
            or self.module_format
            or self.has
            or self.missing
            or self.resolved
            or self.or_groups
            or self.exclude_tokens
            or self.phrases
        )


def parse_fielded_query(needle: str) -> FieldedQuery:
    """Parse fielded operators from *needle*; unknown ops set ``error``."""
    q = FieldedQuery()
    text = needle.strip()
    if not text:
        return q

    # Flatten to a sequence of semantic pieces first.
    pieces: list[tuple[str, str]] = []
    for match in _TOKEN_RE.finditer(text):
        if match.group("phrase") is not None:
            pieces.append(("phrase", match.group("phrase").strip()))
        elif match.group("or"):
            pieces.append(("or", "OR"))
        elif match.group("neg"):
            pieces.append(("neg", match.group("negterm")))
        elif match.group("op"):
            pieces.append(("op", f"{match.group('op')}:{match.group('val')}"))
        elif match.group("bare"):
            pieces.append(("bare", match.group("bare")))

    i = 0
    while i < len(pieces):
        kind, val = pieces[i]
        if kind == "phrase":
            if val:
                q.phrases.append(val)
            i += 1
            continue
        if kind == "neg":
            q.exclude_tokens.append(val.casefold())
            i += 1
            continue
        if kind == "op":
            op, _, raw_val = val.partition(":")
            op_l = op.casefold()
            if op_l not in _FIELD_OPS:
                q.error = (
                    f"Unknown search operator `{op_l}:`. Valid: {', '.join(sorted(_FIELD_OPS))}."
                )
                return q
            if op_l == "in":
                bucket = _normalize_in_bucket(raw_val)
                if bucket is None:
                    q.error = f"Unknown in: bucket `{raw_val}`."
                    return q
                q.in_buckets.add(bucket)
            elif op_l == "method":
                q.method = raw_val.upper()
            elif op_l == "path":
                q.path_prefix = raw_val
            elif op_l == "lang":
                q.lang = raw_val.casefold()
            elif op_l == "format":
                q.module_format = raw_val.casefold()
            elif op_l == "has":
                key = raw_val.casefold()
                if key not in _HAS_KEYS:
                    q.error = f"Unknown has: value `{raw_val}`."
                    return q
                q.has.add(key)
            elif op_l == "missing":
                key = raw_val.casefold()
                if key not in _HAS_KEYS:
                    q.error = f"Unknown missing: value `{raw_val}`."
                    return q
                q.missing.add(key)
            elif op_l == "resolved":
                q.resolved = raw_val.casefold() in {"1", "true", "yes"}
            i += 1
            continue
        if kind == "or":
            # Combine previous bare/phrase with next bare/phrase into an OR group.
            left: str | None = None
            if q.bare_tokens:
                left = q.bare_tokens.pop()
            elif q.phrases:
                left = q.phrases.pop()
            if left is None or i + 1 >= len(pieces):
                q.error = "OR requires terms on both sides (e.g. foo OR bar)."
                return q
            nkind, nval = pieces[i + 1]
            if nkind not in {"bare", "phrase"} or not nval:
                q.error = "OR requires terms on both sides (e.g. foo OR bar)."
                return q
            q.or_groups.append([left.casefold(), nval.casefold()])
            i += 2
            continue
        # bare
        q.bare_tokens.append(val)
        i += 1

    return q


def hay_matches_fielded(hay: str, query: FieldedQuery) -> bool:
    """Return True when *hay* satisfies bare/phrase AND, OR groups, and excludes."""
    folded = hay.casefold()
    for excl in query.exclude_tokens:
        if excl in folded:
            return False
    for token in query.text_tokens:
        if token not in folded:
            return False
    return all(any(term in folded for term in group) for group in query.or_groups)
