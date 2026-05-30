"""Format script runtime errors for the output panel."""

from __future__ import annotations

import re

_SCRIPT_LINE_RE = re.compile(r'File "<script>", line (\d+), in .+')


def format_script_runtime_error(error: str) -> str:
    """Return a concise, user-facing script error string."""
    text = (error or "").strip()
    if not text:
        return text

    if "pm.response is not available" in text:
        for line in text.splitlines():
            if "pm.response is not available" in line:
                msg = line.strip()
                if msg.startswith("AttributeError:"):
                    msg = msg.removeprefix("AttributeError:").strip()
                return msg

    script_lines = [ln.strip() for ln in text.splitlines() if _SCRIPT_LINE_RE.search(ln)]
    last = text.splitlines()[-1].strip() if text.splitlines() else ""
    if script_lines and last:
        return f"{script_lines[-1]}\n{last}"
    return text
