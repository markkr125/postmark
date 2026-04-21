"""Detect advanced JavaScript features that require the Deno runtime.

Scans script text for ``async``/``await`` keywords and ``npm:`` import
patterns.  Returns a set of feature tags (e.g. ``{"async", "npm"}``)
or an empty set when the script can run on MiniRacer.

This is a lightweight heuristic — it uses regex scanning, not a full
parser.  False positives (e.g. ``async`` inside a string literal) are
acceptable because they only trigger a non-blocking banner, never a
runtime failure.
"""

from __future__ import annotations

import re

# -- Feature patterns --------------------------------------------------

# ``async`` keyword: async function, async () =>, async (x) =>
# Anchored to word boundary to avoid matching e.g. "asyncStorage".
_ASYNC_RE = re.compile(
    r"""
    \basync\s+function\b     # async function ...
    | \basync\s*\(           # async (...) =>
    | \bawait\s+             # await expression
    """,
    re.VERBOSE,
)

# Deno-style npm imports: require("npm:...") or import ... from "npm:..."
_NPM_REQUIRE_RE = re.compile(r"""require\s*\(\s*['"]npm:""")
_NPM_IMPORT_RE = re.compile(r"""from\s+['"]npm:""")

# Feature tag constants.
FEATURE_ASYNC = "async"
FEATURE_NPM = "npm"


def detect_advanced_features(script: str, language: str = "javascript") -> set[str]:
    """Return a set of advanced feature tags found in *script*.

    Only JavaScript scripts are scanned — Python scripts always return
    an empty set (the Python runtime handles async natively).

    Possible tags:

    - ``"async"`` — script uses ``async``/``await``
    - ``"npm"`` — script uses ``require("npm:...")`` or
      ``import ... from "npm:..."``
    """
    if language != "javascript" or not script or not script.strip():
        return set()

    features: set[str] = set()

    if _ASYNC_RE.search(script):
        features.add(FEATURE_ASYNC)

    if _NPM_REQUIRE_RE.search(script) or _NPM_IMPORT_RE.search(script):
        features.add(FEATURE_NPM)

    return features
