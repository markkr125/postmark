"""Compose the prompt text sent to the agent when files are attached."""

from __future__ import annotations

from pathlib import Path

from services.ai.chat.attachments.models import (
    markdown_name_for,
    uploaded_uri,
    uri_document_name,
)

ATTACHMENT_HEADER = "Attached files:"

# Prompts written before attachments were copied into the session directory named
# absolute paths under this header instead of handles.
LEGACY_ATTACHMENT_HEADER = "Attached files (absolute paths):"


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
        f"- {Path(path).name} -> {uploaded_uri(markdown_name_for(Path(path).name))}"
        for path in paths
    ]
    block = "\n".join([ATTACHMENT_HEADER, *rows])
    return f"{text}\n\n{block}" if text else block


def attachment_references_from_prompt(text: str) -> list[str]:
    """Return the attachment references listed in a composed prompt.

    Uploads come back as ``postmark://uploaded/<name>.md``; prompts from before
    uploads were stored come back as the absolute paths they carried, so old
    transcripts still resolve.
    """
    lines = (text or "").splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line in (ATTACHMENT_HEADER, LEGACY_ATTACHMENT_HEADER)
        ),
        None,
    )
    if start is None:
        return []
    references: list[str] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped.startswith("- "):
            break
        entry = stripped[2:].strip()
        if not entry:
            continue
        document = uri_document_name(entry)
        references.append(uploaded_uri(document) if document else entry)
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
    "attachment_paths_from_prompt",
    "attachment_references_from_prompt",
    "compose_prompt_with_attachments",
]
