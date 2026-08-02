"""Tests for the ``postmark_document_import`` chunked reader tool."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from openhands.sdk.llm import ImageContent, TextContent
from services.ai.chat.agent_registry import DEFAULT_AGENT_ID, get_agent_def
from services.ai.chat.attachments.chunks import MAX_CHUNK_CHARS
from services.ai.chat.attachments.screenshots import OCR_CACHE_NAME, set_session_vision
from services.ai.chat.attachments.store import (
    list_attachments,
    set_turn_attachments,
    store_attachments,
)
from services.ai.chat.mutation.auto_approve import kind_from_tool_args
from services.ai.chat.tools.document_import.tool import (
    DOCUMENT_IMPORT_TOOL_NAME,
    DocumentImportAction,
    DocumentImportExecutor,
)


def _observation_text(action: DocumentImportAction, session_id: str) -> tuple[str, bool]:
    """Run the executor for *session_id* and return its text and error flag."""
    conversation = SimpleNamespace(state=SimpleNamespace(id=session_id, persistence_dir=None))
    obs = DocumentImportExecutor()(action, cast(Any, conversation))
    first = obs.content[0]
    assert isinstance(first, TextContent)
    return first.text, bool(obs.is_error)


@pytest.fixture
def uploaded(tmp_path: Path) -> tuple[str, str]:
    """Return a session id and the URI of a long DOCX uploaded to it."""
    from docx import Document

    document = Document()
    for section in range(1, 40):
        document.add_paragraph(f"{section}. Endpoint {section}")
        document.add_paragraph("POST /v1/resource-" + str(section) + " " + "detail " * 200)
    source = tmp_path / "spec.docx"
    document.save(str(source))

    session_id = uuid4().hex
    entries = store_attachments(session_id, [str(source)])
    assert entries, "upload should have been stored"
    return session_id, entries[0]["uri"]


@pytest.fixture
def uploaded_with_screenshot(tmp_path: Path) -> tuple[str, str]:
    """Return a session id and the URI of a DOCX holding one screenshot."""
    from docx import Document
    from docx.shared import Inches
    from PIL import Image

    picture = tmp_path / "shot.png"
    Image.new("RGB", (200, 200), "white").save(picture)

    document = Document()
    document.add_paragraph("1. Search endpoint")
    document.add_picture(str(picture), width=Inches(2))
    source = tmp_path / "with_image.docx"
    document.save(str(source))

    session_id = uuid4().hex
    entries = store_attachments(session_id, [str(source)])
    assert entries, "upload should have been stored"
    return session_id, entries[0]["uri"]


def test_ambiguous_attachment_lists_available_documents(tmp_path: Path) -> None:
    """With several uploads and no current-turn hint, the error names each one."""
    from docx import Document

    session_id = uuid4().hex
    for name in ("first.docx", "second.docx"):
        document = Document()
        document.add_paragraph(f"1. Endpoint in {name}")
        source = tmp_path / name
        document.save(str(source))
        store_attachments(session_id, [str(source)])

    text, is_error = _observation_text(DocumentImportAction(chunk=1), session_id)
    assert is_error
    assert "ambiguous_attachment" in text
    assert "first.docx" in text
    assert "second.docx" in text
    assert "postmark://uploaded/first.md" in text
    assert "postmark://uploaded/second.md" in text

    # The listed URI resolves on retry.
    text, is_error = _observation_text(
        DocumentImportAction(uri="postmark://uploaded/second.md", chunk=1), session_id
    )
    assert not is_error
    assert "second.docx" in text


def test_current_message_attachment_wins_without_uri(tmp_path: Path) -> None:
    """A PDF attached earlier must not block reading the docx just attached.

    This is the real failure: the user attaches a second document and says
    "import this" — the model omits ``uri`` as instructed, and the read must
    land on the new file, not error as ambiguous.
    """
    from docx import Document

    session_id = uuid4().hex
    uris: list[str] = []
    for name in ("old-spec.docx", "new-guide.docx"):
        document = Document()
        document.add_paragraph(f"1. Endpoint in {name}")
        source = tmp_path / name
        document.save(str(source))
        uris.extend(entry["uri"] for entry in store_attachments(session_id, [str(source)]))

    # The second message attached new-guide.docx; the tool call omits uri.
    set_turn_attachments(session_id, [uris[1]])
    text, is_error = _observation_text(DocumentImportAction(chunk=1), session_id)
    assert not is_error
    assert "new-guide.docx" in text
    assert "old-spec.docx" not in text

    # A follow-up message with no attachment clears the preference; the model
    # still has the uri from earlier chunk headers, and the error lists both.
    set_turn_attachments(session_id, [])
    text, is_error = _observation_text(DocumentImportAction(chunk=1), session_id)
    assert is_error
    assert "ambiguous_attachment" in text


def test_earlier_document_stays_readable_by_uri(tmp_path: Path) -> None:
    """PDF first, DOCX second, then "back to the PDF" — the old file still reads.

    The follow-up message has no attachment, so the turn preference is empty;
    the model passes the PDF's URI from the transcript (chunk headers and the
    original message both carry it) and the read lands on the right document.
    """
    from docx import Document

    session_id = uuid4().hex
    uris: list[str] = []
    for name in ("first-spec.docx", "second-guide.docx"):
        document = Document()
        document.add_paragraph(f"1. Endpoint in {name}")
        source = tmp_path / name
        document.save(str(source))
        uris.extend(entry["uri"] for entry in store_attachments(session_id, [str(source)]))

    # Turn 2 attached the docx — uri-less reads go there.
    set_turn_attachments(session_id, [uris[1]])
    text, is_error = _observation_text(DocumentImportAction(chunk=1), session_id)
    assert not is_error
    assert "second-guide.docx" in text

    # Turn 3 attaches nothing and asks about the first document again.
    set_turn_attachments(session_id, [])
    text, is_error = _observation_text(DocumentImportAction(uri=uris[0], chunk=1), session_id)
    assert not is_error
    assert "first-spec.docx" in text


def test_two_documents_in_one_message_are_listed_for_choice(tmp_path: Path) -> None:
    """PDF + DOCX attached together: no silent pick — both are offered by URI.

    The model sees both URIs in that same message's trailer, so the error is a
    nudge to read them one at a time, not a dead end.
    """
    from docx import Document

    session_id = uuid4().hex
    uris: list[str] = []
    for name in ("alpha.docx", "beta.docx"):
        document = Document()
        document.add_paragraph(f"1. Endpoint in {name}")
        source = tmp_path / name
        document.save(str(source))
        uris.extend(entry["uri"] for entry in store_attachments(session_id, [str(source)]))

    # Both arrived with the current message — no single "current" document.
    set_turn_attachments(session_id, uris)
    text, is_error = _observation_text(DocumentImportAction(chunk=1), session_id)
    assert is_error
    assert "ambiguous_attachment" in text
    assert "alpha.docx" in text
    assert "beta.docx" in text

    # Each one reads fine once the model passes its URI from the trailer.
    for uri, name in zip(uris, ("alpha.docx", "beta.docx"), strict=True):
        text, is_error = _observation_text(DocumentImportAction(uri=uri, chunk=1), session_id)
        assert not is_error
        assert name in text


def test_reattaching_the_same_file_does_not_duplicate(tmp_path: Path) -> None:
    """Re-sending the same document must not make single-reference reads ambiguous."""
    from docx import Document

    document = Document()
    document.add_paragraph("1. Endpoint list")
    source = tmp_path / "spec.docx"
    document.save(str(source))

    session_id = uuid4().hex
    first = store_attachments(session_id, [str(source)])
    second = store_attachments(session_id, [str(source)])
    assert len(list_attachments(session_id)) == 1
    assert second[0]["uri"] == first[0]["uri"]

    text, is_error = _observation_text(DocumentImportAction(chunk=1), session_id)
    assert not is_error
    assert "ambiguous_attachment" not in text


def test_first_chunk_reports_progress_and_next_step(uploaded: tuple[str, str]) -> None:
    """Chunk 1 carries content, a counter, and an instruction to keep reading."""
    session_id, uri = uploaded
    text, is_error = _observation_text(DocumentImportAction(uri=uri, chunk=1), session_id)
    assert not is_error
    assert "chunk: 1 of " in text
    assert "1. Endpoint 1" in text
    assert "postmark_collection_draft" in text
    assert "read chunk=2" in text
    assert len(text) < MAX_CHUNK_CHARS * 2


def test_final_chunk_asks_for_finish(uploaded: tuple[str, str]) -> None:
    """The last chunk tells the agent to finish the draft rather than read on."""
    session_id, uri = uploaded
    first, _ = _observation_text(DocumentImportAction(uri=uri, chunk=1), session_id)
    total = int(first.split("chunk: 1 of ")[1].split("\n")[0])
    assert total > 1, "fixture should span several chunks"

    text, is_error = _observation_text(DocumentImportAction(uri=uri, chunk=total), session_id)
    assert not is_error
    assert f"chunk: {total} of {total}" in text
    assert "operation=finish" in text
    assert "read chunk=" not in text


def test_chunks_cover_the_whole_document(uploaded: tuple[str, str]) -> None:
    """Reading every chunk in order surfaces the first and last endpoint."""
    session_id, uri = uploaded
    first, _ = _observation_text(DocumentImportAction(uri=uri, chunk=1), session_id)
    total = int(first.split("chunk: 1 of ")[1].split("\n")[0])
    combined = "".join(
        _observation_text(DocumentImportAction(uri=uri, chunk=number), session_id)[0]
        for number in range(1, total + 1)
    )
    assert "1. Endpoint 1" in combined
    assert "39. Endpoint 39" in combined


def test_uri_may_be_omitted_for_a_single_upload(uploaded: tuple[str, str]) -> None:
    """A lone attachment is read without the model repeating its URI."""
    session_id, _ = uploaded
    text, is_error = _observation_text(DocumentImportAction(chunk=1), session_id)
    assert not is_error
    assert "chunk: 1 of " in text


def test_uri_inside_prose_still_resolves(uploaded: tuple[str, str]) -> None:
    """A URI wrapped in a markdown link resolves to the same upload."""
    session_id, uri = uploaded
    text, is_error = _observation_text(
        DocumentImportAction(uri=f"[the spec]({uri})", chunk=1), session_id
    )
    assert not is_error
    assert "chunk: 1 of " in text


def test_chunk_beyond_the_end_errors(uploaded: tuple[str, str]) -> None:
    """Reading past the final chunk is a clear error, not silent emptiness."""
    session_id, uri = uploaded
    text, is_error = _observation_text(DocumentImportAction(uri=uri, chunk=999), session_id)
    assert is_error
    assert "bad_chunk" in text


def test_unknown_uri_uses_the_only_unambiguous_upload(uploaded: tuple[str, str]) -> None:
    """A damaged echoed URI must not derail a chat with one attachment."""
    session_id, _ = uploaded
    text, is_error = _observation_text(
        DocumentImportAction(uri="postmark://uploaded/other.md", chunk=1), session_id
    )
    assert not is_error
    assert "chunk: 1 of " in text


def test_no_uploads_errors() -> None:
    """A session with no attachment is told to ask the user for one."""
    text, is_error = _observation_text(DocumentImportAction(chunk=1), uuid4().hex)
    assert is_error
    assert "no_uploads" in text


def test_unattached_path_is_uploaded_on_demand(tmp_path: Path) -> None:
    """A path the user named but did not attach is uploaded and chunked."""
    from docx import Document

    document = Document()
    document.add_paragraph("1. Named endpoint")
    source = tmp_path / "named.docx"
    document.save(str(source))

    text, is_error = _observation_text(DocumentImportAction(path=str(source), chunk=1), uuid4().hex)
    assert not is_error
    assert "Named endpoint" in text


def test_vision_model_receives_the_chunk_s_screenshots(
    uploaded_with_screenshot: tuple[str, str],
) -> None:
    """A vision model gets the image itself, not only the recognised text."""
    session_id, uri = uploaded_with_screenshot
    set_session_vision(session_id, True)
    conversation = SimpleNamespace(state=SimpleNamespace(id=session_id, persistence_dir=None))
    obs = DocumentImportExecutor()(DocumentImportAction(uri=uri, chunk=1), cast(Any, conversation))

    images = [part for part in obs.content if isinstance(part, ImageContent)]
    assert len(images) == 1
    assert images[0].image_urls[0].startswith("data:image/png;base64,")
    assert "screenshots: 1 attached" in obs.text


def test_vision_model_is_not_given_recognised_text(
    uploaded_with_screenshot: tuple[str, str],
) -> None:
    """OCR is the fallback for models that cannot see; vision models read the image."""
    session_id, uri = uploaded_with_screenshot
    set_session_vision(session_id, True)
    conversation = SimpleNamespace(state=SimpleNamespace(id=session_id, persistence_dir=None))
    obs = DocumentImportExecutor()(DocumentImportAction(uri=uri, chunk=1), cast(Any, conversation))

    assert "read as text" not in obs.text
    assert "```text" not in obs.text
    images_dir = Path(list_attachments(session_id)[0]["images_dir"])
    assert not (images_dir / OCR_CACHE_NAME).exists(), "OCR must not run for a vision model"


def test_non_vision_model_receives_recognised_text_instead(
    uploaded_with_screenshot: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A text-only model cannot use images, so the screenshot is read for it."""
    session_id, uri = uploaded_with_screenshot
    set_session_vision(session_id, False)
    monkeypatch.setattr(
        "services.ai.chat.attachments.screenshots.ocr_image_png",
        lambda _png: "POST /v1/search",
    )
    conversation = SimpleNamespace(state=SimpleNamespace(id=session_id, persistence_dir=None))
    obs = DocumentImportExecutor()(DocumentImportAction(uri=uri, chunk=1), cast(Any, conversation))

    assert not any(isinstance(part, ImageContent) for part in obs.content)
    assert "POST /v1/search" in obs.text
    assert "read as text" in obs.text


