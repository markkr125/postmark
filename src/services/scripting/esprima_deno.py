"""Run the vendored esprima.js via ``deno run data/scripts/esprima_parse.mjs``.

Used for :class:`ScriptLinter` and :func:`find_pm_tests` / ``find_top_level_statement_lines``
so the project does not depend on PyMiniRacer for parsing.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

from services.scripting.runtime_settings import RuntimeSettings

logger = logging.getLogger(__name__)

_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "data" / "scripts"
_PARSER = _SCRIPTS_DIR / "esprima_parse.mjs"
_SUBPARSE_TIMEOUT = 8.0


def esprima_parse_to_dict(script: str) -> dict[str, Any] | None:
    """Return parse JSON; ``None`` if Deno is missing or invocation fails."""
    st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
    if not st["available"]:
        return None
    deno = st["path"]
    if not _PARSER.is_file():
        return None
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".js",
        delete=False,
    ) as f:
        f.write(script)
        src_path = f.name
    try:
        r = subprocess.run(
            [
                deno,
                "run",
                f"--allow-read={_SCRIPTS_DIR}",
                f"--allow-read={Path(src_path).parent}",
                str(_PARSER),
                src_path,
            ],
            capture_output=True,
            text=True,
            timeout=_SUBPARSE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("esprima via Deno failed: %s", exc)
        return None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(src_path)

    if r.returncode != 0 and not (r.stdout or "").strip():
        return None
    out = (r.stdout or "").strip()
    if not out:
        return None
    try:
        return cast(dict[str, Any], json.loads(out))
    except json.JSONDecodeError:
        return None
