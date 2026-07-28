"""Split an uploaded Markdown document into bounded, ordered reading chunks.

A whole spec does not fit comfortably in context, and asking a model to pick page
ranges made coverage depend on its judgement. Chunking is done here instead: the
document is divided once, deterministically, and each chunk states which number it
is out of how many, so reading to the end is a matter of counting.
"""

from __future__ import annotations

from typing import NamedTuple

from services.document_import.to_markdown import page_numbers_in

# Roughly 3k tokens of document per chunk, leaving the model room to hold the
# collection it is building alongside what it is reading.
MAX_CHUNK_CHARS = 12_000

# Never split inside a fenced block, so OCR text and examples stay intact.
_FENCE = "```"


class DocumentChunk(NamedTuple):
    """One slice of an uploaded document."""

    number: int
    total: int
    text: str
    first_page: int
    last_page: int


def _split_units(markdown: str) -> list[str]:
    """Split *markdown* into blocks that must not be broken apart."""
    units: list[str] = []
    buffer: list[str] = []
    in_fence = False
    for line in markdown.splitlines():
        if line.strip().startswith(_FENCE):
            in_fence = not in_fence
        buffer.append(line)
        if not in_fence and not line.strip():
            units.append("\n".join(buffer))
            buffer = []
    if buffer:
        units.append("\n".join(buffer))
    return [unit for unit in units if unit.strip()]


def _hard_split(unit: str) -> list[str]:
    """Break a single oversized block into pieces that fit a chunk."""
    return [unit[start : start + MAX_CHUNK_CHARS] for start in range(0, len(unit), MAX_CHUNK_CHARS)]


def split_markdown(markdown: str) -> list[DocumentChunk]:
    """Return every chunk of *markdown*, in order and covering the whole document."""
    text = markdown or ""
    if not text.strip():
        return []

    bodies: list[str] = []
    current: list[str] = []
    size = 0
    for unit in _split_units(text):
        pieces = _hard_split(unit) if len(unit) > MAX_CHUNK_CHARS else [unit]
        for piece in pieces:
            if current and size + len(piece) > MAX_CHUNK_CHARS:
                bodies.append("\n".join(current))
                current, size = [], 0
            current.append(piece)
            size += len(piece) + 1
    if current:
        bodies.append("\n".join(current))

    total = len(bodies)
    chunks: list[DocumentChunk] = []
    last_seen = 0
    for number, body in enumerate(bodies, 1):
        pages = page_numbers_in(body)
        first = pages[0] if pages else last_seen
        last = pages[-1] if pages else last_seen
        last_seen = last or last_seen
        chunks.append(
            DocumentChunk(number=number, total=total, text=body, first_page=first, last_page=last)
        )
    return chunks


def chunk_at(markdown: str, index: int) -> DocumentChunk | None:
    """Return the 1-based *index* chunk of *markdown*, or None when out of range."""
    chunks = split_markdown(markdown)
    if index < 1 or index > len(chunks):
        return None
    return chunks[index - 1]


__all__ = ["MAX_CHUNK_CHARS", "DocumentChunk", "chunk_at", "split_markdown"]
