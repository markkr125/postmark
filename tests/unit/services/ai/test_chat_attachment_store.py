"""Tests for copying chat attachments into the session directory."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from database.data_paths import session_attachments_dir
from database.models.ai_chat.ai_chat_repository import create_session, delete_session
from services.ai.chat.attachments.models import ATTACHMENT_INDEX_NAME
from services.ai.chat.attachments.store import (
    attachment_path,
    list_attachments,
    resolve_attachment,
    store_attachments,
)


def _pdf(path: Path, text: str = "Endpoint list") -> Path:
    """Write a minimal one-page PDF at *path*."""
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.drawString(72, 720, text)
    pdf.showPage()
    pdf.save()
    return path


@pytest.fixture
def session_id() -> str:
    """Return a persisted chat session id."""
    new_id = str(uuid.uuid4())
    create_session(session_id=new_id, title="t", model_id="m1", mode="agent")
    return new_id


def test_attachment_is_copied_into_the_session_directory(session_id: str, tmp_path: Path) -> None:
    """A copy is what makes the chat independent of the user's Downloads folder."""
    source = _pdf(tmp_path / "Agoda Standard Pull Spec v1.34 (5) (1).pdf")
    entries = store_attachments(session_id, [str(source)])

    assert len(entries) == 1
    stored = Path(entries[0]["stored_path"])
    assert stored.is_file()
    assert stored.is_relative_to(session_attachments_dir(session_id))
    assert entries[0]["handle"] == "doc:1"
    assert entries[0]["name"] == source.name
    assert entries[0]["size_bytes"] == source.stat().st_size


def test_reading_survives_the_original_being_deleted(session_id: str, tmp_path: Path) -> None:
    """The failure this change exists to prevent: the borrowed file disappears."""
    source = _pdf(tmp_path / "spec.pdf")
    store_attachments(session_id, [str(source)])
    source.unlink()

    entry = resolve_attachment(session_id, None)
    assert entry is not None
    assert Path(attachment_path(entry)).is_file()


def test_index_persists_for_a_reopened_session(session_id: str, tmp_path: Path) -> None:
    """Resolution reads from disk, so a chat reopened later still works."""
    store_attachments(session_id, [str(_pdf(tmp_path / "spec.pdf"))])
    assert (session_attachments_dir(session_id) / ATTACHMENT_INDEX_NAME).is_file()
    assert len(list_attachments(session_id)) == 1


def test_copies_stay_out_of_the_sdk_session_directory(session_id: str, tmp_path: Path) -> None:
    """The SDK scans its own directory and warns about files it does not know."""
    from database.data_paths import session_disk_dir

    store_attachments(session_id, [str(_pdf(tmp_path / "spec.pdf"))])
    stored = Path(list_attachments(session_id)[0]["stored_path"])
    assert not stored.is_relative_to(session_disk_dir(session_id))


def test_only_new_attachments_are_returned(session_id: str, tmp_path: Path) -> None:
    """The caller inlines what it gets back, so returning old ones would repeat them."""
    store_attachments(session_id, [str(_pdf(tmp_path / "first.pdf"))])
    added = store_attachments(session_id, [str(_pdf(tmp_path / "second.pdf"))])

    assert [entry["name"] for entry in added] == ["second.pdf"]
    assert len(list_attachments(session_id)) == 2


def test_handles_are_stable_as_more_files_are_added(session_id: str, tmp_path: Path) -> None:
    """A handle must keep pointing at the same document across turns."""
    store_attachments(session_id, [str(_pdf(tmp_path / "first.pdf"))])
    store_attachments(session_id, [str(_pdf(tmp_path / "second.pdf"))])

    entries = list_attachments(session_id)
    assert [e["handle"] for e in entries] == ["doc:1", "doc:2"]
    first = resolve_attachment(session_id, "doc:1")
    second = resolve_attachment(session_id, "doc:2")
    assert first is not None and first["name"] == "first.pdf"
    assert second is not None and second["name"] == "second.pdf"


def test_same_name_in_different_folders_stays_distinct(session_id: str, tmp_path: Path) -> None:
    """Copies are keyed by ordinal, so identical names cannot collide."""
    left = tmp_path / "a"
    right = tmp_path / "b"
    left.mkdir()
    right.mkdir()
    store_attachments(session_id, [str(_pdf(left / "spec.pdf", "left"))])
    store_attachments(session_id, [str(_pdf(right / "spec.pdf", "right"))])

    entries = list_attachments(session_id)
    assert len({e["stored_path"] for e in entries}) == 2
    assert entries[0]["sha256"] != entries[1]["sha256"]


def test_deleting_the_session_removes_the_copies(session_id: str, tmp_path: Path) -> None:
    """Retention is the existing session rmtree; nothing may be left behind."""
    store_attachments(session_id, [str(_pdf(tmp_path / "spec.pdf"))])
    stored = Path(list_attachments(session_id)[0]["stored_path"])
    assert stored.is_file()

    delete_session(session_id)
    assert not stored.exists()
    assert list_attachments(session_id) == []


def test_unsupported_file_is_skipped_not_fatal(session_id: str, tmp_path: Path) -> None:
    """One bad pick must not swallow the user's whole message."""
    bad = tmp_path / "notes.txt"
    bad.write_text("hello", encoding="utf-8")
    good = _pdf(tmp_path / "spec.pdf")

    entries = store_attachments(session_id, [str(bad), str(good)])
    assert [e["name"] for e in entries] == ["spec.pdf"]


def test_image_attachment_is_skipped_for_document_import(session_id: str, tmp_path: Path) -> None:
    """Only PDF/DOCX are readable, so other types must not enter the index."""
    png = tmp_path / "screenshot.png"
    Image.new("RGB", (32, 32), color="red").save(png)
    assert store_attachments(session_id, [str(png)]) == []


def test_name_reference_selects_among_attachments(session_id: str, tmp_path: Path) -> None:
    """A model naming the file rather than the handle must still land correctly."""
    store_attachments(session_id, [str(_pdf(tmp_path / "first.pdf"))])
    store_attachments(session_id, [str(_pdf(tmp_path / "second.pdf"))])

    entry = resolve_attachment(session_id, "/wrong/dir/second.pdf")
    assert entry is not None
    assert entry["name"] == "second.pdf"


def test_ambiguous_reference_is_refused(session_id: str, tmp_path: Path) -> None:
    """Guessing between attachments would read the wrong document."""
    store_attachments(session_id, [str(_pdf(tmp_path / "first.pdf"))])
    store_attachments(session_id, [str(_pdf(tmp_path / "second.pdf"))])
    assert resolve_attachment(session_id, None) is None
    assert resolve_attachment(session_id, "doc:9") is None


def test_unknown_session_yields_no_attachments(tmp_path: Path) -> None:
    """A session with no stored index must not raise."""
    assert list_attachments(str(uuid.uuid4())) == []


def test_damaged_uri_falls_back_to_the_only_attachment(session_id: str, tmp_path: Path) -> None:
    """A lone upload is unambiguous even when a small model mangles its URI."""
    store_attachments(session_id, [str(_pdf(tmp_path / "spec.pdf"))])
    entry = resolve_attachment(session_id, "postmark://uploaded/spec-v1.")
    assert entry is not None
    assert entry["name"] == "spec.pdf"
    assert store_attachments("", [str(tmp_path / "x.pdf")]) == []
