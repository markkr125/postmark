"""Serve the screenshots belonging to one chunk of an uploaded document.

The model's own capability decides the form: a vision model is given the images,
anything else is given text recognised from them. OCR is strictly the fallback —
it is never run for a model that can see the screenshot itself. Either way the
work is scoped to the chunk being read, because a whole document's images would
blow the budget that chunking exists to protect.
"""

from __future__ import annotations

import json
import logging
import re
from base64 import b64encode
from pathlib import Path

from services.ai.chat.attachments.models import StoredAttachment
from services.document_import.ocr import ocr_image_png

# ``**[image 3]**`` as written into the Markdown by ``document_to_markdown``.
IMAGE_MARKER = re.compile(r"\*\*\[image (\d+)\]\*\*")

# Recognised text is cached beside the screenshots: OCR is slow, and the same
# chunk is often read more than once in a session.
OCR_CACHE_NAME = "ocr.json"

# A chunk spans several pages, and image tokens are billed far above text ones, so
# the count is capped rather than left to whatever the document happens to hold.
MAX_CHUNK_IMAGES = 6

# Per-session vision capability, published by the chat worker at run start.
_VISION: dict[str, bool] = {}

logger = logging.getLogger(__name__)


def set_session_vision(session_id: str, supports_vision: bool) -> None:
    """Record whether *session_id*'s active model can read images."""
    if session_id:
        _VISION[session_id] = supports_vision


def session_supports_vision(session_id: str) -> bool:
    """Return whether *session_id*'s model can read images (False when unknown)."""
    return _VISION.get(session_id, False)


def clear_session_vision(session_id: str) -> None:
    """Forget the vision flag for *session_id*."""
    _VISION.pop(session_id, None)


def image_numbers_in(chunk_text: str) -> list[int]:
    """Return the screenshot numbers marked in *chunk_text*, in order."""
    seen: list[int] = []
    for match in IMAGE_MARKER.findall(chunk_text):
        number = int(match)
        if number not in seen:
            seen.append(number)
    return seen


def _ocr_cache(directory: Path) -> dict[str, str]:
    """Return recognised text already computed for *directory*."""
    path = directory / OCR_CACHE_NAME
    if not path.is_file():
        return {}
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return cached if isinstance(cached, dict) else {}


def _recognise(directory: Path, numbers: list[int]) -> dict[int, str]:
    """Return recognised text for *numbers*, running OCR only for uncached images."""
    cache = _ocr_cache(directory)
    recognised: dict[int, str] = {}
    fresh = False
    for number in numbers:
        key = str(number)
        if key not in cache:
            path = directory / f"image-{number}.png"
            if not path.is_file():
                continue
            try:
                cache[key] = ocr_image_png(path.read_bytes())
            except OSError:
                logger.exception("Could not read screenshot %s", path)
                continue
            fresh = True
        text = cache[key].strip()
        if text:
            recognised[number] = text
    if fresh:
        try:
            (directory / OCR_CACHE_NAME).write_text(json.dumps(cache), encoding="utf-8")
        except OSError:
            logger.exception("Could not cache recognised text in %s", directory)
    return recognised


def chunk_ocr_text(entry: StoredAttachment, chunk_text: str) -> tuple[str, int]:
    """Return *chunk_text* with recognised text placed under each image marker.

    Returns:
        The rewritten chunk and how many screenshots yielded any text, so the
        observation can say when a screenshot could not be read at all.
    """
    directory = Path(str(entry.get("images_dir") or ""))
    numbers = image_numbers_in(chunk_text) if directory.is_dir() else []
    if not numbers:
        return chunk_text, 0

    recognised = _recognise(directory, numbers)
    if not recognised:
        return chunk_text, 0

    def _expand(match: re.Match[str]) -> str:
        text = recognised.get(int(match.group(1)), "")
        return match.group(0) if not text else f"{match.group(0)}\n\n```text\n{text}\n```"

    return IMAGE_MARKER.sub(_expand, chunk_text), len(recognised)


def chunk_screenshots(entry: StoredAttachment, chunk_text: str) -> tuple[list[str], int]:
    """Return data URLs for the screenshots in *chunk_text*, and how many were dropped.

    Returns:
        The data URLs to attach, capped at ``MAX_CHUNK_IMAGES``, and the number of
        images left out so the observation can say so rather than hide it.
    """
    directory = Path(str(entry.get("images_dir") or ""))
    if not directory.is_dir():
        return [], 0

    numbers = image_numbers_in(chunk_text)
    urls: list[str] = []
    skipped = 0
    for number in numbers:
        path = directory / f"image-{number}.png"
        if not path.is_file():
            continue
        if len(urls) >= MAX_CHUNK_IMAGES:
            skipped += 1
            continue
        try:
            urls.append(f"data:image/png;base64,{b64encode(path.read_bytes()).decode('ascii')}")
        except OSError:
            logger.exception("Could not read screenshot %s", path)
    return urls, skipped


__all__ = [
    "IMAGE_MARKER",
    "MAX_CHUNK_IMAGES",
    "OCR_CACHE_NAME",
    "chunk_ocr_text",
    "chunk_screenshots",
    "clear_session_vision",
    "image_numbers_in",
    "session_supports_vision",
    "set_session_vision",
]
