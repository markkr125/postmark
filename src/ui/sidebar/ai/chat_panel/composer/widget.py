"""Reusable AI chat composer widget (docked or inline in transcript)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from services.ai.ai_config import AiConfig, AiModelEntry, model_entry_enabled
from services.ai.provider_catalog import effective_run_context_tokens, format_run_context_tokens
from services.ai.reasoning_effort import clamp_effort, default_effort_for, format_reasoning_effort
from ui.sidebar.ai.agent_mode_popup import AgentModeButton
from ui.sidebar.ai.chat_panel.composer.attachments import (
    PromptAttachment,
    compose_prompt_with_attachments,
    compose_prompt_with_prompt_attachments,
    split_prompt_attachments,
)
from ui.sidebar.ai.chat_panel.composer.input import ComposerInput
from ui.sidebar.ai.chat_panel.composer.model_picker_button import (
    _NO_ENABLED_MODELS_TEXT,
    _NO_MODELS_TEXT,
    ModelPickerButton,
)
from ui.sidebar.ai.chat_panel.context_ring_button import ContextUsageRingButton
from ui.sidebar.ai.model_picker_edit import reasoning_levels_for_entry, thinking_enabled_for_entry
from ui.styling.icons import CHAT_STOP_ICON_SIZE, chat_stop_icon, phi

if TYPE_CHECKING:
    from services.ai.chat.session_service import UserMessageSendSnapshot

_CHAT_COMPOSER_MARGIN_H = 8
_CHAT_COMPOSER_MARGIN_TOP = 8
# QSS padding on ``smallPrimaryButton`` is inset (box model) and does not space
# the solid 28x28 send/stop control from the panel edge — use layout margins.
_CHAT_COMPOSER_MARGIN_BOTTOM = 12


class AiChatComposer(QWidget):
    """Prompt input plus mode/model controls for AI chat."""

    submit_requested = Signal()
    stop_requested = Signal()
    cancel_requested = Signal()
    mode_changed = Signal(str)
    model_changed = Signal(str)
    attachments_changed = Signal(list)
    model_picker_requested = Signal()
    mode_picker_requested = Signal()
    layout_height_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build attachments row, input, and control strip."""
        super().__init__(parent)
        self.setObjectName("aiChatComposer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._attachments: list[str] = []
        self._prompt_attachments: list[PromptAttachment] = []
        self._models: list[AiModelEntry] = []
        self._current_model_id: str | None = None
        self._reasoning_effort: str | None = None
        self._agent_id: str | None = None
        self._run_busy = False
        self._compact = False
        self._edit_mode = False
        self._embedded = False
        self._configured_model_count = 0

        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(
            _CHAT_COMPOSER_MARGIN_H,
            _CHAT_COMPOSER_MARGIN_TOP,
            _CHAT_COMPOSER_MARGIN_H,
            _CHAT_COMPOSER_MARGIN_BOTTOM,
        )
        self._root_layout.setSpacing(6)

        self._attachments_row = QWidget()
        self._attachments_row.setObjectName("aiChatAttachments")
        attachments_layout = QHBoxLayout(self._attachments_row)
        attachments_layout.setContentsMargins(0, 0, 0, 0)
        attachments_layout.setSpacing(4)
        self._attachments_layout = attachments_layout
        attachments_layout.addStretch(1)
        self._attachments_row.hide()
        self._root_layout.addWidget(self._attachments_row)

        self._input = ComposerInput()
        self._input.setObjectName("aiChatInput")
        self._input.setPlaceholderText("Message the assistant...  (Enter to send)")
        self._input.submit_requested.connect(self._on_submit)
        self._input.cancel_requested.connect(self.cancel_requested.emit)
        self._input.height_changed.connect(self.layout_height_changed.emit)
        self._root_layout.addWidget(self._input)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)

        self._mode_btn = AgentModeButton()
        self._mode_btn.clicked.connect(self.mode_picker_requested.emit)
        controls.addWidget(self._mode_btn)

        self._model_btn = ModelPickerButton()
        self._model_btn.setToolTip("Select model")
        self._model_btn.clicked.connect(self.model_picker_requested.emit)
        controls.addWidget(self._model_btn, 0)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("aiChatEditCancel")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.hide()
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)
        controls.addWidget(self._cancel_btn, 0)

        controls.addStretch(1)

        self._context_ring = ContextUsageRingButton()
        controls.addWidget(self._context_ring)

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
        # Icon-only 28x28: QSS ``padding: 4px 12px`` on smallPrimaryButton is for
        # text buttons and eats the content box (same gotcha as outlineButton vs
        # iconButton). Zero padding keeps the accent fill + icon correctly sized.
        self._send_btn.setProperty("iconOnly", True)
        self._send_btn.setIcon(phi("paper-plane-right", color="#ffffff"))
        self._send_btn.setFixedSize(28, 28)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setToolTip("Send (Enter)")
        self._send_btn.clicked.connect(self._on_submit)
        send_style = self._send_btn.style()
        send_style.unpolish(self._send_btn)
        send_style.polish(self._send_btn)
        controls.addWidget(self._send_btn)

        self._root_layout.addLayout(controls)

    # ------------------------------------------------------------------
    # Widget accessors (for panel popover anchoring and tests)
    # ------------------------------------------------------------------
    def input_widget(self) -> ComposerInput:
        """Return the prompt text editor."""
        return self._input

    def model_button(self) -> ModelPickerButton:
        """Return the model picker pill."""
        return self._model_btn

    def mode_button(self) -> AgentModeButton:
        """Return the agent mode pill."""
        return self._mode_btn

    def context_ring(self) -> ContextUsageRingButton:
        """Return the context usage ring button."""
        return self._context_ring

    def send_button(self) -> QPushButton:
        """Return the send/stop button."""
        return self._send_btn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_compact(self, compact: bool) -> None:
        """Hide context ring and attach controls (inline edit mode)."""
        self._compact = compact
        self._context_ring.setVisible(not compact)
        self._upload_btn.setVisible(not compact)
        self._sync_attachments_row_visibility()

    def set_embedded(self, embedded: bool) -> None:
        """Strip docked chrome when the composer lives inside a user bubble."""
        self._embedded = embedded
        if embedded:
            self.setObjectName("aiChatComposerInline")
            self._root_layout.setContentsMargins(0, 0, 0, 4)
            self._input.setObjectName("aiChatInputInline")
        else:
            self.setObjectName("aiChatComposer")
            self._root_layout.setContentsMargins(
                _CHAT_COMPOSER_MARGIN_H, 8, _CHAT_COMPOSER_MARGIN_H, 8
            )
            self._input.setObjectName("aiChatInput")
        self.style().unpolish(self)
        self.style().polish(self)
        self._input.style().unpolish(self._input)
        self._input.style().polish(self._input)
        self.updateGeometry()
        self.layout_height_changed.emit()

    def set_edit_mode(self, enabled: bool) -> None:
        """Show cancel affordance and wire Escape on the input."""
        self._edit_mode = enabled
        self._input.set_edit_mode(enabled)
        self._cancel_btn.setVisible(enabled)
        if enabled:
            self._cancel_btn.setFlat(False)
        else:
            self._cancel_btn.setFlat(True)
        self._sync_attachments_row_visibility()

    def set_models(self, entries: list[AiModelEntry]) -> None:
        """Store enabled models and refresh selection."""
        self._configured_model_count = len(entries)
        self._models = [e for e in entries if model_entry_enabled(e)]
        ids = {e["id"] for e in self._models}
        self._current_model_id = self._pick_model_id(ids)
        self._sync_model_state(self._current_model_id)
        has_enabled = bool(self._models)
        self._model_btn.setEnabled(has_enabled or self._configured_model_count > 0)
        if not self._run_busy:
            self._send_btn.setEnabled(has_enabled)
        self._refresh_model_button()
        entry = self._entry_by_id(self._current_model_id) if self._current_model_id else None
        total = effective_run_context_tokens(entry) if entry is not None else 0
        self._context_ring.set_usage(0, total)

    def set_run_busy(self, busy: bool) -> None:
        """Toggle send vs stop while a chat run is in flight."""
        self._run_busy = busy
        if busy:
            self._send_btn.setIconSize(QSize(CHAT_STOP_ICON_SIZE, CHAT_STOP_ICON_SIZE))
            self._send_btn.setIcon(chat_stop_icon())
            self._send_btn.setToolTip("Stop")
            self._send_btn.setEnabled(True)
        else:
            self._send_btn.setIcon(phi("paper-plane-right", color="#ffffff"))
            self._send_btn.setToolTip("Send (Enter)")
            self._send_btn.setEnabled(bool(self._models))

    def set_send_enabled(self, enabled: bool) -> None:
        """Enable or disable send when idle."""
        if self._run_busy:
            return
        self._send_btn.setEnabled(enabled and bool(self._models))

    def restore_text(self, text: str) -> None:
        """Put the prompt body into the input; lift any attachment trailer into chips.

        Inline edit used to dump the composed ``Attached files:`` trailer into the
        compact text field, where long URI lines overlapped Agent / Cancel / Send.
        The trailer is lifted into chips the same way the read-only bubble shows it,
        and :meth:`composed_prompt` writes it back on submit.
        """
        body, attachments = split_prompt_attachments(text)
        self.clear_attachments()
        self._input.setPlainText(body)
        for attachment in attachments:
            self._add_prompt_attachment(attachment)
        self._sync_attachments_row_visibility()
        self._input.setFocus()

    def clear_input(self) -> None:
        """Clear the prompt input."""
        self._input.clear()

    def plain_text(self) -> str:
        """Return trimmed prompt body text (without the attachment trailer)."""
        return self._input.toPlainText().strip()

    def composed_prompt(self) -> str:
        """Return the full prompt including any attachment trailer for send/edit."""
        body = self.plain_text()
        if self._prompt_attachments:
            return compose_prompt_with_prompt_attachments(body, self._prompt_attachments)
        if self._attachments:
            return compose_prompt_with_attachments(body, self._attachments)
        return body

    def current_model_id(self) -> str | None:
        """Return the selected model id."""
        return self._current_model_id

    def current_model_entry(self) -> AiModelEntry | None:
        """Return the selected model entry, if any."""
        if self._current_model_id is None:
            return None
        return self._entry_by_id(self._current_model_id)

    def configured_model_count(self) -> int:
        """Return how many models exist in Settings (enabled or not)."""
        return self._configured_model_count

    def current_mode(self) -> str:
        """Return agent mode (``agent`` / ``ask`` / ``plan``)."""
        return self._mode_btn.mode()

    def set_mode(self, mode: str) -> None:
        """Set agent mode without opening the picker."""
        if self.current_mode() == mode:
            return
        self._mode_btn.set_mode(mode)
        self.mode_changed.emit(mode)

    def current_reasoning_effort(self) -> str | None:
        """Return reasoning effort for the current model."""
        return self._reasoning_effort

    def current_run_context_tokens(self) -> int:
        """Return effective run context window for the current model."""
        entry = self.current_model_entry()
        return effective_run_context_tokens(entry) if entry is not None else 0

    def current_thinking_enabled(self) -> str | None:
        """Return ``on``/``off`` when the model supports thinking."""
        entry = self.current_model_entry()
        if entry is None or not entry.get("thinking"):
            return None
        return thinking_enabled_for_entry(entry)

    def current_agent_id(self) -> str | None:
        """Return agent id from the last applied send snapshot."""
        return self._agent_id

    def select_model_if_available(self, model_id: str) -> bool:
        """Select *model_id* when present in the enabled model list."""
        if model_id not in {entry["id"] for entry in self._models}:
            return False
        self._apply_model_pick(model_id, persist=False)
        return True

    def apply_model_pick(self, model_id: str, *, persist: bool = True) -> None:
        """Apply a model selection from the shared picker popup."""
        self._apply_model_pick(model_id, persist=persist)

    def sync_model_settings(self, model_id: str) -> None:
        """Reload persisted per-model settings after the settings dialog."""
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
                self._context_ring.set_usage(0, effective_run_context_tokens(entry))
            self.model_changed.emit(model_id)

    def apply_send_snapshot(self, snapshot: UserMessageSendSnapshot) -> None:
        """Restore composer controls from a per-send snapshot."""
        from services.ai.chat.agent_registry import DEFAULT_AGENT_ID

        model_id = snapshot.get("send_model_id")
        if isinstance(model_id, str) and model_id:
            self.select_model_if_available(model_id)
        mode = snapshot.get("send_mode")
        if isinstance(mode, str) and mode.strip():
            self.set_mode(mode.strip())
        agent_id = snapshot.get("send_agent_id")
        self._agent_id = (
            str(agent_id).strip()
            if isinstance(agent_id, str) and agent_id.strip()
            else DEFAULT_AGENT_ID
        )
        effort = snapshot.get("send_reasoning_effort")
        if isinstance(effort, str) and effort.strip():
            self._reasoning_effort = effort.strip().lower()

    def read_send_snapshot(self) -> UserMessageSendSnapshot:
        """Capture current composer settings for persistence."""
        from services.ai.chat.agent_registry import DEFAULT_AGENT_ID
        from services.ai.chat.session_service import UserMessageSendSnapshot

        return UserMessageSendSnapshot(
            send_model_id=self._current_model_id,
            send_mode=self.current_mode(),
            send_agent_id=self._agent_id or DEFAULT_AGENT_ID,
            send_reasoning_effort=self._reasoning_effort,
            send_thinking_enabled=self.current_thinking_enabled(),
            send_run_context_tokens=self.current_run_context_tokens(),
        )

    def set_context_usage(self, used_tokens: int, total_tokens: int) -> None:
        """Update the context ring display."""
        self._context_ring.set_usage(used_tokens, total_tokens)

    def attachments(self) -> list[str]:
        """Return attached file paths (docked composer uploads)."""
        return list(self._attachments)

    def clear_attachments(self) -> None:
        """Drop every attachment chip, typically after a send."""
        if not self._attachments and not self._prompt_attachments:
            return
        self._attachments.clear()
        self._prompt_attachments.clear()
        while self._attachments_layout.count() > 1:
            item = self._attachments_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._attachments_row.hide()
        self.attachments_changed.emit(self.attachments())

    def model_button_label(self) -> str:
        """Plain-text model button label for tests."""
        parts = self._model_button_parts()
        if parts is None:
            return _NO_MODELS_TEXT
        bits = [parts[0]]
        if parts[1]:
            bits.append(parts[1])
        if parts[2]:
            bits.append(parts[2])
        return "  ·  ".join(bits)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _sync_attachments_row_visibility(self) -> None:
        """Show the chip row for docked uploads or inline-edit restored trailers."""
        has = bool(self._attachments) or bool(self._prompt_attachments)
        # Compact mode hides the row on the docked composer, but inline edit is
        # also compact and must still show restored attachment chips.
        self._attachments_row.setVisible(has and (not self._compact or self._edit_mode))

    def _on_submit(self) -> None:
        """Emit submit or stop depending on run state."""
        if self._run_busy:
            self.stop_requested.emit()
            return
        if not self._send_btn.isEnabled():
            return
        if not self.plain_text() and not self._attachments and not self._prompt_attachments:
            return
        self.submit_requested.emit()

    def _on_attach(self) -> None:
        """Open file picker and add attachment chips."""
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach file")
        added = False
        for path in paths:
            if path and path not in self._attachments:
                self._attachments.append(path)
                self._add_attachment_chip(path)
                added = True
        if added:
            self._sync_attachments_row_visibility()
            self.attachments_changed.emit(self.attachments())

    def _add_attachment_chip(self, path: str) -> None:
        name = Path(path).name
        chip = QPushButton(f"{self._elided_chip_name(name)}  x")
        chip.setObjectName("aiChatAttachmentChip")
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setToolTip(f"Remove {path}")
        chip.clicked.connect(lambda: self._remove_attachment(path, chip))
        self._attachments_layout.insertWidget(self._attachments_layout.count() - 1, chip)

    def _add_prompt_attachment(self, attachment: PromptAttachment) -> None:
        """Add a chip for an attachment already stored in the session (edit restore)."""
        if any(row.reference == attachment.reference for row in self._prompt_attachments):
            return
        self._prompt_attachments.append(attachment)
        chip = QPushButton(f"{self._elided_chip_name(attachment.name)}  x")
        chip.setObjectName("aiChatAttachmentChip")
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setToolTip(f"Remove {attachment.name}\n{attachment.reference}")
        chip.clicked.connect(lambda: self._remove_prompt_attachment(attachment, chip))
        self._attachments_layout.insertWidget(self._attachments_layout.count() - 1, chip)

    def _elided_chip_name(self, name: str) -> str:
        """Shorten long filenames so chips stay compact in the composer row."""
        # Match the read-only user-bubble chip max width (~200px of text).
        metrics = self.fontMetrics()
        return metrics.elidedText(name, Qt.TextElideMode.ElideMiddle, 200)

    def _remove_attachment(self, path: str, chip: QPushButton) -> None:
        if path in self._attachments:
            self._attachments.remove(path)
        chip.setParent(None)
        chip.deleteLater()
        self._sync_attachments_row_visibility()
        self.attachments_changed.emit(self.attachments())

    def _remove_prompt_attachment(
        self,
        attachment: PromptAttachment,
        chip: QPushButton,
    ) -> None:
        self._prompt_attachments = [
            row for row in self._prompt_attachments if row.reference != attachment.reference
        ]
        chip.setParent(None)
        chip.deleteLater()
        self._sync_attachments_row_visibility()
        self.attachments_changed.emit(self.attachments())

    def _entry_by_id(self, model_id: str) -> AiModelEntry | None:
        for entry in self._models:
            if entry["id"] == model_id:
                return entry
        return None

    def _pick_model_id(self, ids: set[str]) -> str | None:
        if self._current_model_id in ids:
            return self._current_model_id
        stored = AiConfig.get_chat_model_id()
        if stored in ids:
            return stored
        return self._models[0]["id"] if self._models else None

    def _effective_effort(self, entry: AiModelEntry) -> str | None:
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
        self._reasoning_effort = None
        if not model_id:
            return
        entry = self._entry_by_id(model_id)
        if entry is None:
            return
        self._reasoning_effort = self._effective_effort(entry)

    def _model_button_parts(self) -> tuple[str, str | None, str | None] | None:
        if not self._models or self._current_model_id is None:
            if self._configured_model_count > 0:
                return (_NO_ENABLED_MODELS_TEXT, None, None)
            return None
        entry = self._entry_by_id(self._current_model_id)
        if entry is None:
            return None
        name = entry.get("label") or entry["model"]
        ctx_val: str | None = None
        ctx_tokens = effective_run_context_tokens(entry)
        if ctx_tokens > 0:
            ctx_val = format_run_context_tokens(ctx_tokens)
        effort_val: str | None = None
        effort = self._reasoning_effort or self._effective_effort(entry)
        if effort:
            effort_val = format_reasoning_effort(effort)
        return (name, ctx_val, effort_val)

    def _refresh_model_button(self) -> None:
        self._model_btn.set_parts(self._model_button_parts())

    def _apply_model_pick(self, model_id: str, *, persist: bool) -> None:
        self._current_model_id = model_id
        if persist:
            AiConfig.set_chat_model_id(model_id)
        self._sync_model_state(model_id)
        self._refresh_model_button()
        entry = self._entry_by_id(model_id)
        if entry is not None:
            self._context_ring.set_usage(0, effective_run_context_tokens(entry))
        self.model_changed.emit(model_id)


__all__ = ["AiChatComposer"]
