"""Tests for splitting uploaded Markdown into ordered reading chunks."""

from __future__ import annotations

from itertools import pairwise

from services.ai.chat.attachments.chunks import MAX_CHUNK_CHARS, chunk_at, split_markdown


def _markdown(pages: int, per_page: int = 3_000) -> str:
    """Return Markdown spanning *pages* pages of roughly *per_page* characters."""
    parts: list[str] = ["# spec.pdf", ""]
    for page in range(1, pages + 1):
        parts.extend([f"<!-- page {page} -->", "", f"body {page} " + "x " * (per_page // 2), ""])
    return "\n".join(parts)


def test_empty_document_has_no_chunks() -> None:
    """Nothing to read means nothing to iterate."""
    assert split_markdown("   ") == []


def test_short_document_is_a_single_chunk() -> None:
    """A small document is not fragmented needlessly."""
    chunks = split_markdown(_markdown(1, per_page=100))
    assert len(chunks) == 1
    assert chunks[0].number == 1
    assert chunks[0].total == 1


def test_chunks_stay_within_the_size_budget() -> None:
    """Every chunk fits the budget that keeps a read affordable."""
    chunks = split_markdown(_markdown(20))
    assert len(chunks) > 1
    assert all(len(chunk.text) <= MAX_CHUNK_CHARS + 1 for chunk in chunks)


def test_chunks_are_numbered_in_order_against_one_total() -> None:
    """Counters let the agent know when it has read everything."""
    chunks = split_markdown(_markdown(20))
    assert [chunk.number for chunk in chunks] == list(range(1, len(chunks) + 1))
    assert {chunk.total for chunk in chunks} == {len(chunks)}


def test_every_line_appears_in_exactly_one_chunk() -> None:
    """Chunking covers the document without dropping or duplicating content."""
    markdown = _markdown(12)
    chunks = split_markdown(markdown)
    combined = "\n".join(chunk.text for chunk in chunks)
    for page in range(1, 13):
        assert combined.count(f"body {page} ") == 1


def test_chunks_report_the_pages_they_cover() -> None:
    """Page ranges give the agent a citable location for each endpoint."""
    chunks = split_markdown(_markdown(20))
    assert chunks[0].first_page == 1
    assert chunks[-1].last_page == 20
    for earlier, later in pairwise(chunks):
        assert later.first_page >= earlier.last_page


def test_a_fenced_block_is_never_split() -> None:
    """OCR blocks and examples survive intact across chunk boundaries."""
    fence = "```text\n" + "GET /v1/search\n" * 400 + "```"
    chunks = split_markdown("\n\n".join([_markdown(4), fence]))
    holders = [chunk for chunk in chunks if "GET /v1/search" in chunk.text]
    assert len(holders) == 1
    assert holders[0].text.count("```") == 2


def test_an_oversized_block_is_broken_rather_than_dropped() -> None:
    """A single huge paragraph still fits the budget instead of being lost."""
    chunks = split_markdown("y" * (MAX_CHUNK_CHARS * 3))
    assert len(chunks) == 3
    assert all(len(chunk.text) <= MAX_CHUNK_CHARS for chunk in chunks)


def test_chunk_at_is_one_based_and_bounded() -> None:
    """Out-of-range requests are refused rather than clamped silently."""
    markdown = _markdown(20)
    total = len(split_markdown(markdown))
    assert chunk_at(markdown, 1) is not None
    assert chunk_at(markdown, total) is not None
    assert chunk_at(markdown, 0) is None
    assert chunk_at(markdown, total + 1) is None
