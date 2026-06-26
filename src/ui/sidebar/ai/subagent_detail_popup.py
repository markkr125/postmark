"""Read-only flyout for a completed or running subagent delegation."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QTextEdit, QWidget

from services.ai.chat.subagent_events import SubagentRunRecord
from services.ai.chat.subagent_transcript import load_subagent_transcript_preview
from ui.widgets.info_popup import InfoPopup


class SubagentDetailPopup(InfoPopup):
    """Drill-in popup showing subagent label, type, and result preview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build header + scrollable body."""
        super().__init__(parent)
        self.setObjectName("aiChatSubagentDetailPopup")

        self._title = QLabel()
        self._title.setObjectName("aiChatSubagentDetailTitle")
        self.content_layout.addWidget(self._title)

        self._meta = QLabel()
        self._meta.setObjectName("mutedLabel")
        self._meta.setWordWrap(True)
        self.content_layout.addWidget(self._meta)

        scroll = QScrollArea()
        scroll.setObjectName("aiChatSubagentDetailScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self._body = QTextEdit()
        self._body.setObjectName("aiChatSubagentDetailBody")
        self._body.setReadOnly(True)
        self._body.setFrameShape(QTextEdit.Shape.NoFrame)
        scroll.setWidget(self._body)
        self.content_layout.addWidget(scroll)

    def set_record(self, record: SubagentRunRecord) -> None:
        """Populate the popup from *record*."""
        self._title.setText(record["label"])
        status = record["status"]
        self._meta.setText(f"{record['subagent_type']} · {status}")
        parts: list[str] = []
        preview = record.get("result_preview", "")
        if preview:
            parts.append(preview)
        disk = record.get("disk_path")
        if disk:
            transcript = load_subagent_transcript_preview(disk)
            if transcript and transcript not in parts:
                parts.append(transcript)
        if not parts:
            parts.append("No subagent output captured yet.")
        self._body.setPlainText("\n\n".join(parts))


__all__ = ["SubagentDetailPopup"]
