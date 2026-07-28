"""Tests for document path validation."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from services.document_import import extract as extract_module
from services.document_import.extract import extract_document, validate_document_path
from services.document_import.models import DocumentImportError

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_SAMPLE_PDF = _FIXTURES / "sample.pdf"


def test_rejects_sensitive_segment(tmp_path: Path) -> None:
    """Paths with sensitive segment names are rejected."""
    bad = tmp_path / ".env" / "secret.pdf"
    bad.parent.mkdir()
    bad.write_bytes(b"%PDF")
    with pytest.raises(DocumentImportError) as exc:
        validate_document_path(str(bad))
    assert exc.value.code == "sensitive_path"


def test_allows_credentials_in_filename(tmp_path: Path) -> None:
    """Filenames containing sensitive words as substrings remain allowed."""
    ok = tmp_path / "credentials-api-v2.pdf"
    shutil.copy(_SAMPLE_PDF, ok)
    path = validate_document_path(str(ok))
    assert path.name == "credentials-api-v2.pdf"


def test_rejects_sensitive_stem_filename(tmp_path: Path) -> None:
    """A document whose stem is exactly a sensitive name is rejected."""
    bad = tmp_path / "secrets.pdf"
    shutil.copy(_SAMPLE_PDF, bad)
    with pytest.raises(DocumentImportError) as exc:
        validate_document_path(str(bad))
    assert exc.value.code == "sensitive_path"


def test_rejects_suffixed_sensitive_directory(tmp_path: Path) -> None:
    """Directories like ``secrets-2024`` are treated as sensitive."""
    folder = tmp_path / "secrets-2024"
    folder.mkdir()
    target = folder / "api.pdf"
    shutil.copy(_SAMPLE_PDF, target)
    with pytest.raises(DocumentImportError) as exc:
        validate_document_path(str(target))
    assert exc.value.code == "sensitive_path"


def test_rejects_missing_file(tmp_path: Path) -> None:
    """Missing files raise missing_file."""
    with pytest.raises(DocumentImportError) as exc:
        validate_document_path(str(tmp_path / "missing.pdf"))
    assert exc.value.code == "missing_file"


def test_rejects_oversize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Oversize files raise file_too_large."""
    monkeypatch.setattr(extract_module, "_MAX_BYTES", 16)
    big = tmp_path / "big.pdf"
    big.write_bytes(b"x" * 17)
    with pytest.raises(DocumentImportError) as exc:
        validate_document_path(str(big))
    assert exc.value.code == "file_too_large"


def test_rejects_unsupported_suffix(tmp_path: Path) -> None:
    """Unsupported suffixes raise unsupported_document_type."""
    txt = tmp_path / "notes.txt"
    txt.write_text("hello", encoding="utf-8")
    with pytest.raises(DocumentImportError) as exc:
        validate_document_path(str(txt))
    assert exc.value.code == "unsupported_document_type"


def test_accepts_pdf_in_tmp(tmp_path: Path) -> None:
    """A valid PDF in tmp is accepted and extracted."""
    target = tmp_path / "sample.pdf"
    shutil.copy(_SAMPLE_PDF, target)
    doc = extract_document(str(target), run_ocr=False)
    assert doc["doc_type"] == "pdf"
    assert doc["source_name"] == "sample.pdf"
