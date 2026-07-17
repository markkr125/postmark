"""Guard against assistant messages that claim workspace writes which never happened.

The chat's final message is model-authored, so a turn that never ran a write tool
can still report ``"imported 4 collections"``. This module pairs that claim with
the turn's observed tool activity so an unbacked claim is flagged to the user.
"""

from __future__ import annotations

import re

_COUNT = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"

# Count fields emitted by an import observation; all-zero means nothing changed.
_COUNT_FIELDS = ("collections_imported", "requests_imported", "environments_imported")

# Past-tense completion claims only. Forward-looking ("I'll import", "you can
# import") and failure reports ("the import failed") must NOT match, or a
# read-only how-to answer would be flagged.
_CLAIM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:has|have|had)\s+been\s+imported\b", re.IGNORECASE),
    re.compile(r"\bI(?:'ve|\s+have)?\s+imported\b", re.IGNORECASE),
    re.compile(rf"\bimported\s+{_COUNT}\b", re.IGNORECASE),
    re.compile(
        rf"\b{_COUNT}\s+collections?\s+(?:were|was|have\s+been|has\s+been)\s+created\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bI(?:'ve|\s+have)?\s+created\b[^.\n]{0,60}\bcollection",
        re.IGNORECASE,
    ),
)

UNVERIFIED_WRITE_NOTE = (
    "⚠️ **No workspace change was actually made.** The message above reports an import "
    "or creation, but no write tool ran during this turn — nothing was imported or "
    "created."
)


def claims_workspace_write(content: str) -> bool:
    """Return True when *content* asserts a completed import or collection create."""
    text = content or ""
    return any(pattern.search(text) for pattern in _CLAIM_PATTERNS)


def observation_indicates_write(text: str) -> bool:
    """Return whether a write-tool observation reflects a real change.

    Two distinct failure shapes must not count as a write:

    * ``ok: false`` — the tool itself raised.
    * ``ok: true`` with every ``*_imported`` count at zero — ``ImportService``
      swallows fetch/parse failures into ``errors`` and still reports ``ok: true``,
      so an unreachable URL or unparseable spec looks successful apart from the
      zero counts.

    Any other shape counts as a write, so a real change is never reported to the
    user as fabricated.
    """
    body = text or ""
    for line in body.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("ok:"):
            if stripped == "ok: false":
                return False
            break
    counts = [
        int(match.group(1))
        for field in _COUNT_FIELDS
        if (match := re.search(rf"^{field}:\s*(\d+)\s*$", body, re.MULTILINE)) is not None
    ]
    return not (counts and not any(counts))


def unverified_write_note(content: str, *, write_observed: bool) -> str | None:
    """Return a warning note when a write is claimed but none was observed.

    Args:
        content: The assistant's final message text.
        write_observed: Whether a mutate/execute/import tool ran this turn.

    Returns:
        The note to append, or ``None`` when the claim is backed (or absent).
    """
    if write_observed:
        return None
    if not claims_workspace_write(content):
        return None
    return UNVERIFIED_WRITE_NOTE


__all__ = [
    "UNVERIFIED_WRITE_NOTE",
    "claims_workspace_write",
    "observation_indicates_write",
    "unverified_write_note",
]
