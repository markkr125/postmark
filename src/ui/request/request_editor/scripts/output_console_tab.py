"""Console log row rendering for :class:`ScriptOutputPanel`'s Output tab.

Free helpers — the parent panel owns the scroll layout and calls
:func:`add_console_row` to insert each line.

Also exposes :func:`inline_log_annotations_from_console_logs` for the
editor inline-annotation feature (A4).
"""

from __future__ import annotations

import html
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from ui.styling.theme import COLOR_ACCENT, COLOR_DANGER, COLOR_WARNING


def inline_log_annotations_from_console_logs(
    logs: list[dict[str, Any]],
) -> dict[int, str]:
    """Group captured console lines by 0-based ``source_line`` for the editor."""
    by_line: dict[int, list[str]] = {}
    for log in logs:
        line = log.get("source_line")
        if not isinstance(line, int) or line < 0:
            continue
        msg = str(log.get("message", "")).strip()
        if not msg:
            continue
        by_line.setdefault(line, []).append(msg)
    return {ln: " · ".join(parts) for ln, parts in by_line.items()}


_LOG_COLORS: dict[str, str] = {
    "log": "",
    "info": COLOR_ACCENT,
    "warn": COLOR_WARNING,
    "error": COLOR_DANGER,
}


def add_console_row(panel: Any, log: dict[str, Any]) -> None:
    """Add a single console-log row to *panel*'s results layout."""
    level = log.get("level", "log")
    message = log.get("message", "")
    color = _LOG_COLORS.get(level, "")
    style = f"color:{color};" if color else ""

    prefix = ""
    if level == "warn":
        prefix = "\u26a0 "
    elif level == "error":
        prefix = "\u2716 "

    label = QLabel(f"<span style='{style}font-size:12px;'>{prefix}{html.escape(message)}</span>")
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setWordWrap(True)
    panel._insert_row(label)
