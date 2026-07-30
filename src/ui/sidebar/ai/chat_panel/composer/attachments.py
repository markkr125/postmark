"""Compose the prompt text sent to the agent when files are attached."""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from services.ai.chat.attachments.models import (
    markdown_name_for,
    uploaded_uri,
    uri_document_name,
)

ATTACHMENT_HEADER = "Attached files:"

# Prompts written before attachments were copied into the session directory named
# absolute paths under this header instead of handles.
LEGACY_ATTACHMENT_HEADER = "Attached files (absolute paths):"


class PromptAttachment(NamedTuple):
    """One attachment parsed back out of a composed prompt."""

    name: str
    reference: str


# Non-breaking space variants found in trailers re-saved through edit paths.
_TRAILER_SPACE_VARIANTS = ("\u00a0", "\u202f", "\u2007", "\u2009")
_HANDLE_PREFIX = re.compile(r"^(doc:\d+)\s+(.+)$")


def _normalize_trailer_spaces(line: str) -> str:
    """Return *line* with exotic space variants folded to plain spaces."""
    for variant in _TRAILER_SPACE_VARIANTS:
        line = line.replace(variant, " ")
    return line


def compose_prompt_with_attachments(text: str, attachments: list[str]) -> str:
    """Return *text* with attached documents listed by their uploaded URI.

    Only the URI and file name travel in the prompt. The absolute path is
    deliberately withheld: it would be persisted in the transcript and sent to the
    provider, and a long path is exactly what models mangle when they have to
    repeat it as a tool argument.
    """
    paths = [path.strip() for path in attachments if path.strip()]
    if not paths:
        return text
    rows = [
        PromptAttachment(
            Path(path).name,
            uploaded_uri(markdown_name_for(Path(path).name)),
        )
        for path in paths
    ]
    return compose_prompt_with_prompt_attachments(text, rows)


def compose_prompt_with_prompt_attachments(
    text: str,
    attachments: list[PromptAttachment],
) -> str:
    """Return *text* with already-resolved attachment name/reference pairs.

    Used when re-saving an edited user message: the trailer is lifted into chips
    for editing, then written back with the same URIs (no path recomputation).
    """
    if not attachments:
        return text
    rows = [f"- {att.name} -> {att.reference}" for att in attachments]
    block = "\n".join([ATTACHMENT_HEADER, *rows])
    return f"{text}\n\n{block}" if text else block


def split_prompt_attachments(text: str) -> tuple[str, list[PromptAttachment]]:
    """Split a composed prompt into its body and trailing attachment list.

    The attachment block is only recognised when it is the composed trailer — a
    header line followed exclusively by bullet rows to the end of the message.
    Anything else is returned untouched so a prompt that merely mentions the
    header phrase is never mangled.

    Old transcripts drifted: trailers written or re-saved through other paths
    carry non-breaking spaces around the header, dash, or arrow, and the
    handle era listed ``- doc:N <name>`` without an arrow. Matching is done on
    a whitespace-normalized copy while the body is sliced from the original
    text, so edit/fork round-trips the prompt byte-for-byte.
    """
    lines = (text or "").splitlines()
    normalized = [_normalize_trailer_spaces(line) for line in lines]
    start = next(
        (
            index
            for index, line in enumerate(normalized)
            if line.strip() in (ATTACHMENT_HEADER, LEGACY_ATTACHMENT_HEADER)
        ),
        None,
    )
    if start is None:
        return text, []
    trailing = [line.strip() for line in normalized[start + 1 :] if line.strip()]
    if not trailing or not all(line.startswith("- ") for line in trailing):
        return text, []
    attachments: list[PromptAttachment] = []
    for line in trailing:
        entry = line[2:].strip()
        if not entry:
            continue
        if " -> " in entry:
            name, reference = entry.split(" -> ", 1)
            attachments.append(PromptAttachment(name.strip(), reference.strip()))
            continue
        handle = _HANDLE_PREFIX.match(entry)
        if handle is not None:
            # Handle era (``- doc:1 report.pdf``): display the name, keep the
            # raw entry as the reference so index resolution still works.
            attachments.append(PromptAttachment(handle.group(2).strip(), entry))
            continue
        attachments.append(PromptAttachment(Path(entry).name, entry))
    if not attachments:
        return text, []
    body = "\n".join(lines[:start]).rstrip("\n")
    return body, attachments


def attachment_sizes_from_sources(paths: list[str]) -> dict[str, int]:
    """Map each source's uploaded URI to its byte size, for just-sent prompts."""
    sizes: dict[str, int] = {}
    for path in paths:
        reference = uploaded_uri(markdown_name_for(Path(path).name))
        try:
            sizes[reference] = Path(path).stat().st_size
        except OSError:
            continue
    return sizes


def attachment_sizes_from_session(session_id: str) -> dict[str, int]:
    """Map stored attachment references to byte sizes for transcript restores.

    Both the uploaded URI and the original source path are keyed so legacy
    prompts that carried absolute paths still resolve.
    """
    if not session_id:
        return {}
    from services.ai.chat.attachments.store import list_attachments

    sizes: dict[str, int] = {}
    for entry in list_attachments(session_id):
        size = entry.get("size_bytes")
        if not isinstance(size, int):
            continue
        uri = str(entry.get("uri") or "")
        if uri:
            sizes[uri] = size
        source = str(entry.get("source_path") or "")
        if source:
            sizes[source] = size
    return sizes


def attachment_references_from_prompt(text: str) -> list[str]:
    """Return the attachment references listed in a composed prompt.

    Uploads come back as ``postmark://uploaded/<name>.md``; prompts from before
    uploads were stored come back as the absolute paths they carried, so old
    transcripts still resolve.
    """
    _body, attachments = split_prompt_attachments(text)
    references: list[str] = []
    for attachment in attachments:
        document = uri_document_name(attachment.reference)
        references.append(uploaded_uri(document) if document else attachment.reference)
    return references


def attachment_paths_from_prompt(text: str) -> list[str]:
    """Return only the path-style references in a prompt.

    Handles resolve against the stored index instead, so passing them on as if
    they were paths would just produce a missing-file error.
    """
    return [ref for ref in attachment_references_from_prompt(text) if "/" in ref]


__all__ = [
    "ATTACHMENT_HEADER",
    "LEGACY_ATTACHMENT_HEADER",
    "PromptAttachment",
    "attachment_paths_from_prompt",
    "attachment_references_from_prompt",
    "attachment_sizes_from_session",
    "attachment_sizes_from_sources",
    "compose_prompt_with_attachments",
    "compose_prompt_with_prompt_attachments",
    "split_prompt_attachments",
]
