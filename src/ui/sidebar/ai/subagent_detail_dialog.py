"""Non-modal window showing a subagent task prompt and markdown reply."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication, QHideEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.ai.chat.response_text import merge_stream_text
from services.ai.chat.subagent_events import (
    SubagentRunRecord,
    SubagentStatus,
    delegate_agent_result_from_observation,
    enrich_subagent_records,
    subagent_type_display,
)
from services.ai.chat.subagent_transcript import load_subagent_transcript_view
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent
from ui.widgets.busy_spinner import BrailleSpinner

_STATUS_LABELS: dict[SubagentStatus, str] = {
    "warming": "Starting",
    "running": "Running",
    "completed": "Completed",
    "error": "Failed",
}

_DEFAULT_WIDTH = 680
_DEFAULT_HEIGHT = 720
_MAX_WIDTH_FRACTION = 0.62
_MAX_HEIGHT_FRACTION = 0.78
_POLL_MS = 750


def _initial_dialog_size() -> tuple[int, int]:
    """Return a compact default size capped relative to the available screen."""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return _DEFAULT_WIDTH, _DEFAULT_HEIGHT
    geo = screen.availableGeometry()
    width = min(_DEFAULT_WIDTH, int(geo.width() * _MAX_WIDTH_FRACTION))
    height = min(_DEFAULT_HEIGHT, int(geo.height() * _MAX_HEIGHT_FRACTION))
    return max(520, width), max(480, height)


class SubagentDetailDialog(QDialog):
    """Read-only dialog for one subagent delegation with live markdown streaming."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build header, task prompt, and markdown reply sections."""
        super().__init__(parent)
        self.setObjectName("aiChatSubagentDetailDialog")
        self.setWindowTitle("Subagent")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.resize(*_initial_dialog_size())

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(8)

        self._title = QLabel()
        self._title.setObjectName("aiChatSubagentDetailTitle")
        self._title.setWordWrap(True)
        header.addWidget(self._title, 1)

        self._meta = QLabel()
        self._meta.setObjectName("aiChatSubagentDetailMeta")
        self._meta.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        header.addWidget(self._meta, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        task_heading = QLabel("Task")
        task_heading.setObjectName("aiChatSubagentDetailSectionHeading")
        root.addWidget(task_heading)

        self._task = QLabel()
        self._task.setObjectName("aiChatSubagentDetailTask")
        self._task.setWordWrap(True)
        self._task.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self._task)

        reply_row = QHBoxLayout()
        reply_row.setSpacing(8)
        reply_heading = QLabel("Reply")
        reply_heading.setObjectName("aiChatSubagentDetailSectionHeading")
        reply_row.addWidget(reply_heading)
        self._reply_spinner = BrailleSpinner(self, object_name="aiChatSubagentDetailSpinner")
        reply_row.addWidget(self._reply_spinner, 0)
        reply_row.addStretch(1)
        root.addLayout(reply_row)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("aiChatSubagentDetailScroll")
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        # Same MarkdownContent + aiChatAssistantText styling as assistant transcript rows.
        self._reply = MarkdownContent()
        self._scroll.setWidget(self._reply)
        root.addWidget(self._scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("outlineButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        footer.addWidget(close_btn)
        root.addLayout(footer)

        self._record_id: str | None = None
        self._record: SubagentRunRecord | None = None
        self._session_id: str | None = None
        self._answer_markdown = ""
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_MS)
        self._poll_timer.timeout.connect(self._poll_transcript)

    def record_id(self) -> str | None:
        """Return the record id currently shown, if any."""
        return self._record_id

    def is_open_for(self, record_id: str) -> bool:
        """Return whether this dialog is visible for *record_id*."""
        return self.isVisible() and self._record_id == record_id

    def open_record(self, record: SubagentRunRecord, *, session_id: str | None = None) -> None:
        """Show or focus the dialog for *record*."""
        self._session_id = session_id
        self._record = SubagentRunRecord(**record)
        self._record_id = record["id"]
        self._answer_markdown = ""
        if not self.isVisible():
            self.show()
        self._apply_record(self._record, reset_answer=True)
        self.raise_()
        self.activateWindow()
        self._schedule_reply_layout_sync()

    def refresh_record(self, record: SubagentRunRecord) -> None:
        """Update an already-open dialog from a fresher *record*."""
        if self._record_id != record["id"]:
            return
        self._record = SubagentRunRecord(**record)
        self._apply_record(self._record, reset_answer=False)
        self._schedule_reply_layout_sync()

    def _apply_record(self, record: SubagentRunRecord, *, reset_answer: bool) -> None:
        enriched = enrich_subagent_records([record], session_id=self._session_id)[0]
        self._record = enriched
        self._title.setText(enriched["label"])
        status = enriched["status"]
        self._meta.setText(
            f"{subagent_type_display(enriched['subagent_type'])} · "
            f"{_STATUS_LABELS.get(status, status.title())}"
        )
        self.setWindowTitle(enriched["label"])

        task_prompt = enriched.get("task_prompt", "") or enriched["label"]
        self._task.setText(task_prompt)

        if reset_answer:
            self._answer_markdown = ""
            self._reply.set_markdown("")
            self._reply.begin_streaming()

        if status in ("warming", "running"):
            self._reply_spinner.start()
            self._reply_spinner.show()
            if not self._poll_timer.isActive():
                self._poll_timer.start()
            self._load_transcript(final=False)
        else:
            self._poll_timer.stop()
            self._reply_spinner.stop()
            self._reply_spinner.hide()
            self._load_transcript(final=True)

    def _poll_transcript(self) -> None:
        """Refresh reply markdown while the subagent is still running."""
        if self._record is None:
            return
        self._load_transcript(final=self._record["status"] not in ("warming", "running"))

    def _load_transcript(self, *, final: bool) -> None:
        if self._record is None:
            return
        record = self._record
        disk = record.get("disk_path", "")
        fallback = record.get("task_prompt", "") or record["label"]
        view = (
            load_subagent_transcript_view(disk, fallback_task_prompt=fallback)
            if disk
            else {
                "task_prompt": fallback,
                "answer_markdown": record.get("result_preview", ""),
                "event_count": 0,
            }
        )

        if view["task_prompt"]:
            self._task.setText(view["task_prompt"])

        answer = view["answer_markdown"]
        if not answer:
            preview = record.get("result_preview", "")
            if isinstance(preview, str) and preview.strip():
                if record["kind"] == "delegate":
                    answer = delegate_agent_result_from_observation(preview, record["id"])
                    if not answer and not preview.lstrip().startswith("Completed delegation"):
                        answer = preview
                else:
                    answer = preview

        if (
            final
            and answer
            and self._answer_markdown
            and not answer.startswith(self._answer_markdown)
        ):
            merged = answer
        else:
            merged = merge_stream_text(self._answer_markdown, answer)
        if merged != self._answer_markdown:
            delta = merged[len(self._answer_markdown) :]
            self._answer_markdown = merged
            if delta:
                if self._reply.is_streaming():
                    self._reply.append_markdown(delta)
                else:
                    self._reply.set_markdown(merged)

        if final:
            self._poll_timer.stop()
            self._reply_spinner.stop()
            self._reply_spinner.hide()
            if self._answer_markdown:
                self._reply.end_streaming()
            elif record["status"] == "error":
                self._reply.set_markdown("_Subagent failed before producing a reply._")
                self._reply.end_streaming()
            else:
                self._reply.end_streaming()
            self._schedule_reply_layout_sync()

    def _schedule_reply_layout_sync(self) -> None:
        """Re-render markdown after the dialog has a real viewport width."""
        QTimer.singleShot(0, self._sync_reply_layout)

    def _sync_reply_layout(self) -> None:
        """Match assistant-row markdown layout width inside the scroll area."""
        viewport = self._scroll.viewport()
        if viewport is None or viewport.width() <= 0:
            return
        width = viewport.width()
        needs_rerender = self._reply.width() <= 1 or self._reply.width() != width
        if self._reply.width() != width:
            self._reply.setFixedWidth(width)
        markdown = self._reply.markdown()
        if markdown and needs_rerender and not self._reply.is_streaming():
            self._reply.set_markdown(markdown)
        else:
            self._reply.resync_height_for_footer()

    def showEvent(self, event: QShowEvent) -> None:
        """Lay out markdown at the scroll viewport width once visible."""
        super().showEvent(event)
        self._schedule_reply_layout_sync()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Reflow markdown when the dialog or scroll viewport width changes."""
        super().resizeEvent(event)
        self._schedule_reply_layout_sync()

    def hideEvent(self, event: QHideEvent) -> None:
        """Stop polling when the dialog is hidden."""
        self._poll_timer.stop()
        self._reply_spinner.stop()
        super().hideEvent(event)


__all__ = ["SubagentDetailDialog"]
