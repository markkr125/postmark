"""``pm.test`` / ``pm.test.skip`` helpers for the RestrictedPython sandbox."""

from __future__ import annotations

import time
from typing import Any


class _SkipTest(Exception):
    """Raised by inline ``ctx.skip()`` to short-circuit a ``pm.test`` body."""


class _PmTestCallable:
    """``pm.test(...)`` callable + ``pm.test.skip(...)`` companion."""

    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def __call__(self, name: str, fn: Any) -> None:
        start = time.time()
        result: dict[str, Any] = {
            "name": str(name),
            "passed": True,
            "error": None,
            "duration_ms": 0.0,
        }
        skip_marker = {"hit": False}

        class _Ctx:
            def skip(self_inner) -> None:
                skip_marker["hit"] = True
                raise _SkipTest()

        try:
            try:
                fn(_Ctx())
            except TypeError:
                fn()
        except _SkipTest:
            result["passed"] = True
            result["skipped"] = True
        except Exception as e:
            result["passed"] = False
            result["error"] = str(e)
        if skip_marker["hit"]:
            result["skipped"] = True
        result["duration_ms"] = (time.time() - start) * 1000
        src = getattr(self._owner, "_test_source_name", None)
        if src:
            result["source_name"] = str(src)
        self._owner._test_results.append(result)

    def skip(self, name: str, _fn: Any = None) -> None:
        self._owner._test_results.append(
            {
                "name": str(name),
                "passed": True,
                "skipped": True,
                "error": None,
                "duration_ms": 0.0,
            }
        )
