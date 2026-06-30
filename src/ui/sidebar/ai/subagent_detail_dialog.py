"""Non-modal window showing a subagent task prompt and markdown reply."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
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
    SubagentActivityStep,
    SubagentRunRecord,
    SubagentStatus,
    delegate_agent_result_from_observation,
    enrich_subagent_records,
    subagent_type_display,
)
from services.ai.chat.subagent_transcript import (
    SubagentTranscriptView,
    _fallback_steps_for_record,
    load_subagent_disk_snapshot,
    steps_for_subagent_record,
)
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent
from ui.sidebar.ai.message_bubble.thought_section import ThoughtSection
from ui.styling.icons import phi
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
_STEP_ICON_PX = 14
_THOUGHT_BODY_MAX_PX = 280


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

        activity_heading = QLabel("Activity")
        activity_heading.setObjectName("aiChatSubagentDetailSectionHeading")
        root.addWidget(activity_heading)
        self._activity_heading = activity_heading

        self._activity_container = QWidget()
        self._activity_container.setObjectName("aiChatSubagentDetailActivity")
        self._activity_layout = QVBoxLayout(self._activity_container)
        self._activity_layout.setContentsMargins(0, 0, 0, 0)
        self._activity_layout.setSpacing(6)
        root.addWidget(self._activity_container)

        self._activity_step_keys: list[tuple[str, str]] = []

        self._thinking_scroll = QScrollArea()
        self._thinking_scroll.setObjectName("aiChatSubagentDetailThoughtScroll")
        self._thinking_scroll.setWidgetResizable(True)
        self._thinking_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._thinking_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._thinking_scroll.setVisible(False)
        self._thinking = ThoughtSection()
        self._thinking.setVisible(False)
        self._thinking.layout_height_changed.connect(self._sync_thought_scroll)
        self._thinking_scroll.setWidget(self._thinking)
        root.addWidget(self._thinking_scroll)

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
        viewport = self._scroll.viewport()
        if viewport is not None:
            viewport.setObjectName("aiChatSubagentDetailScrollViewport")

        # Same MarkdownContent + aiChatAssistantText styling as assistant transcript rows.
        self._reply = MarkdownContent()
        self._scroll.setWidget(self._reply)
        root.addWidget(self._scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("aiChatSubagentDetailClose")
        close_btn.setIcon(phi("x", size=12))
        close_btn.setIconSize(QSize(12, 12))
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
        self._activity_step_keys = []
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
            self._thinking.set_text("")

        if status in ("warming", "running"):
            self._reply_spinner.start()
            self._reply_spinner.show()
            if not self._poll_timer.isActive():
                self._poll_timer.start()
            self._refresh_disk_state(final=False)
        else:
            self._poll_timer.stop()
            self._reply_spinner.stop()
            self._reply_spinner.hide()
            self._refresh_disk_state(final=True)

    def _poll_transcript(self) -> None:
        """Refresh reply markdown while the subagent is still running."""
        if self._record is None:
            return
        self._refresh_disk_state(final=self._record["status"] not in ("warming", "running"))

    def _refresh_disk_state(self, *, final: bool) -> None:
        """Load transcript and activity from disk with one EventLog read when possible."""
        if self._record is None:
            return
        record = self._record
        disk = record.get("disk_path", "")
        fallback = record.get("task_prompt", "") or record["label"]
        if disk:
            snapshot = load_subagent_disk_snapshot(disk, fallback_task_prompt=fallback)
            view = snapshot["view"]
            steps = snapshot["steps"] or _fallback_steps_for_record(record)
        else:
            view = SubagentTranscriptView(
                task_prompt=fallback,
                answer_markdown=str(record.get("result_preview", "") or ""),
                thinking_markdown="",
                event_count=0,
            )
            steps = steps_for_subagent_record(record)
        self._apply_transcript_view(record, view, final=final)
        self._apply_thinking(view, final=final)
        self._apply_activity_steps(steps)

    def _apply_transcript_view(
        self,
        record: SubagentRunRecord,
        view: SubagentTranscriptView,
        *,
        final: bool,
    ) -> None:
        """Update task prompt and reply markdown from a parsed transcript view."""
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

    def _build_step_row(self, step: SubagentActivityStep) -> QWidget:
        """Build one icon + summary row for the activity list."""
        row = QWidget(self._activity_container)
        row.setObjectName("aiChatSubagentDetailStepRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        icon_label = QLabel(row)
        icon_label.setObjectName("aiChatSubagentDetailStepIcon")
        icon_label.setPixmap(
            phi(step.get("icon", "circle"), size=_STEP_ICON_PX).pixmap(_STEP_ICON_PX, _STEP_ICON_PX)
        )
        icon_label.setFixedSize(_STEP_ICON_PX, _STEP_ICON_PX)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

        summary = QLabel(step.get("summary", ""), row)
        summary.setObjectName("aiChatSubagentDetailStepSummary")
        summary.setWordWrap(True)
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail = step.get("detail", "")
        if detail:
            summary.setToolTip(detail)
        layout.addWidget(summary, 1)
        return row

    def _apply_thinking(self, view: SubagentTranscriptView, *, final: bool) -> None:
        """Show the subagent's reasoning, refreshed from each disk snapshot."""
        thinking = view.get("thinking_markdown", "")
        if thinking != self._thinking.text():
            self._thinking.set_text(thinking)
            if thinking and not final:
                self._thinking.set_collapsed(False)
        if final and self._thinking.has_text():
            self._thinking.set_collapsed(True)
        self._sync_thought_scroll()

    def _sync_thought_scroll(self) -> None:
        """Show the thought scroll wrapper and cap expanded body height."""
        has = self._thinking.has_text()
        self._thinking_scroll.setVisible(has)
        if not has:
            return
        self._thinking_scroll.setMaximumHeight(_THOUGHT_BODY_MAX_PX)
        self._thinking.updateGeometry()

    def _apply_activity_steps(self, steps: list[SubagentActivityStep]) -> None:
        """Rebuild the activity list only when step keys changed."""
        keys = [(step.get("id", ""), step.get("summary", "")) for step in steps]
        if keys == self._activity_step_keys:
            return
        self._activity_step_keys = keys

        while self._activity_layout.count():
            item = self._activity_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        for step in steps:
            self._activity_layout.addWidget(self._build_step_row(step))
        has_steps = bool(steps)
        self._activity_container.setVisible(has_steps)
        self._activity_heading.setVisible(has_steps)

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
