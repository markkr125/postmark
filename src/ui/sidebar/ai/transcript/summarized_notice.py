"""Muted transcript row shown after the first OpenHands compaction in a session."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

_NOTICE_TEXT = (
    "Earlier messages were summarized to free context. The assistant may not recall them verbatim."
)


def make_summarized_notice(parent: QWidget) -> QWidget:
    """Build a non-dismissible muted notice row for the transcript."""
    row = QWidget(parent)
    row.setObjectName("aiChatSummarizedNotice")
    layout = QVBoxLayout(row)
    layout.setContentsMargins(0, 4, 0, 4)
    layout.setSpacing(0)
    label = QLabel(_NOTICE_TEXT)
    label.setObjectName("mutedLabel")
    label.setWordWrap(True)
    layout.addWidget(label)
    return row


def find_summarized_notice(messages_host: QWidget) -> QWidget | None:
    """Return an existing summarized notice under *messages_host*, if any."""
    for child in messages_host.findChildren(QWidget):
        if child.objectName() == "aiChatSummarizedNotice":
            return child
    return None
