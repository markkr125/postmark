"""Copy chat attachments into the session directory and resolve them later.

Attachments used to be borrowed from wherever the user picked them, which made a
stored chat only as durable as the user's Downloads folder and forced the absolute
path through the model as a tool argument. Copies live beside the session on disk,
so they survive the original moving, are removed with the session, and let the
model refer to a document by a short ``doc:1`` handle it cannot mangle.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from base64 import b64decode
from pathlib import Path
from typing import cast
from uuid import uuid4

from database.data_paths import session_attachments_dir
from services.ai.chat.attachments.models import (
    ATTACHMENT_DIR_NAME,
    ATTACHMENT_INDEX_NAME,
    StoredAttachment,
    attachment_handle,
    handle_ordinal,
    markdown_name_for,
    uploaded_uri,
    uri_document_name,
)
from services.ai.chat.attachments.screenshots import clear_session_vision
from services.document_import.extract import extract_document, validate_document_path
from services.document_import.models import DocumentImportError, ExtractedDocument
from services.document_import.to_markdown import document_to_markdown

# Screenshots are OCR'd into the Markdown once at upload time.
MAX_UPLOAD_IMAGES = 40

logger = logging.getLogger(__name__)

_COPY_CHUNK = 1024 * 1024


def _session_dir(session_id: str) -> Path | None:
    """Return the session's disk directory, or None when *session_id* is unusable."""
    try:
        return session_attachments_dir(session_id)
    except (ValueError, AttributeError):
        return None


def _index_path(session_id: str) -> Path | None:
    """Return the attachment index path for *session_id*."""
    base = _session_dir(session_id)
    return None if base is None else base / ATTACHMENT_INDEX_NAME


def _read_index(session_id: str) -> list[StoredAttachment]:
    """Return the persisted attachment index, tolerating a missing or bad file."""
    path = _index_path(session_id)
    if path is None or not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Unreadable attachment index for session %s", session_id)
        return []
    if not isinstance(raw, list):
        return []
    return [
        cast(StoredAttachment, entry)
        for entry in raw
        if isinstance(entry, dict) and entry.get("stored_path")
    ]


def _write_index(session_id: str, entries: list[StoredAttachment]) -> None:
    """Persist *entries* atomically so a crash cannot leave a torn index."""
    path = _index_path(session_id)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    temp.replace(path)


def _copy_with_digest(source: Path, target: Path) -> tuple[int, str]:
    """Copy *source* to *target*, returning ``(size, sha256)``."""
    digest = hashlib.sha256()
    size = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f"{target.name}.part")
    with source.open("rb") as src, temp.open("wb") as dst:
        while chunk := src.read(_COPY_CHUNK):
            digest.update(chunk)
            size += len(chunk)
            dst.write(chunk)
    temp.replace(target)
    return size, digest.hexdigest()


def _unique_markdown_name(entries: list[StoredAttachment], name: str) -> str:
    """Return *name* made unique within the session, so URIs stay unambiguous."""
    taken = {str(entry.get("markdown_name") or "").lower() for entry in entries}
    if name.lower() not in taken:
        return name
    stem = name[: -len(".md")]
    for suffix in range(2, 100):
        candidate = f"{stem}-{suffix}.md"
        if candidate.lower() not in taken:
            return candidate
    return f"{stem}-{uuid4().hex[:6]}.md"


def _write_images(doc: ExtractedDocument, images_dir: Path) -> None:
    """Write each embedded screenshot as ``image-N.png`` beside the Markdown.

    The number matches the ``[image N]`` marker in the text, which is how a chunk
    knows which screenshots belong to it.
    """
    images_dir.mkdir(parents=True, exist_ok=True)
    for image in doc["images"]:
        data = image.get("data_b64") or ""
        if not data:
            continue
        try:
            (images_dir / f"image-{image['index'] + 1}.png").write_bytes(b64decode(data))
        except (OSError, ValueError):
            logger.exception("Could not store screenshot %s", image["index"] + 1)


def _write_markdown(source: Path, target: Path, images_dir: Path, display_name: str) -> bool:
    """Convert the stored copy to Markdown at *target*, reporting success.

    Screenshots are written to disk as-is. OCR is not run here: it is the fallback
    for models that cannot see images, so it is done at read time and only then.
    """
    try:
        doc = extract_document(str(source), max_images=MAX_UPLOAD_IMAGES, run_ocr=False)
        doc["source_name"] = display_name
        target.write_text(document_to_markdown(doc), encoding="utf-8")
        _write_images(doc, images_dir)
    except Exception:
        # Third-party parsers raise their own types on a malformed file; a bad
        # upload must not take the user's turn down with it.
        logger.exception("Could not convert attachment %s to Markdown", display_name)
        return False
    return True


