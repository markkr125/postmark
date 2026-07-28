"""Extract ordered text, tables, and embedded images from DOCX files."""

from __future__ import annotations

import zipfile
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from services.document_import.models import ExtractedBlock, ExtractedDocument
from services.document_import.ocr import ImageCollector

_MEDIA_PREFIX = "word/media/"


def _table_text(table: Table) -> str:
    """Render a DOCX table as newline-separated pipe-delimited rows."""
    rows: list[str] = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        rows.append(" | ".join(cells))
    return "\n".join(rows)


def _blip_parts(paragraph: Paragraph, document: DocxDocument) -> list[tuple[str, bytes]]:
    """Return (part name, bytes) for every drawing referenced by *paragraph*."""
    found: list[tuple[str, bytes]] = []
    for blip in paragraph._element.findall(".//" + qn("a:blip")):
        embed = blip.get(qn("r:embed"))
        if not embed:
            continue
        related = document.part.related_parts.get(embed)
        if related is None:
            continue
        found.append((str(related.partname), related.blob))
    return found


def _table_image_parts(table: Table, document: DocxDocument) -> list[tuple[str, bytes]]:
    """Return images embedded anywhere inside *table*, including nested tables."""
    found: list[tuple[str, bytes]] = []
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                found.extend(_blip_parts(paragraph, document))
            for nested in cell.tables:
                found.extend(_table_image_parts(nested, document))
    return found


def _drain(
    collector: ImageCollector,
    blocks: list[ExtractedBlock],
    parts: list[tuple[str, bytes]],
    seen_parts: set[str],
) -> None:
    """Add *parts* to the collector, appending kept blocks in document order."""
    for part_name, raw in parts:
        if part_name in seen_parts:
            continue
        seen_parts.add(part_name)
        block = collector.add(raw, page=0, label=part_name)
        if block is not None:
            blocks.append(block)


def _append_unpositioned_media(
    path: Path,
    collector: ImageCollector,
    blocks: list[ExtractedBlock],
    seen_parts: set[str],
) -> None:
    """Append zip media never reached by the body walk (headers, text boxes)."""
    added_before = len(collector.images)
    with zipfile.ZipFile(path) as archive:
        names = sorted(n for n in archive.namelist() if n.startswith(_MEDIA_PREFIX))
        pending = [(f"/{name}", name) for name in names if f"/{name}" not in seen_parts]
        for part_name, name in pending:
            _drain(collector, blocks, [(part_name, archive.read(name))], seen_parts)
    added = len(collector.images) - added_before
    if added:
        collector.warnings.append(
            f"{added} image(s) are not positioned in the document flow "
            "(header, footer, or text box) and appear at the end"
        )


def extract_docx(
    path: Path,
    *,
    max_images: int,
    run_ocr: bool,
) -> ExtractedDocument:
    """Extract body-ordered paragraphs, tables, and embedded images from a DOCX."""
    document = Document(str(path))
    blocks: list[ExtractedBlock] = []
    collector = ImageCollector(max_images=max_images, run_ocr=run_ocr)
    seen_parts: set[str] = set()

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if text:
                blocks.append({"kind": "text", "page": 0, "text": text})
            _drain(collector, blocks, _blip_parts(paragraph, document), seen_parts)
        elif isinstance(child, CT_Tbl):
            table = Table(child, document)
            text = _table_text(table).strip()
            if text:
                blocks.append({"kind": "table", "page": 0, "text": text})
            _drain(collector, blocks, _table_image_parts(table, document), seen_parts)

    _append_unpositioned_media(path, collector, blocks, seen_parts)

    return {
        "source_name": path.name,
        "doc_type": "docx",
        "page_count": 0,
        "blocks": blocks,
        "images": collector.images,
        "warnings": collector.finalize_warnings(),
    }


__all__ = ["extract_docx"]
