"""Compact file chips shown at the top of a user transcript bubble.

Uploads travel in the prompt as a composed ``Attached files:`` trailer, but the
bubble should read as the user's request plus what they attached — never as a
dump of internal ``postmark://`` URIs. This row renders each attachment parsed
from that trailer as a glanceable chip (type icon, filename, size), so the raw
references stay in the message data for the model and edit/fork while the UI
shows a human filename.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.sidebar.ai.chat_panel.composer.attachments import PromptAttachment
from ui.styling.icons import phi
from ui.styling.theme import COLOR_TEXT_MUTED

_CHIP_ICON_SIZE = 13
_CHIP_NAME_MAX_WIDTH_PX = 200

_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"})
_TEXT_SUFFIXES = frozenset({".doc", ".docx", ".md", ".txt", ".rtf", ".odt"})


def _icon_name_for(filename: str) -> str:
    """Return the Phosphor glyph that best matches *filename*'s extension."""
    lowered = filename.lower()
    suffix = "." + lowered.rsplit(".", 1)[-1] if "." in lowered else ""
    if suffix == ".pdf":
        return "file-pdf"
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in _TEXT_SUFFIXES:
        return "file-text"
    return "file"


def format_attachment_size(size_bytes: int) -> str:
    """Return a short human size for a chip, e.g. ``2.4 MB`` or ``612 KB``."""
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    if size_bytes >= 1_000:
        return f"{round(size_bytes / 1_000)} KB"
    return f"{size_bytes} B"


class _AttachmentChip(QFrame):
    """One read-only file chip: type icon, elided name, optional size."""

    clicked = Signal(str)

    def __init__(self, attachment: PromptAttachment, size_bytes: int | None) -> None:
        """Build a chip for *attachment* with an optional byte size label."""
        super().__init__()
        self.setObjectName("aiChatUserAttachmentChip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(attachment.reference)
        self._reference = attachment.reference

        row = QHBoxLayout(self)
        row.setContentsMargins(7, 3, 8, 3)
        row.setSpacing(6)

        icon = QLabel(self)
        icon.setObjectName("aiChatUserAttachmentChipIcon")
        icon.setPixmap(
            phi(
                _icon_name_for(attachment.name), color=COLOR_TEXT_MUTED, size=_CHIP_ICON_SIZE
            ).pixmap(_CHIP_ICON_SIZE, _CHIP_ICON_SIZE)
        )
        icon.setFixedSize(_CHIP_ICON_SIZE, _CHIP_ICON_SIZE)
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)

        name = QLabel(self)
        name.setObjectName("aiChatUserAttachmentChipName")
        metrics = name.fontMetrics()
        name.setText(
            metrics.elidedText(
                attachment.name, Qt.TextElideMode.ElideMiddle, _CHIP_NAME_MAX_WIDTH_PX
            )
        )
        row.addWidget(name, 0, Qt.AlignmentFlag.AlignVCenter)

        if size_bytes is not None:
            size = QLabel(format_attachment_size(size_bytes), self)
            size.setObjectName("aiChatUserAttachmentChipSize")
            row.addWidget(size, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit the attachment reference on a left-button click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._reference)
            event.accept()
            return
        super().mousePressEvent(event)

    def reference(self) -> str:
        """Return the stored attachment reference this chip represents."""
        return self._reference


class UserMessageAttachmentRow(QWidget):
    """Chip row rendered above the prompt text in a user transcript bubble."""

    attachment_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an empty hidden chip row."""
        super().__init__(parent)
        self.setObjectName("aiChatUserAttachments")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        # Bottom inset creates the gap between the chips and the hairline border
        # painted at the row's edge (QSS padding does not affect layout).
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(0)
        self._chips_host = QWidget(self)
        chips_layout = QHBoxLayout(self._chips_host)
        chips_layout.setContentsMargins(0, 0, 0, 0)
        chips_layout.setSpacing(6)
        chips_layout.addStretch(1)
        layout.addWidget(self._chips_host)
        self.hide()

    def set_attachments(
        self,
        attachments: list[PromptAttachment],
        sizes: dict[str, int],
    ) -> None:
        """Rebuild the chips for *attachments*, hiding the row when empty."""
        host_layout = self._chips_host.layout()
        assert isinstance(host_layout, QHBoxLayout)
        while host_layout.count() > 1:
            item = host_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for attachment in attachments:
            chip = _AttachmentChip(attachment, sizes.get(attachment.reference))
            chip.clicked.connect(self.attachment_clicked.emit)
            host_layout.insertWidget(host_layout.count() - 1, chip)
        self.setVisible(bool(attachments))


__all__ = ["UserMessageAttachmentRow", "format_attachment_size"]
__all__ = ["UserMessageAttachmentRow", "format_attachment_size"]
