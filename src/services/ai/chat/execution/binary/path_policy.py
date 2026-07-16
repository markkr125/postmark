"""Path allowlist for Agent binary body paths (mutate + send)."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

from database.data_paths import postmark_user_data_dir, project_root

_SENSITIVE_NAME_PARTS = frozenset(
    {
        ".env",
        ".ssh",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "credentials",
        "secrets",
    }
)


def _allowed_roots() -> list[Path]:
    """Return resolved roots under which binary paths may live."""
    roots: list[Path] = []
    for candidate in (
        postmark_user_data_dir(),
        project_root() / "data",
        Path(tempfile.gettempdir()),
    ):
        try:
            roots.append(candidate.resolve())
        except OSError:
            continue
    # Pytest / CI tmp often under /tmp already; also allow TMPDIR if distinct.
    tmpdir = os.environ.get("TMPDIR") or os.environ.get("TMP")
    if tmpdir:
        with contextlib.suppress(OSError):
            roots.append(Path(tmpdir).resolve())
    return roots


def _is_under(path: Path, root: Path) -> bool:
    """Return whether *path* is equal to or under *root*."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _has_sensitive_segment(path: Path) -> bool:
    """Return whether any path segment looks like a secret store."""
    for part in path.parts:
        lowered = part.casefold()
        if lowered in _SENSITIVE_NAME_PARTS:
            return True
        if lowered.startswith(".env"):
            return True
    return False


def validate_binary_path(path_str: str) -> tuple[Path | None, str | None]:
    """Validate an Agent binary body path against the allowlist.

    Returns ``(resolved_path, None)`` or ``(None, error_code)``.
    """
    text = (path_str or "").strip()
    if not text:
        return None, "empty_binary_path"
    # Reject path traversal tokens before resolve.
    if ".." in Path(text).parts:
        return None, "binary_path_traversal"
    try:
        resolved = Path(text).expanduser().resolve(strict=False)
    except OSError:
        return None, "invalid_binary_path"
    if _has_sensitive_segment(resolved):
        return None, "binary_path_sensitive"
    # Hard reject absolute sensitive roots even if somehow under allowlist.
    home = Path.home()
    for blocked in (home / ".ssh", Path("/etc"), Path("/root")):
        try:
            blocked_r = blocked.resolve()
        except OSError:
            continue
        if _is_under(resolved, blocked_r) or resolved == blocked_r:
            return None, "binary_path_forbidden"
    if not any(_is_under(resolved, root) for root in _allowed_roots()):
        return None, "binary_path_not_allowed"
    return resolved, None


def is_binary_path_allowed(path_str: str) -> bool:
    """Return whether *path_str* passes the Agent binary path policy."""
    path, err = validate_binary_path(path_str)
    return path is not None and err is None
