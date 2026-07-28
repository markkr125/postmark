"""Tests for serving an uploaded document's screenshots chunk by chunk."""

from __future__ import annotations

from base64 import b64decode
from pathlib import Path
from typing import cast

import pytest
from services.ai.chat.attachments.models import StoredAttachment
from services.ai.chat.attachments.screenshots import (
    MAX_CHUNK_IMAGES,
    OCR_CACHE_NAME,
    chunk_ocr_text,
    chunk_screenshots,
    clear_session_vision,
    image_numbers_in,
    session_supports_vision,
    set_session_vision,
)

# Smallest valid PNG; the bytes only need to round-trip.
_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def entry(tmp_path: Path) -> StoredAttachment:
    """Return a stored attachment whose images directory holds ten screenshots."""
    images = tmp_path / "images"
    images.mkdir()
    for number in range(1, 11):
        (images / f"image-{number}.png").write_bytes(_PNG)
    return cast(StoredAttachment, {"images_dir": str(images)})


def test_markers_are_read_in_order_without_repeats() -> None:
    """A screenshot referenced twice is still attached once."""
    text = "**[image 3]**\nsome text\n**[image 1]**\nmore\n**[image 3]**"
    assert image_numbers_in(text) == [3, 1]


def test_only_the_chunk_s_screenshots_are_attached(entry: StoredAttachment) -> None:
    """Attaching the whole document's images would defeat the point of chunking."""
    urls, skipped = chunk_screenshots(entry, "**[image 2]**\ntext\n**[image 4]**")
    assert len(urls) == 2
    assert skipped == 0
    assert all(url.startswith("data:image/png;base64,") for url in urls)


def test_a_chunk_without_screenshots_attaches_nothing(entry: StoredAttachment) -> None:
    """Text-only chunks cost nothing extra."""
    assert chunk_screenshots(entry, "just prose about GET /hotels") == ([], 0)


def test_images_are_capped_and_the_remainder_is_reported(entry: StoredAttachment) -> None:
    """Image tokens are expensive, so the count is bounded and the cut is visible."""
    markers = "\n".join(f"**[image {number}]**" for number in range(1, 11))
    urls, skipped = chunk_screenshots(entry, markers)
    assert len(urls) == MAX_CHUNK_IMAGES
    assert skipped == 10 - MAX_CHUNK_IMAGES


def test_a_missing_screenshot_file_is_skipped(entry: StoredAttachment) -> None:
    """A marker without bytes on disk must not break the read."""
    urls, skipped = chunk_screenshots(entry, "**[image 99]**\n**[image 1]**")
    assert len(urls) == 1
    assert skipped == 0


def test_an_upload_without_images_is_handled(tmp_path: Path) -> None:
    """Documents with no screenshots have no images directory."""
    empty = cast(StoredAttachment, {"images_dir": str(tmp_path / "absent")})
    assert chunk_screenshots(empty, "**[image 1]**") == ([], 0)


def test_recognised_text_is_placed_under_its_marker(
    entry: StoredAttachment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Text must land where the screenshot was, or the model cannot place it."""
    monkeypatch.setattr(
        "services.ai.chat.attachments.screenshots.ocr_image_png",
        lambda _png: "POST /v1/search",
    )
    text, count = chunk_ocr_text(entry, "intro\n\n**[image 2]**\n\noutro")
    assert count == 1
    assert text.index("**[image 2]**") < text.index("POST /v1/search") < text.index("outro")
    assert "```text" in text


def test_only_the_chunk_s_screenshots_are_recognised(
    entry: StoredAttachment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OCR is slow, so it runs for the images being read and no others."""
    seen: list[int] = []

    def _fake(png: bytes) -> str:
        seen.append(len(png))
        return "text"

    monkeypatch.setattr("services.ai.chat.attachments.screenshots.ocr_image_png", _fake)
    chunk_ocr_text(entry, "**[image 1]**\n**[image 2]**")
    assert len(seen) == 2


def test_recognised_text_is_cached_between_reads(
    entry: StoredAttachment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-reading a chunk must not pay for OCR twice."""
    calls: list[int] = []

    def _fake(png: bytes) -> str:
        calls.append(len(png))
        return "GET /v1/rates"

    monkeypatch.setattr("services.ai.chat.attachments.screenshots.ocr_image_png", _fake)
    first, _ = chunk_ocr_text(entry, "**[image 1]**")
    assert (Path(entry["images_dir"]) / OCR_CACHE_NAME).is_file()

    monkeypatch.setattr(
        "services.ai.chat.attachments.screenshots.ocr_image_png",
        lambda _png: pytest.fail("OCR ran again for a cached screenshot"),
    )
    second, count = chunk_ocr_text(entry, "**[image 1]**")
    assert len(calls) == 1
    assert count == 1
    assert second == first


def test_unreadable_screenshot_leaves_the_marker_alone(
    entry: StoredAttachment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the OCR extra there is no text; the chunk is still usable."""
    monkeypatch.setattr("services.ai.chat.attachments.screenshots.ocr_image_png", lambda _png: "")
    text, count = chunk_ocr_text(entry, "**[image 1]**")
    assert count == 0
    assert text == "**[image 1]**"


def test_vision_defaults_to_off_for_an_unknown_session() -> None:
    """Unknown capability must not send images to a model that cannot read them."""
    assert session_supports_vision("never-seen") is False


def test_vision_flag_round_trips_and_clears() -> None:
    """The flag follows the session's active model and is dropped with the session."""
    set_session_vision("sess-a", True)
    assert session_supports_vision("sess-a") is True
    set_session_vision("sess-a", False)
    assert session_supports_vision("sess-a") is False
    set_session_vision("sess-a", True)
    clear_session_vision("sess-a")
    assert session_supports_vision("sess-a") is False