def test_action_preview_names_the_document_and_chunk() -> None:
    """Cards show the document name and which chunk is being read."""
    action = DocumentImportAction(uri="postmark://uploaded/spec.md", chunk=3)
    assert action.human_preview() == "spec.md (chunk 3)"


def test_action_preview_uses_turn_attachment_original_name() -> None:
    """When uri is omitted, the card uses the original upload filename."""
    set_turn_attachments(
        "turn-label-session",
        ["postmark://uploaded/1_Hotel_Guide.md"],
        names=["1 Hotel Implementation Guide_V12.0.docx"],
    )
    try:
        action = DocumentImportAction(chunk=1)
        assert action.display_name() == "1 Hotel Implementation Guide_V12.0.docx"
        assert action.human_preview() == "1 Hotel Implementation Guide_V12.0.docx (chunk 1)"
    finally:
        set_turn_attachments("turn-label-session", [])


def test_read_only_no_confirmation() -> None:
    """Document import is read-only and has no Approve kind."""
    assert kind_from_tool_args(DOCUMENT_IMPORT_TOOL_NAME) is None


def test_registered_in_default_agent() -> None:
    """Default agent exposes postmark_document_import."""
    defn = get_agent_def(DEFAULT_AGENT_ID)
    assert DOCUMENT_IMPORT_TOOL_NAME in defn.tool_names
