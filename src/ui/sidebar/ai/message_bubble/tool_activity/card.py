"""Compact inline tool-activity row in the assistant transcript.

Each row is a one-line summary (status, tool, detail, duration). When the tool
returns output, the row is clickable to expand a compact, word-wrapped panel
with human-readable observation text (errors, successes, warnings) — not the
raw machine ``key: value`` dump or a tall empty editor.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from services.ai.chat.tool_activity_events import ToolActivityRecord, ToolActivityStatus
from ui.sidebar.ai.message_bubble.tool_activity.format_output import (
    format_tool_activity_output,
)
from ui.styling.icons import phi
from ui.styling.theme import COLOR_DANGER, COLOR_SUCCESS
from ui.widgets.busy_spinner import BrailleSpinner

_STATUS_LABELS: dict[ToolActivityStatus, str] = {
    "pending_confirm": "Waiting",
    "running": "Running",
    "completed": "Completed",
    "error": "Failed",
    "rejected": "Rejected",
    "suppressed": "Done",
}

_TOOL_ICONS: dict[str, str] = {
    "postmark_workspace_query": "magnifying-glass",
    "postmark_datetime": "clock",
    "postmark_import": "download-simple",
    "postmark_workspace_import": "download-simple",
    "postmark_document_import": "file-text",
    "postmark_collection_draft": "folder-plus",
    "postmark_workspace_mutate": "pencil-simple",
    "postmark_workspace_execute": "paper-plane-right",
}

_TERMINAL_STATUSES = frozenset({"completed", "error", "rejected", "suppressed"})
_MAX_OUTPUT_HEIGHT_PX = 220
# Inner text padding (matches layout margins on the scroll content).
_OUTPUT_PAD_Y_PX = 16
_OUTPUT_PAD_X_PX = 20
# Outer frame border (1px top+bottom) so height includes the full radius.
_OUTPUT_BORDER_Y_PX = 2
# FontMetrics.boundingRect can under-report by a line's descent; keep slack.
_OUTPUT_HEIGHT_SLACK_PX = 6
# Fallback when the style reports no scrollbar extent yet.
_SCROLLBAR_FALLBACK_PX = 14


def _format_duration(seconds: float | None) -> str:
    """Return a short inline duration such as ``1.2s``, or empty when unknown."""
    if seconds is None or seconds < 0:
        return ""
    return f"{seconds:.1f}s" if seconds < 60 else f"{seconds / 60:.1f}m"


def _ellipsize(text: str, label: QLabel) -> str:
    """Return *text* elided to one line of the chat's content width."""
    width = max(200, label.width() or 400)
    return label.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, width)


class _ToolActivityHeader(QWidget):
    """Clickable summary row; toggles output expansion when output is available."""

    def __init__(self, card: ToolActivityCard) -> None:
        """Wire header clicks to *card* expansion."""
        super().__init__(card)
        self._card = card
        self.setObjectName("aiChatToolActivityHeader")

    def mousePressEvent(self, _event: object) -> None:
        """Toggle expansion when the row has output to show."""
        if self._card.can_expand():
            self._card.toggle_expanded()


