"""Shared fixtures for request and response editor UI tests."""

from __future__ import annotations

from typing import Any

import pytest

from services.collection_service import RequestLoadDict


@pytest.fixture()
def make_request_dict():
    """Factory that builds a :class:`RequestLoadDict` with sane defaults.

    Override any key via keyword argument::

        data = make_request_dict(method="POST", body='{"x": 1}')
    """

    def _make(**overrides: Any) -> RequestLoadDict:
        base: RequestLoadDict = {
            "name": "X",
            "method": "GET",
            "url": "http://x",
        }
        return {**base, **overrides}  # type: ignore[typeddict-item]

    return _make
