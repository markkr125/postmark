"""Cursor-style edit flyout for :class:`AiModelPickerPopup` model rows."""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.styling.theme import COLOR_ACCENT, COLOR_BORDER, COLOR_HOVER_BG, COLOR_SOLID_BUTTON_FG
from shiboken6 import Shiboken

from services.ai.ai_config import AiModelEntry
from services.ai.provider_catalog import (
    effective_run_context_tokens,
    format_run_context_tokens,
    run_context_choices,
)
from services.ai.reasoning_effort import (
    OLLAMA_BOOLEAN_LEVELS,
    clamp_effort,
    format_reasoning_effort,
    is_boolean_thinking_efforts,
)


def reasoning_levels_for_entry(entry: AiModelEntry) -> tuple[str, ...]:
    """Leveled reasoning efforts (excludes boolean thinking off/on)."""
    raw = entry.get("reasoning_efforts")
    if not isinstance(raw, list):
        return ()
    levels = tuple(str(e).strip().lower() for e in raw if isinstance(e, str) and str(e).strip())
    if is_boolean_thinking_efforts(levels):
        return ()
    return levels


def thinking_supported(entry: AiModelEntry) -> bool:
    """Whether the model supports boolean thinking (separate from reasoning)."""
    return bool(entry.get("thinking"))


def thinking_enabled_for_entry(entry: AiModelEntry) -> str:
    """Return ``on`` or ``off`` for thinking."""
    stored = entry.get("thinking_enabled")
    if isinstance(stored, str) and stored.strip().lower() in OLLAMA_BOOLEAN_LEVELS:
        return stored.strip().lower()
    default = str(entry.get("thinking_default", "")).strip().lower()
    if default in OLLAMA_BOOLEAN_LEVELS:
        return default
    return "on"


def entry_has_edit_options(entry: AiModelEntry) -> bool:
    """True when the row Edit control can change any setting."""
    if run_context_choices(entry):
        return True
    if thinking_supported(entry):
        return True
    return bool(reasoning_levels_for_entry(entry))


def context_label_for_row(entry: AiModelEntry) -> str:
    """Context tag text for a picker row."""
    return format_run_context_tokens(effective_run_context_tokens(entry))


class _EditMenuRow(QWidget):
    """Base row with compact layout and a gentle hover highlight."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Enable hover tracking for :meth:`paintEvent`."""
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self._hovered = False

    def enterEvent(self, event) -> None:
        """Show hover highlight."""
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Clear hover highlight."""
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def _paint_gentle_hover(self) -> None:
        """Draw a soft hover wash behind row contents."""
        if not self._hovered:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        wash = QColor(COLOR_HOVER_BG)
        wash.setAlpha(72)
        painter.setBrush(wash)
        painter.drawRoundedRect(self.rect().adjusted(1, 0, -1, 0), 3, 3)


class _CheckOptionRow(_EditMenuRow):
    """One selectable row with a trailing checkmark (Cursor-style)."""

    picked = Signal()

    def __init__(self, label: str, *, checked: bool, parent: QWidget | None = None) -> None:
        """Build a clickable row showing *label* and an optional checkmark."""
        super().__init__(parent)
        self.setObjectName("aiModelPickerEditOption")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked = checked

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 6, 2)
        layout.setSpacing(4)

        self._label = QLabel(label)
        self._label.setObjectName("aiModelPickerEditOptionLabel")
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._label, 1)

        self._mark = QLabel("✓" if checked else "")
        self._mark.setObjectName("aiModelPickerEditCheck")
        self._mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._mark.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._mark, 0)

    def set_checked(self, checked: bool) -> None:
        """Update the checkmark visibility."""
        self._checked = checked
        self._mark.setText("✓" if checked else "")

    def paintEvent(self, event) -> None:
        """Paint hover wash then row contents."""
        self._paint_gentle_hover()
        super().paintEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit ``picked`` on left click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.picked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class _PillSwitch(QWidget):
    """iOS-style pill toggle with a sliding white thumb."""

    toggled = Signal(bool)

    _WIDTH = 32
    _HEIGHT = 18
    _THUMB = 14
    _PAD = 2

    def __init__(self, *, checked: bool, parent: QWidget | None = None) -> None:
        """Build a switch in the given on/off state."""
        super().__init__(parent)
        self.setObjectName("aiModelPickerPillSwitch")
        self.setFixedSize(self._WIDTH, self._HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked = checked

    def isChecked(self) -> bool:
        """Return whether the switch is on."""
        return self._checked

    def setChecked(self, checked: bool) -> None:
        """Set on/off without emitting when unchanged."""
        if self._checked == checked:
            return
        self._checked = checked
        self.update()
        self.toggled.emit(checked)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Flip state on left click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, _event: object) -> None:
        """Draw track and thumb."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track = QColor(COLOR_ACCENT if self._checked else COLOR_BORDER)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(
            0, 0, self._WIDTH, self._HEIGHT, self._HEIGHT // 2, self._HEIGHT // 2
        )

        thumb_x = self._WIDTH - self._THUMB - self._PAD if self._checked else self._PAD
        thumb_y = (self._HEIGHT - self._THUMB) // 2
        painter.setBrush(QColor(COLOR_SOLID_BUTTON_FG))
        painter.setPen(QPen(QColor(0, 0, 0, 25), 1))
        painter.drawEllipse(thumb_x, thumb_y, self._THUMB, self._THUMB)


