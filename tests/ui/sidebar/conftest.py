"""Shared fixtures and marks for right/left sidebar UI tests."""

from __future__ import annotations

import pytest

# Serialize all sidebar Qt tests on one xdist worker so they do not contend with
# RestrictedPython subprocess sandboxes, Deno LSP, or other heavy parallel suites
# (reduces intermittent SIGABRT / OOM under ``pytest -n auto``).
pytestmark = pytest.mark.xdist_group("sidebar_qt")
