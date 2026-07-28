"""Tests for PDF document extraction."""

from __future__ import annotations

from pathlib import Path

from services.document_import.extract import extract_document
from services.document_import.models import (
    image_cap_warning,
    repeated_image_warning,
    tiny_image_warning,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_SAMPLE_PDF = _FIXTURES / "sample.pdf"


def test_pdf_extracts_text_blocks_in_order() -> None:
    """PDF paragraphs become ordered text blocks."""
    doc = extract_document(str(_SAMPLE_PDF), run_ocr=False)
    text_blocks = [block for block in doc["blocks"] if block["kind"] == "text"]
    assert text_blocks
    combined = "\n".join(block["text"] for block in text_blocks)
    assert "First paragraph block." in combined
    assert "Second paragraph after blank line." in combined
    assert combined.index("First paragraph block.") < combined.index(
        "Second paragraph after blank line."
    )


def test_pdf_extracts_embedded_image_dimensions() -> None:
    """Embedded PDF images are normalized to PNG with dimensions."""
    doc = extract_document(str(_SAMPLE_PDF), run_ocr=False)
    assert doc["images"]
    image = doc["images"][0]
    assert image["mime"] == "image/png"
    assert image["width"] > 0
    assert image["height"] > 0
    assert any(block["kind"] == "image" for block in doc["blocks"])


def test_pdf_page_range_limits_extracted_pages(tmp_path: Path) -> None:
    """A page range restricts extraction to those pages only."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(_SAMPLE_PDF))
    writer = PdfWriter()
    for _ in range(3):
        writer.add_page(reader.pages[0])
    multi = tmp_path / "three.pdf"
    with multi.open("wb") as handle:
        writer.write(handle)

    doc = extract_document(str(multi), page_range=(2, 2), run_ocr=False)
    assert doc["page_count"] == 3
    assert {block["page"] for block in doc["blocks"]} == {2}


def test_pdf_image_cap_warns_once(tmp_path: Path) -> None:
    """Hitting max_images emits a single warning across pages."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(_SAMPLE_PDF))
    writer = PdfWriter()
    for _ in range(4):
        writer.add_page(reader.pages[0])
    multi = tmp_path / "multi.pdf"
    with multi.open("wb") as handle:
        writer.write(handle)

    doc = extract_document(str(multi), max_images=1, run_ocr=False)
    assert len(doc["images"]) == 1
    assert image_cap_warning(1) in doc["warnings"]
    assert "not read" in doc["warnings"][0]


def test_repeated_page_logo_is_collapsed(tmp_path: Path) -> None:
    """A logo on every page must not consume the image budget or repeat its OCR.

    Real specs put the same header image on all pages; emitting each copy floods
    the observation with identical content and crowds out real screenshots.
    """
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(_SAMPLE_PDF))
    writer = PdfWriter()
    for _ in range(6):
        writer.add_page(reader.pages[0])
    multi = tmp_path / "logo.pdf"
    with multi.open("wb") as handle:
        writer.write(handle)

    doc = extract_document(str(multi), max_images=30, run_ocr=False)

    assert len(doc["images"]) == 1
    assert repeated_image_warning(5) in doc["warnings"]


def test_icon_sized_images_are_reported_not_silently_dropped(tmp_path: Path) -> None:
    """Dropping images without saying so would hide missing screenshots."""
    from io import BytesIO

    from PIL import Image
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    Image.new("RGB", (8, 8), color="blue").save(buf, format="PNG")
    buf.seek(0)
    tiny = tmp_path / "tiny.pdf"
    pdf = canvas.Canvas(str(tiny), pagesize=letter)
    pdf.drawString(72, 720, "Endpoint list")
    pdf.drawImage(ImageReader(buf), 72, 600, width=8, height=8)
    pdf.showPage()
    pdf.save()

    doc = extract_document(str(tiny), run_ocr=False)

    assert doc["images"] == []
    assert tiny_image_warning(1) in doc["warnings"]
