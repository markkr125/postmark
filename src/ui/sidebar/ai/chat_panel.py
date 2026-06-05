"""AI assistant chat panel (skeleton) for the right sidebar.

Renders a scrollable transcript of message bubbles above a composer with an
attachment-chips row, an auto-growing prompt (``_ComposerInput``, 3..15 lines),
and a control strip (upload, agent mode, model picker, context button, Send).
This is UI structure only: it does not call any LLM. ``Send`` appends a local
user bubble and emits ``message_submitted``; the mode/upload/context controls
are placeholders.

See ``docs/ui-reference/sidebar.md`` (section *AI composer input (auto-grow)*)
for behavior, Qt sizing notes, and constants.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
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
from services.ai.provider_catalog import effective_run_context_tokens, format_context_tokens
from services.ai.reasoning_effort import clamp_effort, default_effort_for, format_reasoning_effort
from ui.sidebar.ai.agent_mode_popup import AgentModeButton, AiAgentModePopup
from ui.sidebar.ai.message_bubble import ChatMessageBubble, ChatRole
from ui.sidebar.ai.model_picker_edit import reasoning_levels_for_entry, thinking_enabled_for_entry
from ui.sidebar.ai.model_picker_popup import AiModelPickerPopup
from ui.styling.icons import phi

_EMPTY_STATE_TEXT = "Ask anything about your API requests."
_NO_MODELS_TEXT = "No models configured"
_COMPOSER_MIN_LINES = 3
_COMPOSER_MAX_LINES = 15
# Matches ``padding: 6px`` top+bottom on ``aiChatInput`` in global_qss.py.
_COMPOSER_QSS_VERTICAL_PADDING = 12


class _ComposerInput(QPlainTextEdit):
    """Prompt input that auto-grows (3..15 lines) and emits submit on Ctrl+Enter."""

    submit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Configure wrap, scrollbars, and connect auto-grow recompute."""
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.document().documentLayout().documentSizeChanged.connect(self._adjust_height)
        self._adjust_height()

    def _vertical_chrome(self) -> int:
        """Pixels consumed by frame, document margin, and stylesheet padding."""
        frame = 2 * self.frameWidth()
        doc_margin = int(2 * self.document().documentMargin())
        return _COMPOSER_QSS_VERTICAL_PADDING + frame + doc_margin

    def _adjust_height(self, *_args: object) -> None:
        """Resize to fit content, clamped to 3..15 lines; scroll past the cap."""
        line_height = self.fontMetrics().lineSpacing()
        chrome = self._vertical_chrome()
        visual_lines = self.document().documentLayout().documentSize().height()
        visual_lines = max(1.0, visual_lines)

        min_h = _COMPOSER_MIN_LINES * line_height + chrome
        max_h = _COMPOSER_MAX_LINES * line_height + chrome
        content_h = int(visual_lines * line_height) + chrome
        target = max(min_h, min(content_h, max_h))

        over_cap = content_h > max_h
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if over_cap
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        if self.height() != target:
            self.setFixedHeight(target)

    def resizeEvent(self, event) -> None:
        """Recompute height when width changes (wrapping can change line count)."""
        super().resizeEvent(event)
        self._adjust_height()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Submit on Ctrl+Return/Enter; otherwise behave as a normal editor."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ModelPickerButton(QWidget):
    """Compact model pill matching :class:`AgentModeButton` (label · tags · caret)."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build name, context/reasoning tags, and trailing caret."""
        super().__init__(parent)
        self.setObjectName("aiChatModelButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        mouse_through = Qt.WidgetAttribute.WA_TransparentForMouseEvents

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 6, 3)
        lay.setSpacing(4)

        self._name = QLabel(_NO_MODELS_TEXT)
        self._name.setObjectName("aiChatModelButtonPart")
        self._name.setAttribute(mouse_through, True)
        lay.addWidget(self._name, 0)

        self._sep_ctx = QLabel("·")
        self._sep_ctx.setObjectName("aiChatModelButtonPart")
        self._sep_ctx.setAttribute(mouse_through, True)
        lay.addWidget(self._sep_ctx, 0)

        self._ctx = QLabel()
        self._ctx.setObjectName("aiModelPickerContext")
        self._ctx.setAttribute(mouse_through, True)
        lay.addWidget(self._ctx, 0)

        self._sep_effort = QLabel("·")
        self._sep_effort.setObjectName("aiChatModelButtonPart")
        self._sep_effort.setAttribute(mouse_through, True)
        lay.addWidget(self._sep_effort, 0)

        self._effort = QLabel()
        self._effort.setObjectName("aiModelPickerEffort")
        self._effort.setAttribute(mouse_through, True)
        lay.addWidget(self._effort, 0)

        caret = QLabel()
        caret.setPixmap(phi("caret-down", size=10).pixmap(10, 10))
        caret.setAttribute(mouse_through, True)
        lay.addWidget(caret, 0)

        self._hide_tags()

    def _hide_tags(self) -> None:
        """Hide context/reasoning segments (empty-state / name-only)."""
        self._sep_ctx.hide()
        self._ctx.hide()
        self._sep_effort.hide()
        self._effort.hide()

    def set_parts(self, parts: tuple[str, str | None, str | None] | None) -> None:
        """Update visible segments from ``(name, context, effort)`` or empty state."""
        if parts is None:
            self._name.setText(_NO_MODELS_TEXT)
            self._hide_tags()
        else:
            name, ctx_val, effort_val = parts
            self._name.setText(name)
            if ctx_val:
                self._ctx.setText(ctx_val)
                self._sep_ctx.show()
                self._ctx.show()
            else:
                self._sep_ctx.hide()
                self._ctx.hide()
            if effort_val:
                self._effort.setText(effort_val)
                self._sep_effort.show()
                self._effort.show()
            else:
                self._sep_effort.hide()
                self._effort.hide()
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit ``clicked`` on left press."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class AiChatPanel(QWidget):
    """Right-sidebar AI chat skeleton (transcript + composer)."""

    message_submitted = Signal(str)
    mode_changed = Signal(str)
    attachments_changed = Signal(list)
    manage_models_requested = Signal()
    effort_changed = Signal(str, str)
    context_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the transcript scroll area and the composer."""
        super().__init__(parent)
        self.setObjectName("aiChatPanel")
        self._attachments: list[str] = []
        self._models: list[AiModelEntry] = []
        self._current_model_id: str | None = None
        self._reasoning_effort: str | None = None

        self._picker_popup = AiModelPickerPopup.instance()
        self._mode_popup = AiAgentModePopup.instance()

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
        self._input.submit_requested.connect(self._on_send)
        composer_layout.addWidget(self._input)

        # Control strip, left to right: mode, model, context, upload, Send.
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)

        self._mode_btn = AgentModeButton()
        self._mode_btn.clicked.connect(self._open_mode_picker)
        controls.addWidget(self._mode_btn)

        self._model_btn = ModelPickerButton()
        self._model_btn.setToolTip("Select model")
        self._model_btn.clicked.connect(self._open_model_picker)
        controls.addWidget(self._model_btn, 0)
        controls.addStretch(1)

        self._context_btn = QPushButton()
        self._context_btn.setObjectName("iconButton")
        self._context_btn.setIcon(phi("chart-pie-slice", size=16))
        self._context_btn.setFixedSize(28, 28)
        self._context_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._context_btn.setToolTip("Context: —")
        self._context_btn.clicked.connect(self.context_requested.emit)
        controls.addWidget(self._context_btn)

        self._upload_btn = QPushButton()
        self._upload_btn.setObjectName("iconButton")
        self._upload_btn.setIcon(phi("paperclip", size=16))
        self._upload_btn.setFixedSize(28, 28)
        self._upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._upload_btn.setToolTip("Attach file")
        self._upload_btn.clicked.connect(self._on_attach)
        controls.addWidget(self._upload_btn)

        self._send_btn = QPushButton()
        self._send_btn.setObjectName("smallPrimaryButton")
        self._send_btn.setIcon(phi("paper-plane-right", color="#ffffff"))
        self._send_btn.setFixedSize(28, 28)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setToolTip("Send (Ctrl+Enter)")
        self._send_btn.clicked.connect(self._on_send)
        controls.addWidget(self._send_btn)

        composer_layout.addLayout(controls)
        root.addWidget(composer)

        self.set_models([])
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
        self._sync_model_state(self._current_model_id)
        has_models = bool(self._models)
        self._model_btn.setEnabled(has_models)
        self._send_btn.setEnabled(has_models)
        self._refresh_model_button()
        entry = self._entry_by_id(self._current_model_id) if self._current_model_id else None
        total = effective_run_context_tokens(entry) if entry is not None else 0
        self.set_context_usage(0, total)

    def _entry_by_id(self, model_id: str) -> AiModelEntry | None:
        """Return the model entry with *model_id*, if present."""
        for entry in self._models:
            if entry["id"] == model_id:
                return entry
        return None

    def _effective_effort(self, entry: AiModelEntry) -> str | None:
        """Return persisted leveled reasoning effort, if the model supports it."""
        efforts = reasoning_levels_for_entry(entry)
        if not efforts:
            return None
        stored = entry.get("reasoning_effort")
        if isinstance(stored, str) and stored.strip():
            return clamp_effort(
                stored.strip().lower(), efforts, str(entry.get("reasoning_default", ""))
            )
        default = str(entry.get("reasoning_default", ""))
        if default:
            return clamp_effort(default, efforts, default)
        return default_effort_for(efforts)

    def _sync_model_state(self, model_id: str | None) -> None:
        """Refresh derived state for *model_id* from the in-memory model list."""
        self._reasoning_effort = None
        if not model_id:
            return
        entry = self._entry_by_id(model_id)
        if entry is None:
            return
        self._reasoning_effort = self._effective_effort(entry)

    def current_model_id(self) -> str | None:
        """Return the selected model id, or ``None`` when no model is set."""
        return self._current_model_id

    def current_reasoning_effort(self) -> str | None:
        """Return the selected reasoning effort for the current model, if any."""
        return self._reasoning_effort

    def current_run_context_tokens(self) -> int:
        """Return the effective run context window for the current model."""
        entry = self._entry_by_id(self._current_model_id) if self._current_model_id else None
        return effective_run_context_tokens(entry) if entry is not None else 0

    def current_thinking_enabled(self) -> str | None:
        """Return ``on``/``off`` when the model supports thinking, else ``None``."""
        entry = self._entry_by_id(self._current_model_id) if self._current_model_id else None
        if entry is None or not entry.get("thinking"):
            return None
        return thinking_enabled_for_entry(entry)

    def current_mode(self) -> str:
        """Return the selected agent mode (``"agent"`` / ``"ask"`` / ``"plan"``)."""
        return self._mode_btn.mode()

    def set_mode(self, mode: str) -> None:
        """Set agent mode without opening the picker (for tests and persistence)."""
        if self.current_mode() == mode:
            return
        self._mode_btn.set_mode(mode)
        self.mode_changed.emit(mode)

    def attachments(self) -> list[str]:
        """Return the list of attached file paths."""
        return list(self._attachments)

    def set_context_usage(self, used_tokens: int, total_tokens: int) -> None:
        """Update the context button tooltip. ``total_tokens <= 0`` shows a dash."""
        if total_tokens <= 0:
            self._context_btn.setToolTip("Context: —")
            return
        pct = min(100, round(100 * used_tokens / total_tokens))
        used = format_context_tokens(used_tokens)
        total = format_context_tokens(total_tokens)
        self._context_btn.setToolTip(f"Context: {pct}% ({used}/{total})")

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
    def _model_button_parts(self) -> tuple[str, str | None, str | None] | None:
        """Return ``(name, context tag, effort tag)`` or ``None`` for the empty state."""
        if not self._models or self._current_model_id is None:
            return None
        entry = self._entry_by_id(self._current_model_id)
        if entry is None:
            return None
        name = entry.get("label") or entry["model"]
        ctx_val: str | None = None
        ctx_tokens = effective_run_context_tokens(entry)
        if ctx_tokens > 0:
            ctx_val = format_context_tokens(ctx_tokens)
        effort_val: str | None = None
        effort = self._reasoning_effort or self._effective_effort(entry)
        if effort:
            effort_val = format_reasoning_effort(effort)
        return (name, ctx_val, effort_val)

    def _model_button_label(self) -> str:
        """Plain-text model button label (name · context · effort) for tests."""
        parts = self._model_button_parts()
        if parts is None:
            return _NO_MODELS_TEXT
        bits = [parts[0]]
        if parts[1]:
            bits.append(parts[1])
        if parts[2]:
            bits.append(parts[2])
        return "  ·  ".join(bits)

    def _refresh_model_button(self) -> None:
        """Update the model pill from the current selection."""
        self._model_btn.set_parts(self._model_button_parts())

    def _open_model_picker(self) -> None:
        """Open or close the model picker (toggle when already visible)."""
        if not self._models:
            return
        if self._picker_popup.isVisible():
            self._picker_popup.hidePopup()
            return
        self._picker_popup.show_for(
            self._model_btn,
            self._models,
            self._current_model_id,
            self._on_model_picked,
            self._on_manage_models,
            on_settings_changed=self._on_model_settings_changed,
        )

    def _on_model_picked(self, model_id: str) -> None:
        """Store the picked model id and refresh the button label."""
        self._current_model_id = model_id
        self._sync_model_state(model_id)
        self._refresh_model_button()
        entry = self._entry_by_id(model_id)
        if entry is not None:
            self.set_context_usage(0, effective_run_context_tokens(entry))

    def _on_model_settings_changed(self, model_id: str) -> None:
        """Reload persisted settings for *model_id* and refresh the composer."""
        persisted = {e["id"]: e for e in AiConfig.get_models()}
        if model_id in persisted:
            for i, row in enumerate(self._models):
                if row["id"] == model_id:
                    self._models[i] = persisted[model_id]
                    break
        if self._current_model_id == model_id:
            self._sync_model_state(model_id)
            self._refresh_model_button()
            entry = self._entry_by_id(model_id)
            if entry is not None:
                self.set_context_usage(0, effective_run_context_tokens(entry))
        self.effort_changed.emit(model_id, self._reasoning_effort or "")

    def _on_manage_models(self) -> None:
        """Bubble up a request to open Settings -> AI -> Models."""
        self.manage_models_requested.emit()

    def _open_mode_picker(self) -> None:
        """Open the compact mode picker above the mode pill."""
        popup = self._mode_popup
        if popup.isVisible():
            popup.hide_popup()
            return

        def on_pick(mode: str) -> None:
            self._mode_btn.set_mode(mode)
            self.mode_changed.emit(mode)

        popup.show_for(self._mode_btn, self._mode_btn.mode(), on_pick)

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
        # TODO: build LLM via AiLlmService.build_llm(entry) using current_model_id(),
        # current_mode(), current_run_context_tokens(), current_thinking_enabled(),
        # current_reasoning_effort(), attachments();
        # stream the reply into add_message("assistant", ...).
        self.message_submitted.emit(text)

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
