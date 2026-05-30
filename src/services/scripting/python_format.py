"""Format Python source via Ruff (jedi-language-server has no formatter)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from services.scripting.runtime_settings import RuntimeSettings


def _resolve_ruff_format_argv() -> list[str] | None:
    """Return argv prefix ``[..., 'format']`` or ``None`` when Ruff is unavailable."""
    bin_path = shutil.which("ruff")
    if bin_path:
        return [bin_path, "format"]
    py = RuntimeSettings.python_path()
    try:
        probe = subprocess.run(
            [py, "-m", "ruff", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if probe.returncode != 0:
        return None
    return [py, "-m", "ruff", "format"]


def format_python_source(source: str) -> str | None:
    """Run ``ruff format`` on *source*; return formatted text or ``None`` on failure."""
    argv = _resolve_ruff_format_argv()
    if argv is None or not source.strip():
        return None
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as fh:
            fh.write(source)
            if not source.endswith("\n"):
                fh.write("\n")
            path = Path(fh.name)
        proc = subprocess.run(
            [*argv, str(path)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode != 0:
            return None
        out = path.read_text(encoding="utf-8")
        return out.rstrip("\n") if not source.endswith("\n") else out
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        if path is not None:
            path.unlink(missing_ok=True)
