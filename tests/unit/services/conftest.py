"""Unit service test fixtures."""

from __future__ import annotations

import fcntl
from collections.abc import Generator
from pathlib import Path

import pytest

_SANDBOX_LOCK_PATH = Path("/tmp/postmark_restricted_python_sandbox.lock")


def _module_uses_restricted_sandbox(module: object) -> bool:
    """Return True when *module* marks all tests with ``restricted_python_sandbox``."""
    mark = getattr(module, "pytestmark", None)
    if mark is None:
        return False
    marks = mark if isinstance(mark, list | tuple) else [mark]
    for item in marks:
        if item.name != "xdist_group":
            continue
        args = item.args or ()
        name = item.kwargs.get("name")
        if "restricted_python_sandbox" in args or name == "restricted_python_sandbox":
            return True
    return False


@pytest.fixture(autouse=True)
def _serialize_restricted_python_sandbox(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Hold a cross-worker lock while RestrictedPython subprocess tests run.

    ``--dist loadfile`` can place ``test_script_sandbox.py`` and
    ``test_pm_python_parity.py`` on different xdist workers; without a lock
    both spawn memory-heavy sandboxes at once and the host OOM killer returns
    exit code -9.
    """
    module = request.module
    if module is None or not _module_uses_restricted_sandbox(module):
        yield
        return

    _SANDBOX_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _SANDBOX_LOCK_PATH.open("w") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
