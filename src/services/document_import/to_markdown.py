"""Render an extracted PDF/DOCX document as Markdown for chunked reading.

Markdown is the storage format for uploads because it keeps the structure a model
needs to find endpoints — headings, tables, code blocks — while being plain text
that can be sliced into chunks without breaking a parser. Screenshots appear only
as ``[image N]`` markers; the bytes live beside the Markdown.
"""

from __future__ import annotations

import re

from services.document_import.models import ExtractedDocument

# Marks where each source page began, so a chunk can report the pages it covers.
PAGE_MARKER = "<!-- page {page} -->"
_PAGE_MARKER_RE = re.compile(r"<!--\s*page\s+(\d+)\s*-->")

# A heading in extracted PDF text: "9. Hotel Search / Availability Check API".
_NUMBERED_HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2})*)\.?\s+([A-Z][^\n]{2,80})$")

# A line that is already a pipe-delimited row from a DOCX table.
_TABLE_ROW = re.compile(r"^[^|\n]*\|")


def page_numbers_in(markdown: str) -> list[int]:
    """Return the source page numbers marked in *markdown*, in order."""
    return [int(match) for match in _PAGE_MARKER_RE.findall(markdown)]


def _heading(text: str) -> str | None:
    """Return *text* as a Markdown heading when it looks like a section title."""
    match = _NUMBERED_HEADING.match(text.strip())
    if match is None:
        return None
    number, title = match.groups()
    level = min(2 + number.count("."), 6)
    return f"{'#' * level} {number}. {title.strip()}"


def _table(text: str) -> str:
    """Render pipe-delimited rows as a Markdown table with a header separator."""
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    if not rows:
        return ""
    if not _TABLE_ROW.match(rows[0]):
        return "\n".join(rows)
    columns = len(rows[0].split("|"))
    separator = "| " + " | ".join(["---"] * columns) + " |"
    body = [f"| {row.strip('| ')} |" for row in rows]
    return "\n".join([body[0], separator, *body[1:]])


def document_to_markdown(doc: ExtractedDocument) -> str:
    """Return the whole document as Markdown, with page markers and image OCR."""
    lines: list[str] = [f"# {doc['source_name']}", ""]
    if doc["warnings"]:
        lines.append("> Extraction notes:")
        lines.extend(f"> - {warning}" for warning in doc["warnings"])
        lines.append("")

    current_page = -1
    for block in doc["blocks"]:
        page = block["page"]
        if page and page != current_page:
            current_page = page
            lines.extend([PAGE_MARKER.format(page=page), ""])

        if block["kind"] == "image":
            # Only the marker is stored. Whether the screenshot reaches the model as
            # an image or as recognised text depends on the model reading it, which
            # is not known at upload time.
            lines.extend([f"**[image {int(block.get('image_index', 0)) + 1}]**", ""])
            continue

        text = block.get("text", "").strip()
        if not text:
            continue
        if block["kind"] == "table":
            lines.extend([_table(text), ""])
            continue
        heading = _heading(text)
        lines.extend([heading, ""] if heading else [text, ""])

    return "\n".join(lines).strip() + "\n"


__all__ = ["PAGE_MARKER", "document_to_markdown", "page_numbers_in"]
