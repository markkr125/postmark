"""Path validation and dispatch for PDF/DOCX document extraction."""

from __future__ import annotations

from pathlib import Path

from services.document_import.docx_extract import extract_docx
from services.document_import.models import DocumentImportError, ExtractedDocument
from services.document_import.pdf_extract import extract_pdf

_MAX_BYTES = 50 * 1024 * 1024
_SENSITIVE = (".env", ".ssh", "id_rsa", "id_ed25519", "credentials", "secrets")
_DENY_DIRS = ("/etc", "/root")
_SUPPORTED_SUFFIXES = {".pdf", ".docx"}
_NAME_SEPARATORS = ("-", "_", ".")


def _matches_sensitive(name: str, sensitive: str) -> bool:
    """Return True when *name* is a sensitive name or a suffixed variant of it."""
    if name == sensitive:
        return True
    return any(name.startswith(f"{sensitive}{sep}") for sep in _NAME_SEPARATORS)


def _directory_is_sensitive(segment: str) -> bool:
    """Return True for directories that hold secrets (``secrets``, ``.env.local``)."""
    lowered = segment.lower()
    return any(_matches_sensitive(lowered, sensitive) for sensitive in _SENSITIVE)


def _filename_is_sensitive(segment: str) -> bool:
    """Return True only when a document's own stem is a sensitive name.

    Document names legitimately embed these words (``credentials-api-v2.pdf``),
    so the file itself is rejected only on an exact stem match or a dotfile.
    """
    lowered = segment.lower()
    if lowered.startswith("."):
        return _directory_is_sensitive(lowered)
    stem = lowered.rsplit(".", 1)[0] if "." in lowered else lowered
    return stem in _SENSITIVE


def validate_document_path(path_str: str) -> Path:
    """Resolve and validate a local document path for extraction."""
    raw = (path_str or "").strip()
    if not raw:
        raise DocumentImportError("missing_path")
    if ".." in raw.split("/"):
        raise DocumentImportError("invalid_path")
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise DocumentImportError("missing_file")
    for segment in path.parts[:-1]:
        if _directory_is_sensitive(segment):
            raise DocumentImportError("sensitive_path")
    if _filename_is_sensitive(path.name):
        raise DocumentImportError("sensitive_path")
    deny_roots = [Path(d).resolve() for d in _DENY_DIRS] + [Path.home() / ".ssh"]
    for root in deny_roots:
        if path.is_relative_to(root):
            raise DocumentImportError("denied_path")
    if path.stat().st_size > _MAX_BYTES:
        raise DocumentImportError("file_too_large")
    if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise DocumentImportError("unsupported_document_type")
    return path


def parse_page_range(value: str | None) -> tuple[int, int] | None:
    """Parse a 1-based inclusive page range like ``1-5``."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if "-" not in text:
        raise DocumentImportError("bad_page_range")
    start_text, end_text = text.split("-", 1)
    try:
        start = int(start_text.strip())
        end = int(end_text.strip())
    except ValueError as exc:
        raise DocumentImportError("bad_page_range") from exc
    if start < 1 or end < start:
        raise DocumentImportError("bad_page_range")
    return start, end


def extract_document(
    path_str: str,
    *,
    page_range: tuple[int, int] | None = None,
    max_images: int = 20,
    run_ocr: bool = True,
) -> ExtractedDocument:
    """Validate *path_str* and extract an ordered document bundle."""
    path = validate_document_path(path_str)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(
            path,
            page_range=page_range,
            max_images=max_images,
            run_ocr=run_ocr,
        )
    if suffix == ".docx":
        return extract_docx(path, max_images=max_images, run_ocr=run_ocr)
    raise DocumentImportError("unsupported_document_type")


__all__ = [
    "DocumentImportError",
    "extract_document",
    "parse_page_range",
    "validate_document_path",
]