class ToolActivityCard(QWidget):
    """One-line summary row for a single main-agent tool call."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build a hidden row until a record is applied."""
        super().__init__(parent)
        self.setObjectName("aiChatToolActivityCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._header = _ToolActivityHeader(self)
        header_row = QHBoxLayout(self._header)
        header_row.setContentsMargins(0, 1, 0, 1)
        header_row.setSpacing(8)

        self._expand_btn = QToolButton(self._header)
        self._expand_btn.setObjectName("aiChatToolActivityExpand")
        self._expand_btn.setArrowType(Qt.ArrowType.RightArrow)
        self._expand_btn.setAutoRaise(True)
        self._expand_btn.setCheckable(True)
        self._expand_btn.setFixedSize(16, 16)
        self._expand_btn.hide()
        self._expand_btn.toggled.connect(self._on_expand_toggled)
        header_row.addWidget(self._expand_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self._status_slot = QWidget(self._header)
        self._status_slot.setObjectName("aiChatToolActivityStatusSlot")
        self._status_slot.setFixedSize(14, 14)
        slot = QVBoxLayout(self._status_slot)
        slot.setContentsMargins(0, 0, 0, 0)
        slot.setSpacing(0)
        self._spinner = BrailleSpinner(self._status_slot)
        slot.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignCenter)
        self._status_icon = QLabel(self._status_slot)
        self._status_icon.setObjectName("aiChatToolActivityStatusIcon")
        self._status_icon.setFixedSize(14, 14)
        self._status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_icon.hide()
        slot.addWidget(self._status_icon, 0, Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(self._status_slot, 0, Qt.AlignmentFlag.AlignVCenter)

        self._title_icon = QLabel(self._header)
        self._title_icon.setObjectName("aiChatToolActivityTitleIcon")
        self._title_icon.setFixedSize(14, 14)
        self._title_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(self._title_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        self._title = QLabel(self._header)
        self._title.setObjectName("aiChatToolActivityTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._title.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        header_row.addWidget(self._title, 0, Qt.AlignmentFlag.AlignVCenter)

        self._detail = QLabel(self._header)
        self._detail.setObjectName("aiChatToolActivityDetail")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._detail.setFixedHeight(self._detail.fontMetrics().lineSpacing() + 2)
        header_row.addWidget(self._detail, 1, Qt.AlignmentFlag.AlignVCenter)

        self._duration = QLabel(self._header)
        self._duration.setObjectName("aiChatToolActivityDuration")
        self._duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._duration.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        header_row.addWidget(self._duration, 0, Qt.AlignmentFlag.AlignVCenter)

        root.addWidget(self._header)

        # Border lives on the outer frame so a scroll viewport never clips it.
        # Short errors hug content (no scrollbar); long bodies scroll inside.
        self._output_frame = QFrame(self)
        self._output_frame.setObjectName("aiChatToolActivityOutput")
        self._output_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._output_frame.setMaximumHeight(_MAX_OUTPUT_HEIGHT_PX)
        self._output_frame.hide()
        frame_layout = QVBoxLayout(self._output_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        self._output_scroll = QScrollArea(self._output_frame)
        self._output_scroll.setObjectName("aiChatToolActivityOutputScroll")
        self._output_scroll.setWidgetResizable(False)
        self._output_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._output_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._output_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        frame_layout.addWidget(self._output_scroll)

        self._output = QLabel()
        self._output.setObjectName("aiChatToolActivityOutputBody")
        self._output.setWordWrap(True)
        self._output.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._output.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._output.setContentsMargins(10, 8, 10, 8)
        self._output.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._output_scroll.setWidget(self._output)
        root.addWidget(self._output_frame)
        self._output_frame.installEventFilter(self)

        self._record_id = ""
        self._status: ToolActivityStatus = "running"
        self._expanded = False
        self._can_expand = False
        self._fitting_output = False
        self.hide()

    def record_id(self) -> str:
        """Return the bound tool activity record id."""
        return self._record_id

    def status(self) -> ToolActivityStatus:
        """Return the current visual status."""
        return self._status

    def can_expand(self) -> bool:
        """Return whether this row has observation output the user can open."""
        return self._can_expand

    def toggle_expanded(self) -> None:
        """Flip the expand chevron and output panel."""
        self._expand_btn.toggle()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Refit output height when the panel width changes."""
        if (
            watched is self._output_frame
            and event.type() == QEvent.Type.Resize
            and not self._fitting_output
        ):
            self._fit_output_height()
        return super().eventFilter(watched, event)

    def _on_expand_toggled(self, expanded: bool) -> None:
        """Show or hide the full observation output."""
        self._expanded = expanded
        self._expand_btn.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self._output_frame.setVisible(expanded)
        self._header.setCursor(
            Qt.CursorShape.PointingHandCursor if self._can_expand else Qt.CursorShape.ArrowCursor
        )
        if expanded:
            self._fit_output_height()
        self._sync_height_policy()

    def _wrapped_text_height(self, text_width: int) -> int:
        """Return the word-wrapped text height for the current output body."""
        return (
            self._output.fontMetrics()
            .boundingRect(
                0,
                0,
                max(1, text_width),
                10_000,
                Qt.TextFlag.TextWordWrap,
                self._output.text(),
            )
            .height()
        )

    def _scrollbar_extent(self) -> int:
        """Return the vertical scrollbar width that will steal text space."""
        extent = self._output_scroll.style().pixelMetric(
            self._output_scroll.style().PixelMetric.PM_ScrollBarExtent
        )
        return max(_SCROLLBAR_FALLBACK_PX, int(extent or 0))

    def _fit_output_height(self) -> None:
        """Size the frame to content; scroll only when the body exceeds the cap.

        When a scrollbar is needed, remeasure at the narrower text width — the
        bar steals horizontal space, so a one-pass height locks the label short
        and clips the last line at the bottom of the scroll range.
        """
        if not self._expanded or not self._can_expand or self._fitting_output:
            return
        width = max(160, self._output_frame.width())
        if width <= 160 and self.width() > 0:
            # Left indent matches QSS margin-left on the output frame (22px).
            width = max(160, self.width() - 22)
        inner_width = max(1, width - _OUTPUT_BORDER_Y_PX)
        text_width = max(1, inner_width - _OUTPUT_PAD_X_PX)
        content_h = max(
            1, self._wrapped_text_height(text_width) + _OUTPUT_PAD_Y_PX + _OUTPUT_HEIGHT_SLACK_PX
        )
        needs_scroll = content_h + _OUTPUT_BORDER_Y_PX > _MAX_OUTPUT_HEIGHT_PX
        label_width = inner_width
        if needs_scroll:
            bar = self._scrollbar_extent()
            text_width = max(1, text_width - bar)
            content_h = max(
                1,
                self._wrapped_text_height(text_width) + _OUTPUT_PAD_Y_PX + _OUTPUT_HEIGHT_SLACK_PX,
            )
            label_width = max(1, inner_width - bar)
        frame_h = min(_MAX_OUTPUT_HEIGHT_PX, content_h + _OUTPUT_BORDER_Y_PX)
        # Viewport is inside the border; keep the label at full content height.
        viewport_h = max(1, frame_h - _OUTPUT_BORDER_Y_PX)

        self._fitting_output = True
        try:
            self._output.setFixedSize(label_width, content_h)
            self._output_scroll.setFixedHeight(viewport_h)
            self._output_scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
                if needs_scroll
                else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            if self._output_frame.height() != frame_h:
                self._output_frame.setFixedHeight(frame_h)
        finally:
            self._fitting_output = False

    def _sync_height_policy(self) -> None:
        if self._expanded and self._can_expand:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def apply_record(self, record: ToolActivityRecord) -> None:
        """Update the row from *record*."""
        was_expanded = self._expanded and record["id"] == self._record_id
        self._record_id = record["id"]
        self._status = record["status"]
        tool_name = str(record.get("tool_name") or "")
        icon_name = _TOOL_ICONS.get(tool_name, "wrench")
        failed = self._status in {"error", "rejected"}
        icon_color = COLOR_DANGER if failed else ""
        self._title_icon.setPixmap(phi(icon_name, color=icon_color, size=12).pixmap(12, 12))
        self._title.setText(record["title"])
        self._title.setProperty("failed", "true" if failed else "false")
        self._title.style().unpolish(self._title)
        self._title.style().polish(self._title)

        detail_text = (record.get("detail") or "").strip()
        self._detail.setToolTip(detail_text)
        display = _ellipsize(detail_text, self._detail)
        if self._status == "running":
            self._spinner.start()
            self._spinner.show()
            self._status_icon.hide()
        else:
            self._spinner.stop()
            self._spinner.hide()
            self._status_icon.show()
            icon = "check-circle" if self._status == "completed" else "x-circle"
            color = COLOR_SUCCESS if self._status == "completed" else COLOR_DANGER
            self._status_icon.setPixmap(phi(icon, color=color, size=12).pixmap(12, 12))
        self._detail.setText(display)
        self._detail.setVisible(bool(detail_text))

        started = record.get("started_at")
        completed = record.get("completed_at")
        elapsed = None if started is None or completed is None else completed - started
        self._duration.setText(_format_duration(elapsed))

        output_text = (record.get("output") or "").strip()
        self._can_expand = bool(output_text) and self._status in _TERMINAL_STATUSES
        self._expand_btn.setVisible(self._can_expand)
        if self._can_expand:
            self._output.setText(format_tool_activity_output(output_text))
            self._expand_btn.blockSignals(True)
            self._expand_btn.setChecked(was_expanded)
            self._expand_btn.blockSignals(False)
            self._on_expand_toggled(was_expanded)
        else:
            self._expanded = False
            self._output_frame.hide()
            self._expand_btn.setChecked(False)
            self._header.setCursor(Qt.CursorShape.ArrowCursor)
            self._sync_height_policy()

        self.show()


__all__ = ["ToolActivityCard"]
