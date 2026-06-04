"""AI assistant chat panel (skeleton) for the right sidebar.

Renders a scrollable transcript of message bubbles above a composer with an
attachment-chips row, a multi-line input, and a control strip (upload, agent
mode, model picker, context-usage indicator, Send). This is UI structure
only: it does not call any LLM. ``Send`` appends a local user bubble and
emits ``message_submitted``; the mode/upload/context controls are
placeholders.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.ai.ai_config import AiConfig, AiModelEntry, model_entry_enabled
from services.ai.provider_catalog import format_context_tokens
from ui.sidebar.ai.message_bubble import ChatMessageBubble, ChatRole
from ui.sidebar.ai.model_picker_popup import AiModelPickerPopup
from ui.styling.icons import phi

_EMPTY_STATE_TEXT = "Ask anything about your API requests."
_NO_MODELS_TEXT = "No models configured"
_AGENT_MODES: tuple[tuple[str, str], ...] = (
    ("Agent", "agent"),
    ("Ask", "ask"),
    ("Plan", "plan"),
)


class _ComposerInput(QPlainTextEdit):
    """Prompt input that emits ``submit_requested`` on Ctrl+Enter."""

    submit_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Submit on Ctrl+Return/Enter; otherwise behave as a normal editor."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class AiChatPanel(QWidget):
    """Right-sidebar AI chat skeleton (transcript + composer)."""

    message_submitted = Signal(str)
    mode_changed = Signal(str)
    attachments_changed = Signal(list)
    manage_models_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the transcript scroll area and the composer."""
        super().__init__(parent)
        self.setObjectName("aiChatPanel")
        self._attachments: list[str] = []
        self._models: list[AiModelEntry] = []
        self._current_model_id: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 8)
        root.setSpacing(8)

        # --- Transcript ------------------------------------------------
        self._scroll = QScrollArea()
        self._scroll.setObjectName("aiChatScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self._messages = QWidget()
        self._messages_layout = QVBoxLayout(self._messages)
        self._messages_layout.setContentsMargins(0, 0, 0, 0)
        self._messages_layout.setSpacing(8)
        self._messages_layout.addStretch(1)  # pushes bubbles to the bottom

        self._empty_label = QLabel(_EMPTY_STATE_TEXT)
        self._empty_label.setObjectName("emptyStateLabel")
        self._empty_label.setWordWrap(True)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._messages_layout.addWidget(self._empty_label)

        self._scroll.setWidget(self._messages)
        root.addWidget(self._scroll, 1)

        # --- Composer --------------------------------------------------
        composer = QWidget()
        composer.setObjectName("aiChatComposer")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(0, 8, 0, 0)
        composer_layout.setSpacing(6)

        # Attachment chips (row hidden until a file is added)
        self._attachments_row = QWidget()
        self._attachments_row.setObjectName("aiChatAttachments")
        self._attachments_layout = QHBoxLayout(self._attachments_row)
        self._attachments_layout.setContentsMargins(0, 0, 0, 0)
        self._attachments_layout.setSpacing(4)
        self._attachments_layout.addStretch(1)
        self._attachments_row.hide()
        composer_layout.addWidget(self._attachments_row)

        self._input = _ComposerInput()
        self._input.setObjectName("aiChatInput")
        self._input.setPlaceholderText("Message the assistant...  (Ctrl+Enter to send)")
        self._input.setFixedHeight(72)
        self._input.submit_requested.connect(self._on_send)
        composer_layout.addWidget(self._input)

        # Control strip, left to right: mode, model, context, upload, Send.
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)

        self._mode_combo = QComboBox()
        self._mode_combo.setObjectName("aiChatModeCombo")
        for label, value in _AGENT_MODES:
            self._mode_combo.addItem(label, value)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        controls.addWidget(self._mode_combo)

        self._model_btn = QPushButton()
        self._model_btn.setObjectName("aiChatModelButton")
        self._model_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._model_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._model_btn.setIcon(phi("caret-down", size=12))
        self._model_btn.setToolTip("Select model")
        self._model_btn.clicked.connect(self._open_model_picker)
        controls.addWidget(self._model_btn, 1)

        self._context_label = QLabel("")
        self._context_label.setObjectName("aiChatContextLabel")
        self._context_label.setToolTip("Context used / model context window")
        controls.addWidget(self._context_label)

        self._upload_btn = QPushButton()
        self._upload_btn.setObjectName("iconButton")
        self._upload_btn.setIcon(phi("paperclip", size=16))
        self._upload_btn.setFixedSize(28, 28)
        self._upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._upload_btn.setToolTip("Attach file")
        self._upload_btn.clicked.connect(self._on_attach)
        controls.addWidget(self._upload_btn)

        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("smallPrimaryButton")
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.clicked.connect(self._on_send)
        controls.addWidget(self._send_btn)

        composer_layout.addLayout(controls)
        root.addWidget(composer)

        self.set_models(AiConfig.get_models())
        self.set_context_usage(0, 0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_models(self, entries: list[AiModelEntry]) -> None:
        """Store enabled models, keep/refresh the selection, and toggle Send."""
        self._models = [e for e in entries if model_entry_enabled(e)]
        ids = {e["id"] for e in self._models}
        if self._current_model_id not in ids:
            self._current_model_id = self._models[0]["id"] if self._models else None
        has_models = bool(self._models)
        self._model_btn.setEnabled(has_models)
        self._send_btn.setEnabled(has_models)
        self._refresh_model_button()

    def current_model_id(self) -> str | None:
        """Return the selected model id, or ``None`` when no model is set."""
        return self._current_model_id

    def current_mode(self) -> str:
        """Return the selected agent mode (``"agent"`` / ``"ask"`` / ``"plan"``)."""
        data = self._mode_combo.currentData()
        return data if isinstance(data, str) else "agent"

    def attachments(self) -> list[str]:
        """Return the list of attached file paths."""
        return list(self._attachments)

    def set_context_usage(self, used_tokens: int, total_tokens: int) -> None:
        """Update the context indicator. ``total_tokens <= 0`` shows a dash."""
        if total_tokens <= 0:
            self._context_label.setText("ctx —")
            return
        pct = min(100, round(100 * used_tokens / total_tokens))
        used = format_context_tokens(used_tokens)
        total = format_context_tokens(total_tokens)
        self._context_label.setText(f"{pct}% ({used}/{total})")

    def add_message(self, role: ChatRole, text: str) -> ChatMessageBubble:
        """Append a message bubble to the transcript and scroll to it."""
        self._empty_label.hide()
        bubble = ChatMessageBubble(role, text)
        align = Qt.AlignmentFlag.AlignRight if role == "user" else Qt.AlignmentFlag.AlignLeft
        self._messages_layout.addWidget(bubble, alignment=align)
        QTimer.singleShot(0, self._scroll_to_bottom)
        return bubble

    def clear(self) -> None:
        """Remove all message bubbles and restore the empty state."""
        for i in reversed(range(self._messages_layout.count())):
            item = self._messages_layout.itemAt(i)
            widget = item.widget() if item is not None else None
            if isinstance(widget, ChatMessageBubble):
                widget.setParent(None)
                widget.deleteLater()
        self._empty_label.show()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _refresh_model_button(self) -> None:
        """Update the model button label from the current selection."""
        label = _NO_MODELS_TEXT
        for entry in self._models:
            if entry["id"] == self._current_model_id:
                label = entry.get("label") or entry["model"]
                break
        self._model_btn.setText(label)

    def _open_model_picker(self) -> None:
        """Open the Cursor-style model picker anchored to the model button."""
        if not self._models:
            return
        popup = AiModelPickerPopup.instance()
        popup.show_for(
            self._model_btn,
            self._models,
            self._current_model_id,
            self._on_model_picked,
            self._on_manage_models,
        )

    def _on_model_picked(self, model_id: str) -> None:
        """Store the picked model id and refresh the button label."""
        self._current_model_id = model_id
        self._refresh_model_button()

    def _on_manage_models(self) -> None:
        """Bubble up a request to open Settings -> AI -> Models."""
        self.manage_models_requested.emit()

    def _on_mode_changed(self, _index: int) -> None:
        self.mode_changed.emit(self.current_mode())

    def _on_attach(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach file")
        added = False
        for path in paths:
            if path and path not in self._attachments:
                self._attachments.append(path)
                self._add_attachment_chip(path)
                added = True
        if added:
            self._attachments_row.setVisible(bool(self._attachments))
            self.attachments_changed.emit(self.attachments())

    def _add_attachment_chip(self, path: str) -> None:
        chip = QPushButton(f"{Path(path).name}  x")
        chip.setObjectName("aiChatAttachmentChip")
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setToolTip(f"Remove {path}")
        chip.clicked.connect(lambda: self._remove_attachment(path, chip))
        # Insert before the trailing stretch so chips pack left.
        self._attachments_layout.insertWidget(self._attachments_layout.count() - 1, chip)

    def _remove_attachment(self, path: str, chip: QPushButton) -> None:
        if path in self._attachments:
            self._attachments.remove(path)
        chip.setParent(None)
        chip.deleteLater()
        self._attachments_row.setVisible(bool(self._attachments))
        self.attachments_changed.emit(self.attachments())

    def _on_send(self) -> None:
        """Append the typed text as a user bubble and emit the signal."""
        if not self._send_btn.isEnabled():
            return
        text = self._input.toPlainText().strip()
        if not text:
            return
        self.add_message("user", text)
        self._input.clear()
        # TODO: build LLM via AiLlmService.build_llm(entry) using
        # current_model_id() + current_mode() + attachments(); stream the
        # reply into add_message("assistant", ...).
        self.message_submitted.emit(text)

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
