"""Guard against assistant messages that claim workspace writes which never happened.

The chat's final message is model-authored, so a turn that never ran a write tool
can still report ``"imported 4 collections"``. This module pairs that claim with
the turn's observed tool activity so an unbacked claim is flagged to the user.
"""

from __future__ import annotations

import re

from services.ai.chat.mutation.auto_approve import is_mutate_or_execute_tool

_COUNT = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"

# Count fields emitted by an import observation; all-zero means nothing changed.
_COUNT_FIELDS = ("collections_imported", "requests_imported", "environments_imported")

# Only finish emits mutation_id; start/add_requests/status/discard must not count.
_DRAFT_TOOL = "postmark_collection_draft"
_MUTATION_ID_MARKER = "mutation_id:"

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

FABRICATED_LINK_NOTE = (
    "⚠️ **Removed a collection link that was not created in this turn.** The assistant "
    "referenced a collection that no tool produced here, so the link was stripped — it "
    "may point at an unrelated collection from earlier in this chat."
)

# Markdown link whose target is a collection deep-link, capturing the label and id.
_COLLECTION_LINK = re.compile(r"\[([^\]\n]*)\]\(postmark://collection/(\d+)[^)\n]*\)")
_BARE_COLLECTION_URI = re.compile(r"postmark://collection/(\d+)")


def collection_ids_in_observation(text: str) -> set[int]:
    """Return collection ids that an observation reports as really created."""
    if not observation_indicates_write(text or ""):
        return set()
    return {int(match) for match in _BARE_COLLECTION_URI.findall(text or "")}


def strip_unbacked_collection_links(content: str, produced_ids: set[int]) -> tuple[str, bool]:
    """Replace collection links the turn never created with their plain label.

    A fabricated ``postmark://collection/<id>`` is indistinguishable from a real
    one and can land on an unrelated collection, so the link is removed while the
    surrounding sentence is left intact.

    Returns:
        The cleaned text and whether anything was stripped.
    """
    text = content or ""
    stripped = False

    def _replace_link(match: re.Match[str]) -> str:
        nonlocal stripped
        if int(match.group(2)) in produced_ids:
            return match.group(0)
        stripped = True
        return match.group(1) or "the collection"

    text = _COLLECTION_LINK.sub(_replace_link, text)

    def _replace_bare(match: re.Match[str]) -> str:
        nonlocal stripped
        if int(match.group(1)) in produced_ids:
            return match.group(0)
        stripped = True
        return "(link removed)"

    text = _BARE_COLLECTION_URI.sub(_replace_bare, text)
    return text, stripped


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


def observation_records_write(tool_name: str, text: str) -> bool:
    """Return whether this tool observation should enter the write ledger.

    Uses :func:`is_mutate_or_execute_tool` as the single source of truth for
    which tools can write. For ``postmark_collection_draft``, only a finish
    observation (identified by the ``mutation_id:`` marker) counts — start /
    add_requests / status / discard must not, or a model claiming success after
    only staging would silence the unverified-write guard.
    """
    if not is_mutate_or_execute_tool(tool_name):
        return False
    body = text or ""
    if tool_name == _DRAFT_TOOL and _MUTATION_ID_MARKER not in body:
        return False
    return observation_indicates_write(body)


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
    "FABRICATED_LINK_NOTE",
    "UNVERIFIED_WRITE_NOTE",
    "claims_workspace_write",
    "collection_ids_in_observation",
    "observation_indicates_write",
    "observation_records_write",
    "strip_unbacked_collection_links",
    "unverified_write_note",
]