def store_attachments(session_id: str, sources: list[str]) -> list[StoredAttachment]:
    """Copy *sources* into the session's attachment directory and index them.

    Files that fail validation are skipped and logged rather than aborting the
    turn, so one bad pick cannot swallow the user's message.

    Returns:
        Only the newly stored attachments, which are the ones this turn should
        deliver to the model.
    """
    if not session_id or not sources:
        return []
    base = _session_dir(session_id)
    if base is None:
        return []

    entries = _read_index(session_id)
    added: list[StoredAttachment] = []
    for source in sources:
        try:
            valid = validate_document_path(source)
        except DocumentImportError as exc:
            logger.warning("Skipped attachment %s: %s", source, exc.code)
            continue
        ordinal = len(entries) + 1
        target = base / ATTACHMENT_DIR_NAME / f"{ordinal:02d}{valid.suffix.lower()}"
        try:
            size, digest = _copy_with_digest(valid, target)
        except OSError:
            logger.exception("Failed to copy attachment %s", source)
            continue
        markdown_name = _unique_markdown_name(entries, markdown_name_for(valid.name))
        markdown_path = base / ATTACHMENT_DIR_NAME / markdown_name
        images_dir = markdown_path.with_suffix("") / "images"
        if not _write_markdown(target, markdown_path, images_dir, valid.name):
            continue
        entry: StoredAttachment = {
            "handle": attachment_handle(ordinal),
            "uri": uploaded_uri(markdown_name),
            "name": valid.name,
            "markdown_name": markdown_name,
            "stored_path": str(target),
            "markdown_path": str(markdown_path),
            "images_dir": str(images_dir),
            "source_path": str(valid),
            "size_bytes": size,
            "sha256": digest,
        }
        entries.append(entry)
        added.append(entry)
    if added:
        _write_index(session_id, entries)
    return added


def delete_session_attachments(session_id: str) -> None:
    """Remove every attachment copy for *session_id*."""
    clear_session_vision(session_id)
    base = _session_dir(session_id)
    if base is not None and base.is_dir():
        shutil.rmtree(base, ignore_errors=True)


def list_attachments(session_id: str) -> list[StoredAttachment]:
    """Return every attachment stored for *session_id*, oldest first."""
    return _read_index(session_id) if session_id else []


def attachment_path(entry: StoredAttachment) -> str:
    """Return the readable path for *entry*, falling back to the original file."""
    stored = str(entry.get("stored_path") or "")
    if stored and Path(stored).is_file():
        return stored
    return str(entry.get("source_path") or stored)


def read_markdown(entry: StoredAttachment) -> str:
    """Return the stored Markdown for *entry*, or an empty string when missing."""
    path = Path(str(entry.get("markdown_path") or ""))
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.exception("Could not read uploaded Markdown %s", path)
        return ""


def resolve_attachment(session_id: str, reference: str | None) -> StoredAttachment | None:
    """Return the attachment *reference* names, or None when it is ambiguous.

    Accepts a ``postmark://uploaded/<name>.md`` URI, a ``doc:N`` handle, a file
    name, or nothing at all when the session holds exactly one attachment.
    """
    entries = list_attachments(session_id)
    if not entries:
        return None
    raw = (reference or "").strip()
    if not raw:
        return entries[0] if len(entries) == 1 else None

    document = uri_document_name(raw)
    if document:
        wanted_md = document.lower()
        for entry in entries:
            if str(entry.get("markdown_name", "")).lower() == wanted_md:
                return entry
        # A model may abbreviate or damage an echoed URI. There is no ambiguity
        # when this chat owns one upload, so use that upload rather than failing a
        # deterministic read because an unnecessary identifier was malformed.
        return entries[0] if len(entries) == 1 else None

    ordinal = handle_ordinal(raw)
    if ordinal is not None and 1 <= ordinal <= len(entries):
        return entries[ordinal - 1]

    wanted = Path(raw).name.strip().lower()
    if wanted:
        for entry in entries:
            if str(entry.get("name", "")).lower() == wanted:
                return entry
        stem = Path(wanted).stem[:12]
        if stem:
            matches = [e for e in entries if str(e.get("name", "")).lower().startswith(stem)]
            if len(matches) == 1:
                return matches[0]
    return entries[0] if len(entries) == 1 else None


__all__ = [
    "MAX_UPLOAD_IMAGES",
    "attachment_path",
    "delete_session_attachments",
    "list_attachments",
    "read_markdown",
    "resolve_attachment",
    "store_attachments",
]
