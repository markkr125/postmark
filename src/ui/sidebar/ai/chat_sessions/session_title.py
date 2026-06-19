"""Flyout session title with text-hugging hover chrome and inline rename."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QEnterEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QWidget
from shiboken6 import Shiboken

from ui.styling.icons import phi
from ui.styling.theme import COLOR_TEXT_MUTED
from ui.widgets.tree_rename_overlay import TreeRenameClickAway

_AI_SESSION_TITLE_PLACEHOLDER = "New chat"
_PENCIL_ICON_SIZE_PX = 14
_PENCIL_SLOT_WIDTH_PX = 18
_TITLE_INLINE_H_PAD_PX = 4
_TITLE_INLINE_V_PAD_PX = 2
_TITLE_INLINE_SPACING_PX = 4


class _AiChatSessionTitleInline(QWidget):
    """Tight title + pencil group that toggles hover chrome."""

    def __init__(
        self,
        on_hover: Callable[[bool], None],
        on_click: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        """Build the inline group and forward hover / click to callbacks."""
        super().__init__(parent)
        self.setObjectName("aiChatSessionTitleInline")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self._on_hover = on_hover
        self._on_click = on_click
        self._click_enabled = False

    def set_click_enabled(self, enabled: bool) -> None:
        """Allow or block click-to-rename on the inline title band."""
        self._click_enabled = enabled

    def enterEvent(self, event: QEnterEvent) -> None:
        """Reveal hover chrome when the pointer enters the title text band."""
        self._on_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """Hide hover chrome when the pointer leaves the title text band."""
        self._on_hover(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Start rename when the user clicks the title band."""
        if self._click_enabled and event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
            event.accept()
            return
        super().mousePressEvent(event)