class _ThinkingSwitchRow(_EditMenuRow):
    """Thinking on/off row with a trailing toggle switch."""

    toggled = Signal(bool)

    def __init__(self, *, enabled: bool, parent: QWidget | None = None) -> None:
        """Build the thinking section row."""
        super().__init__(parent)
        self.setObjectName("aiModelPickerEditThinkingRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 6, 2)
        layout.setSpacing(4)

        label = QLabel("Thinking")
        label.setObjectName("aiModelPickerEditOptionLabel")
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(label, 1)

        self._switch = _PillSwitch(checked=enabled)
        self._switch.toggled.connect(self.toggled.emit)
        layout.addWidget(self._switch, 0, Qt.AlignmentFlag.AlignRight)

    def paintEvent(self, event) -> None:
        """Paint hover wash then row contents."""
        self._paint_gentle_hover()
        super().paintEvent(event)


class _OptionSection:
    """Tracks radio-style rows within one categorized section."""

    def __init__(self) -> None:
        self.rows: list[_CheckOptionRow] = []

    def set_checked(self, row: _CheckOptionRow) -> None:
        """Check *row* and clear the others in this section."""
        for item in self.rows:
            item.set_checked(item is row)


class AiModelPickerEditPanel(QFrame):
    """Flyout panel for per-model context, thinking, and reasoning settings."""

    hidden = Signal()
    _instance: ClassVar[AiModelPickerEditPanel | None] = None

    @classmethod
    def instance(cls) -> AiModelPickerEditPanel:
        """Return the shared edit flyout."""
        if cls._instance is not None and not Shiboken.isValid(cls._instance):
            cls._instance = None
        if cls._instance is None:
            cls._instance = AiModelPickerEditPanel()
        return cls._instance

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an empty panel; sections are filled in :meth:`show_for`."""
        super().__init__(parent)
        self.setObjectName("aiModelPickerEditPanel")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedWidth(168)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(0)

        self._on_context: Callable[[str, int], None] | None = None
        self._on_thinking: Callable[[str, str], None] | None = None
        self._on_reasoning: Callable[[str, str], None] | None = None
        self._model_id = ""

    def is_open_for(self, model_id: str) -> bool:
        """True when the flyout is visible for *model_id*."""
        return self.isVisible() and self._model_id == model_id

    def show_for(
        self,
        entry: AiModelEntry,
        model_id: str,
        *,
        on_context: Callable[[str, int], None],
        on_thinking: Callable[[str, str], None],
        on_reasoning: Callable[[str, str], None],
    ) -> None:
        """Populate sections; caller positions via :meth:`AiModelPickerPopup._position_edit_panel`."""
        self._model_id = model_id
        self._on_context = on_context
        self._on_thinking = on_thinking
        self._on_reasoning = on_reasoning
        self._rebuild(entry)
        self.adjustSize()
        self.show()
        self.raise_()

    def hide_panel(self) -> None:
        """Hide the flyout."""
        if not self.isVisible():
            return
        self.hide()
        self._model_id = ""
        self._on_context = None
        self._on_thinking = None
        self._on_reasoning = None
        self.hidden.emit()

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_section_header(self, title: str) -> None:
        header = QLabel(title)
        header.setObjectName("aiModelPickerEditSection")
        self._layout.addWidget(header)

    def _add_radio_section(
        self,
        title: str,
        options: tuple[tuple[str, str], ...],
        current_key: str,
        on_pick: Callable[[str], None],
    ) -> None:
        """Append a section; *options* are ``(internal_key, display_label)``."""
        if not options:
            return
        self._add_section_header(title)
        group = _OptionSection()
        for key, label in options:
            row = _CheckOptionRow(label, checked=key == current_key, parent=self)
            group.rows.append(row)

            def _handler(
                picked_key: str = key,
                picked_row: _CheckOptionRow = row,
                grp: _OptionSection = group,
            ) -> None:
                grp.set_checked(picked_row)
                on_pick(picked_key)

            row.picked.connect(_handler)
            self._layout.addWidget(row)

    def _add_thinking_switch(self, entry: AiModelEntry, model_id: str) -> None:
        """Append the thinking toggle section."""
        enabled = thinking_enabled_for_entry(entry) == "on"

        def on_toggle(checked: bool) -> None:
            if self._on_thinking is not None:
                self._on_thinking(model_id, "on" if checked else "off")

        self._add_section_header("Options")
        row = _ThinkingSwitchRow(enabled=enabled, parent=self)
        row.toggled.connect(on_toggle)
        self._layout.addWidget(row)

    def _rebuild(self, entry: AiModelEntry) -> None:
        """Fill context, thinking, and reasoning sections from *entry*."""
        self._clear_layout()
        mid = self._model_id

        ctx_choices = run_context_choices(entry)
        if ctx_choices:
            current_ctx = effective_run_context_tokens(entry)
            ctx_options = tuple((str(tokens), label) for label, tokens in ctx_choices)

            def on_ctx(key: str) -> None:
                if self._on_context is not None:
                    self._on_context(mid, int(key))

            self._add_radio_section(
                "Context",
                ctx_options,
                str(current_ctx),
                on_ctx,
            )

        if thinking_supported(entry):
            self._add_thinking_switch(entry, mid)

        reasoning_levels = reasoning_levels_for_entry(entry)
        if reasoning_levels:
            stored = entry.get("reasoning_effort")
            current = clamp_effort(
                str(stored) if isinstance(stored, str) else "",
                reasoning_levels,
                str(entry.get("reasoning_default", "")),
            )
            reason_options = tuple((lv, format_reasoning_effort(lv)) for lv in reasoning_levels)

            def on_reason(key: str) -> None:
                if self._on_reasoning is not None:
                    self._on_reasoning(mid, key)

            self._add_radio_section("Reasoning", reason_options, current, on_reason)


def show_row_edit_panel(
    _parent: QWidget,
    entry: AiModelEntry,
    model_id: str,
    *,
    on_context: Callable[[str, int], None],
    on_thinking: Callable[[str, str], None],
    on_reasoning: Callable[[str, str], None],
) -> AiModelPickerEditPanel:
    """Show the categorized edit flyout; returns the panel instance."""
    panel = AiModelPickerEditPanel.instance()
    panel.show_for(
        entry,
        model_id,
        on_context=on_context,
        on_thinking=on_thinking,
        on_reasoning=on_reasoning,
    )
    return panel


__all__ = [
    "AiModelPickerEditPanel",
    "context_label_for_row",
    "entry_has_edit_options",
    "reasoning_levels_for_entry",
    "show_row_edit_panel",
    "thinking_enabled_for_entry",
    "thinking_supported",
]
