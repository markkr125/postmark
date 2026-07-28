"""TypedDict schemas for extracted PDF/DOCX documents."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


class ExtractedImage(TypedDict):
    """One embedded screenshot normalized to PNG."""

    index: int
    page: int  # 1-based for pdf; 0 for docx
    mime: str  # always "image/png"
    data_b64: str  # base64 PNG
    ocr_text: str  # "" unless OCR ran
    width: int
    height: int


class ExtractedBlock(TypedDict):
    """One ordered text/table/image block from a document."""

    kind: Literal["text", "table", "image"]
    page: int
    text: NotRequired[str]  # text/table
    image_index: NotRequired[int]  # image -> images[]


class ExtractedDocument(TypedDict):
    """Full ordered extraction result for a PDF or DOCX file."""

    source_name: str
    doc_type: Literal["pdf", "docx"]
    page_count: int
    blocks: list[ExtractedBlock]
    images: list[ExtractedImage]
    warnings: list[str]


MIN_IMAGE_PIXELS = 64 * 64


def repeated_image_warning(count: int) -> str:
    """Return the warning emitted when one image recurs on many pages."""
    return (
        f"Collapsed {count} repeats of page furniture (logo or header image) "
        "into their first occurrence"
    )


def tiny_image_warning(count: int) -> str:
    """Return the warning emitted when images were dropped for being too small."""
    return (
        f"Skipped {count} image(s) smaller than {MIN_IMAGE_PIXELS} pixels "
        "(icons or logos, too small to hold a request example)"
    )


def image_cap_warning(max_images: int) -> str:
    """Return the actionable warning emitted when the image cap is reached."""
    return (
        f"Stopped after {max_images} images; the remaining screenshots in this "
        "document were not read"
    )


def image_is_too_small(width: int, height: int) -> bool:
    """Return True for images too small to carry a readable request example."""
    return width * height < MIN_IMAGE_PIXELS


class DocumentImportError(Exception):
    """Raised when path validation or extraction fails."""

    def __init__(self, code: str) -> None:
        """Store a machine-readable error code."""
        super().__init__(code)
        self.code = code


__all__ = [
    "DocumentImportError",
    "ExtractedBlock",
    "ExtractedDocument",
    "ExtractedImage",
]
