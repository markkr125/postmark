"""PNG normalization, optional OCR, and collection of embedded document images."""

from __future__ import annotations

import base64
import hashlib
import logging
import threading
from io import BytesIO

from PIL import Image

from services.document_import.models import (
    ExtractedBlock,
    ExtractedImage,
    image_cap_warning,
    image_is_too_small,
    repeated_image_warning,
    tiny_image_warning,
)

_engine = None
_engine_lock = threading.Lock()
_OCR_LOGGER_NAME = "RapidOCR"


def normalize_png(data: bytes) -> tuple[bytes, int, int]:
    """Re-encode arbitrary image bytes to PNG and return dimensions."""
    img = Image.open(BytesIO(data)).convert("RGB")
    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue(), img.width, img.height


def ocr_image_png(png_bytes: bytes) -> str:
    """Run local OCR when the ``ocr`` extra is installed; else return empty text.

    OCR is optional: without it, screenshots are only usable by vision models,
    so a missing engine degrades to empty text rather than failing the import.
    """
    global _engine
    with _engine_lock:
        if _engine is None:
            try:
                from rapidocr import RapidOCR

                logging.getLogger(_OCR_LOGGER_NAME).setLevel(logging.WARNING)
                _engine = RapidOCR()
            except Exception:
                return ""
        try:
            result = _engine(png_bytes)
        except Exception:
            return ""
    return "\n".join(getattr(result, "txts", None) or ())


class ImageCollector:
    """Accumulate document images, dropping page furniture and duplicates.

    API specs repeat a logo on every page; emitting each copy wastes the image
    budget and floods the observation with identical OCR text, so repeats
    collapse into their first occurrence.
    """

    def __init__(self, *, max_images: int, run_ocr: bool) -> None:
        """Start an empty collector bound to *max_images*."""
        self.images: list[ExtractedImage] = []
        self.warnings: list[str] = []
        self._max_images = max_images
        self._run_ocr = run_ocr
        self._digests: set[str] = set()
        self._repeats = 0
        self._tiny = 0
        self._cap_warned = False

    def at_capacity(self) -> bool:
        """Return True once the image cap is reached, warning once."""
        if len(self.images) < self._max_images:
            return False
        if not self._cap_warned:
            self.warnings.append(image_cap_warning(self._max_images))
            self._cap_warned = True
        return True

    def add(self, raw: bytes, *, page: int, label: str = "") -> ExtractedBlock | None:
        """Normalize and record one image, returning its block when kept."""
        if self.at_capacity():
            return None
        try:
            png_bytes, width, height = normalize_png(raw)
        except Exception:
            self.warnings.append(f"Skipped unreadable image {label or f'on page {page}'}".strip())
            return None
        if image_is_too_small(width, height):
            self._tiny += 1
            return None
        digest = hashlib.sha256(png_bytes).hexdigest()
        if digest in self._digests:
            self._repeats += 1
            return None
        self._digests.add(digest)
        image_index = len(self.images)
        self.images.append(
            {
                "index": image_index,
                "page": page,
                "mime": "image/png",
                "data_b64": base64.b64encode(png_bytes).decode("ascii"),
                "ocr_text": ocr_image_png(png_bytes) if self._run_ocr else "",
                "width": width,
                "height": height,
            }
        )
        return {"kind": "image", "page": page, "image_index": image_index}

    def finalize_warnings(self) -> list[str]:
        """Return collected warnings, including the collapsed-repeat summary."""
        warnings = list(self.warnings)
        if self._repeats:
            warnings.append(repeated_image_warning(self._repeats))
        if self._tiny:
            warnings.append(tiny_image_warning(self._tiny))
        return warnings


__all__ = ["ImageCollector", "normalize_png", "ocr_image_png"]