class AiChatSessionTitle(QWidget):
    """Session title with text-hugging hover chrome, pencil affordance, and rename."""

    rename_committed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the muted subtitle under the AI assistant headline."""
        super().__init__(parent)
        self.setObjectName("aiChatSessionTitleSlot")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._full_text = _AI_SESSION_TITLE_PLACEHOLDER
        self._hovered = False
        self._rename_enabled = False
        self._editing = False
        self._pre_edit_text = ""
        self._rename_edit: QLineEdit | None = None
        self._click_away: TreeRenameClickAway | None = None

        self._slot_layout = QHBoxLayout(self)
        self._slot_layout.setContentsMargins(0, 0, 0, 0)
        self._slot_layout.setSpacing(0)

        self._inline = _AiChatSessionTitleInline(
            self._set_hovered,
            self._begin_rename,
            self,
        )
        self._inline_layout = QHBoxLayout(self._inline)
        self._inline_layout.setContentsMargins(
            _TITLE_INLINE_H_PAD_PX,
            _TITLE_INLINE_V_PAD_PX,
            _TITLE_INLINE_H_PAD_PX,
            _TITLE_INLINE_V_PAD_PX,
        )
        self._inline_layout.setSpacing(_TITLE_INLINE_SPACING_PX)

        self._label = QLabel(self._inline)
        self._label.setObjectName("aiChatSessionTitle")
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._pencil_slot = QWidget(self._inline)
        self._pencil_slot.setFixedSize(_PENCIL_SLOT_WIDTH_PX, _PENCIL_ICON_SIZE_PX + 2)
        pencil_layout = QHBoxLayout(self._pencil_slot)
        pencil_layout.setContentsMargins(0, 0, 0, 0)
        self._pencil = QLabel(self._pencil_slot)
        self._pencil.setObjectName("aiChatSessionTitlePencil")
        self._pencil.setPixmap(
            phi("pencil-simple", size=_PENCIL_ICON_SIZE_PX, color=COLOR_TEXT_MUTED).pixmap(
                _PENCIL_ICON_SIZE_PX,
                _PENCIL_ICON_SIZE_PX,
            )
        )
        self._pencil.setFixedSize(_PENCIL_ICON_SIZE_PX, _PENCIL_ICON_SIZE_PX)
        self._pencil.hide()
        pencil_layout.addWidget(self._pencil, 0, Qt.AlignmentFlag.AlignCenter)

        self._inline_layout.addWidget(self._label, 0)
        self._inline_layout.addWidget(self._pencil_slot, 0)

        self._slot_layout.addWidget(
            self._inline,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self._slot_layout.addStretch(1)

        self._apply_tooltips()
        self._apply_elide()

    def set_full_text(self, title: str) -> None:
        """Store *title* and repaint with elision for the current width."""
        if self._editing:
            return
        cleaned = title.strip()
        self._full_text = cleaned or _AI_SESSION_TITLE_PLACEHOLDER
        self._apply_tooltips()
        self._apply_elide()

    def set_rename_enabled(self, enabled: bool) -> None:
        """Enable click-to-rename when a persisted session is active."""
        self._rename_enabled = enabled
        self._inline.set_click_enabled(enabled and not self._editing)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Re-elide when the flyout width changes."""
        super().resizeEvent(event)
        if self._editing and self._rename_edit is not None:
            self._rename_edit.setMinimumWidth(self._rename_edit_width())
            return
        self._apply_elide()

    def _rename_click_away(self) -> TreeRenameClickAway:
        """Return a click-away helper parented to this widget."""
        if self._click_away is None:
            self._click_away = TreeRenameClickAway(self)
        return self._click_away

    def _set_hovered(self, hovered: bool) -> None:
        """Show gentle inline chrome and the pencil icon on hover."""
        if self._hovered == hovered:
            return
        self._hovered = hovered
        if not self._editing:
            self._pencil.setVisible(hovered and self._rename_enabled)
        self._inline.setProperty("titleHovered", "true" if hovered else "false")
        style = self._inline.style()
        style.unpolish(self._inline)
        style.polish(self._inline)
        self._inline.update()
        cursor = (
            Qt.CursorShape.IBeamCursor
            if hovered and self._rename_enabled
            else Qt.CursorShape.ArrowCursor
        )
        for widget in (self._inline, self._label, self._pencil_slot, self._pencil):
            widget.setCursor(cursor)

    def _rename_edit_width(self) -> int:
        """Return the width available for the full-width rename editor."""
        return max(120, self.width())

    def _begin_rename(self) -> None:
        """Swap the elided label for a full-width inline editor."""
        if not self._rename_enabled or self._editing:
            return
        self._editing = True
        self._pre_edit_text = self._full_text
        self._inline.set_click_enabled(False)
        self._inline.hide()

        edit = QLineEdit(self)
        edit.setObjectName("aiChatSessionTitleEdit")
        edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        edit_text = self._full_text
        if edit_text == _AI_SESSION_TITLE_PLACEHOLDER:
            edit_text = ""
        edit.setText(edit_text)
        edit.setMinimumWidth(self._rename_edit_width())
        self._rename_edit = edit
        self._slot_layout.insertWidget(0, edit, 1)
        edit.selectAll()
        edit.setFocus()
        self._arm_rename_edit(edit)

    def _arm_rename_edit(self, line_edit: QLineEdit) -> None:
        """Wire Enter, click-away, and Escape to save the edited title."""
        line_edit.setProperty("rename_armed", False)

        def _save() -> None:
            if not Shiboken.isValid(line_edit):
                return
            self._commit_rename()

        line_edit.returnPressed.connect(_save)

        def _arm() -> None:
            if not Shiboken.isValid(line_edit):
                return
            line_edit.setProperty("rename_armed", True)

        arm_timer = QTimer(line_edit)
        arm_timer.setSingleShot(True)
        arm_timer.timeout.connect(_arm)
        arm_timer.start(0)
        self._rename_click_away().arm(
            line_edit,
            on_commit=_save,
            on_cancel=_save,
        )

    def _commit_rename(self) -> None:
        """Persist the edited title locally and emit when it changed."""
        edit = self._rename_edit
        if not self._editing or edit is None:
            return
        self._rename_click_away().release()
        new_title = edit.text().strip()
        previous = self._pre_edit_text
        self._finish_rename_editor()
        if not new_title:
            self.set_full_text(previous)
            return
        if new_title != previous:
            self._full_text = new_title
            self.rename_committed.emit(new_title)
        self.set_full_text(new_title)

    def _finish_rename_editor(self) -> None:
        """Remove the inline editor and restore the elided label."""
        edit = self._rename_edit
        self._editing = False
        self._rename_edit = None
        if edit is not None:
            self._slot_layout.removeWidget(edit)
            edit.deleteLater()
        self._inline.show()
        self._pencil.hide()
        self._inline.set_click_enabled(self._rename_enabled)
        self._inline.setMinimumWidth(0)
        self._inline.setMaximumWidth(16777215)
        self._apply_elide()

    def _apply_tooltips(self) -> None:
        """Expose the full stored title on hover."""
        self.setToolTip(self._full_text)
        self._label.setToolTip(self._full_text)
        self._inline.setToolTip(self._full_text)

    def _apply_elide(self) -> None:
        """Elide the title and shrink the inline group to the visible text width."""
        max_available = max(0, self.width())
        inline_margins = _TITLE_INLINE_H_PAD_PX * 2
        reserved = self._pencil_slot.width() + _TITLE_INLINE_SPACING_PX + inline_margins
        text_budget = max(0, max_available - reserved)
        fm = self._label.fontMetrics()
        elided = fm.elidedText(
            self._full_text,
            Qt.TextElideMode.ElideRight,
            text_budget,
        )
        self._label.setText(elided)
        text_width = fm.horizontalAdvance(elided)
        inline_width = min(max_available, text_width + reserved)
        self._inline.setFixedWidth(max(inline_width, 0))
