"""Variable-change section rendering for :class:`ScriptOutputPanel`."""

from __future__ import annotations

import html
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


def add_variable_section(panel: Any, changes: dict[str, str]) -> None:
    """Add a section showing variable changes from the script."""
    header = QLabel("<span style='font-weight:bold;font-size:12px;'>Variable changes</span>")
    header.setObjectName("mutedLabel")
    header.setTextFormat(Qt.TextFormat.RichText)
    header.setStyleSheet("padding-top: 6px;")
    panel._insert_row(header)

    for key, value in changes.items():
        row = QLabel(
            f"<span style='font-size:12px;'>"
            f"<b>{html.escape(str(key))}</b> = "
            f"{html.escape(str(value))}</span>"
        )
        row.setTextFormat(Qt.TextFormat.RichText)
        row.setWordWrap(True)
        panel._insert_row(row)
