"""Resolve binary request bodies from filesystem paths."""

from __future__ import annotations

from pathlib import Path

from services.history_retention_config import (
    DEFAULT_MAX_RESPONSE_BYTES,
    load_history_retention_config,
)

# Cap binary uploads at the same ceiling as history response storage.
DEFAULT_BINARY_MAX_BYTES = DEFAULT_MAX_RESPONSE_BYTES


def binary_upload_max_bytes() -> int:
    """Return the max binary upload size (history max_response_bytes)."""
    try:
        return load_history_retention_config().max_response_bytes
    except Exception:
        return DEFAULT_BINARY_MAX_BYTES


def resolve_binary_body_bytes(
    path_str: str,
    *,
    max_bytes: int | None = None,
) -> tuple[bytes | None, str | None]:
    """Read file bytes for a binary body path.

    Returns ``(content, None)`` on success or ``(None, error_message)`` on failure.
    Does not enforce agent path allowlists — callers that need policy must validate first.
    """
    text = (path_str or "").strip()
    if not text:
        return None, "Binary body path is empty"
    path = Path(text).expanduser()
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        return None, f"Invalid binary body path: {exc}"
    if not resolved.is_file():
        return None, f"Binary body file not found: {resolved}"
    limit = max_bytes if max_bytes is not None else binary_upload_max_bytes()
    try:
        size = resolved.stat().st_size
    except OSError as exc:
        return None, f"Cannot stat binary body file: {exc}"
    if size > limit:
        return None, f"Binary body exceeds size limit ({size} > {limit} bytes)"
    try:
        return resolved.read_bytes(), None
    except OSError as exc:
        return None, f"Cannot read binary body file: {exc}"
