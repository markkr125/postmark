"""Tests for rendering an extracted document as Markdown."""

from __future__ import annotations

from services.document_import.models import ExtractedDocument
from services.document_import.to_markdown import document_to_markdown, page_numbers_in


def _doc(**overrides: object) -> ExtractedDocument:
    """Return a minimal extracted document with *overrides* applied."""
    base: ExtractedDocument = {
        "source_name": "spec.pdf",
        "doc_type": "pdf",
        "page_count": 2,
        "blocks": [],
        "images": [],
        "warnings": [],
    }
    return {**base, **overrides}  # type: ignore[typeddict-item]


def test_page_markers_record_source_pages() -> None:
    """Each page transition is marked so a chunk can report its page range."""
    doc = _doc(
        blocks=[
            {"kind": "text", "page": 1, "text": "first"},
            {"kind": "text", "page": 3, "text": "third"},
        ]
    )
    markdown = document_to_markdown(doc)
    assert page_numbers_in(markdown) == [1, 3]


def test_numbered_titles_become_headings() -> None:
    """Numbered section titles are promoted so chunk boundaries stay readable."""
    doc = _doc(
        blocks=[
            {"kind": "text", "page": 1, "text": "9. Hotel Search API"},
            {"kind": "text", "page": 1, "text": "9.1. Request Fields"},
        ]
    )
    markdown = document_to_markdown(doc)
    assert "## 9. Hotel Search API" in markdown
    assert "### 9.1. Request Fields" in markdown


def test_prose_is_not_turned_into_a_heading() -> None:
    """Ordinary sentences stay body text."""
    doc = _doc(blocks=[{"kind": "text", "page": 1, "text": "The API returns a JSON body."}])
    markdown = document_to_markdown(doc)
    assert "# The API" not in markdown
    assert "The API returns a JSON body." in markdown


def test_tables_get_a_header_separator() -> None:
    """Pipe rows become a real Markdown table so columns survive chunking."""
    doc = _doc(blocks=[{"kind": "table", "page": 1, "text": "name | type\nid | string"}])
    markdown = document_to_markdown(doc)
    assert "| name | type |" in markdown
    assert "| --- | --- |" in markdown
    assert "| id | string |" in markdown


def test_screenshots_are_stored_as_markers_only() -> None:
    """Whether a screenshot is delivered as an image or as text is a read-time choice.

    Baking recognised text into the document would force it on vision models, which
    read the screenshot itself far better.
    """
    doc = _doc(
        blocks=[{"kind": "image", "page": 2, "image_index": 0}],
        images=[
            {
                "index": 0,
                "page": 2,
                "mime": "image/png",
                "data_b64": "",
                "ocr_text": "POST /v1/search",
                "width": 100,
                "height": 100,
            }
        ],
    )
    markdown = document_to_markdown(doc)
    assert "**[image 1]**" in markdown
    assert "POST /v1/search" not in markdown


def test_extraction_warnings_are_kept_visible() -> None:
    """Warnings ride along in the document so the agent can report them."""
    doc = _doc(warnings=["Stopped after 40 images"])
    assert "Stopped after 40 images" in document_to_markdown(doc)
