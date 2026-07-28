"""Schema and handle vocabulary for chat file attachments."""

from __future__ import annotations

import re
from typing import TypedDict

# Index file inside the session's disk directory, so attachments are removed with
# the session by the existing rmtree in ai_chat_repository.delete_session.
ATTACHMENT_INDEX_NAME = "attachments.json"
ATTACHMENT_DIR_NAME = "attachments"

HANDLE_PREFIX = "doc:"

# Uploaded documents are addressed by URI in prompts and tool calls.
UPLOADED_URI_PREFIX = "postmark://uploaded/"

# ``doc:2`` anywhere in a model-supplied string, so a handle is still found when
# the model wraps it in quotes or brackets.
_HANDLE = re.compile(rf"{HANDLE_PREFIX}\s*(\d+)")

# Anything outside this set becomes an underscore: spaces, brackets and quotes in a
# URI make it impossible to tell where the reference ends once a model has wrapped
# it in prose or a markdown link.
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

# The URI-safe name that follows the prefix; stops at the first character a name
# can never contain, so trailing prose or punctuation is ignored.
_URI_TAIL = re.compile(r"[A-Za-z0-9._-]+")


class StoredAttachment(TypedDict):
    """One attachment copied into the session's upload directory.

    ``source_path`` is kept only as a fallback for reading the original if the
    copy is ever missing; it is never shown to the model.
    """

    handle: str
    uri: str
    name: str
    markdown_name: str
    stored_path: str
    markdown_path: str
    images_dir: str
    source_path: str
    size_bytes: int
    sha256: str


def markdown_name_for(name: str) -> str:
    """Return the URI-safe ``.md`` file name an upload is converted to."""
    stem = _UNSAFE_NAME.sub("_", name.rsplit(".", 1)[0]).strip("_") or "document"
    return f"{stem}.md"


def uploaded_uri(markdown_name: str) -> str:
    """Return the ``postmark://uploaded/<name>.md`` identity for an upload."""
    return f"{UPLOADED_URI_PREFIX}{markdown_name}"


def uri_document_name(reference: str) -> str | None:
    """Return the ``<name>.md`` addressed by *reference*, or None when absent.

    Models wrap URIs in markdown links and trailing punctuation, so the tail is
    taken up to the first delimiter.
    """
    text = (reference or "").strip()
    marker = text.find(UPLOADED_URI_PREFIX)
    if marker < 0:
        return None
    tail = text[marker + len(UPLOADED_URI_PREFIX) :]
    name = _URI_TAIL.match(tail)
    return name.group(0) if name else None


def attachment_handle(ordinal: int) -> str:
    """Return the stable short handle for the *ordinal*-th attachment (1-based)."""
    return f"{HANDLE_PREFIX}{ordinal}"


def handle_ordinal(reference: str) -> int | None:
    """Return the 1-based ordinal named by *reference*, or None when absent."""
    match = _HANDLE.search(reference or "")
    return int(match.group(1)) if match else None


__all__ = [
    "ATTACHMENT_DIR_NAME",
    "ATTACHMENT_INDEX_NAME",
    "HANDLE_PREFIX",
    "UPLOADED_URI_PREFIX",
    "StoredAttachment",
    "attachment_handle",
    "handle_ordinal",
    "markdown_name_for",
    "uploaded_uri",
    "uri_document_name",
]
