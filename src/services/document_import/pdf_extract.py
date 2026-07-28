"""Extract ordered text and embedded images from PDF files."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from services.document_import.models import ExtractedBlock, ExtractedDocument
from services.document_import.ocr import ImageCollector


def _text_blocks(page_num: int, raw_text: str) -> list[ExtractedBlock]:
    """Split page text on blank lines into ordered text blocks."""
    blocks: list[ExtractedBlock] = []
    for chunk in raw_text.split("\n\n"):
        text = chunk.strip()
        if text:
            blocks.append({"kind": "text", "page": page_num, "text": text})
    return blocks


def extract_pdf(
    path: Path,
    *,
    page_range: tuple[int, int] | None,
    max_images: int,
    run_ocr: bool,
) -> ExtractedDocument:
    """Extract text blocks and embedded images from a PDF."""
    reader = PdfReader(str(path))
    page_count = len(reader.pages)
    start, end = page_range or (1, page_count)
    blocks: list[ExtractedBlock] = []
    collector = ImageCollector(max_images=max_images, run_ocr=run_ocr)

    for page_num, page in enumerate(reader.pages, 1):
        if page_num < start or page_num > end:
            continue
        raw_text = page.extract_text() or ""
        blocks.extend(_text_blocks(page_num, raw_text))
        for img in getattr(page, "images", []):
            if collector.at_capacity():
                break
            block = collector.add(img.data, page=page_num)
            if block is not None:
                blocks.append(block)

    return {
        "source_name": path.name,
        "doc_type": "pdf",
        "page_count": page_count,
        "blocks": blocks,
        "images": collector.images,
        "warnings": collector.finalize_warnings(),
    }


__all__ = ["extract_pdf"]
