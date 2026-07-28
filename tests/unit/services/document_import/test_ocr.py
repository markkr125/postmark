"""Tests for PNG normalization and OCR helpers."""

from __future__ import annotations

import builtins
import importlib.util
import sys
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from services.document_import import ocr


def test_normalize_png_returns_dimensions() -> None:
    """normalize_png re-encodes bytes and returns width/height."""
    img = Image.new("RGB", (3, 5), color="blue")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    png_bytes, width, height = ocr.normalize_png(buf.getvalue())
    assert width == 3
    assert height == 5
    assert png_bytes.startswith(b"\x89PNG")


def test_ocr_empty_when_engine_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """OCR returns empty text when rapidocr cannot be imported."""
    real_import = builtins.__import__

    def _block_rapidocr(
        name: str,
        globals: dict | None = None,
        locals: dict | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ):  # type: ignore[no-untyped-def]
        if name == "rapidocr":
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_rapidocr)
    monkeypatch.setattr(ocr, "_engine", None, raising=False)
    assert ocr.ocr_image_png(b"not-a-png") == ""


@pytest.mark.skipif(
    "rapidocr" not in sys.modules and importlib.util.find_spec("rapidocr") is None,
    reason="rapidocr optional extra not installed",
)
def test_ocr_reads_text_from_a_screenshot() -> None:
    """OCR must actually transcribe a screenshot, not just return a string.

    Screenshot-only request/response examples are the point of the ocr extra,
    so this asserts the adapter matches the installed engine's result shape.
    """
    img = Image.new("RGB", (420, 90), color="white")
    ImageDraw.Draw(img).text((10, 35), "POST /v1/booking", fill="black")
    buf = BytesIO()
    img.save(buf, format="PNG")

    text = ocr.ocr_image_png(buf.getvalue())

    assert "booking" in text.lower()
