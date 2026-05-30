"""Breakpoint gutter helpers for :class:`~editor_widget.CodeEditorWidget`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QToolTip

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPlainTextEdit

    _BreakpointBase = QPlainTextEdit
else:
    _BreakpointBase = object

_BP_HOVER_TOOLTIP_DELAY_MS = 1000
_BP_HOVER_TOOLTIP_TEXT = "Click to add breakpoint"


class _BreakpointMixin(_BreakpointBase):
    """Mixin providing breakpoint gutter state and interactions."""

    _breakpoints: dict[int, str | None]
    _top_level_lines: set[int]
    _debug_line: int | None
    _show_breakpoint_gutter: bool
    _breakpoint_hover_line: int | None
    _read_only: bool
    _bp_gutter_area: Any
    _line_number_area: Any
    _test_gutter_area: Any
    _fold_gutter_area: Any
    _bp_hover_tip_timer: Any
    _bp_hover_tip_target_line: int | None
    breakpoints_changed: Any

    if TYPE_CHECKING:

        def _set_breakpoint_hover_line(self, line: int | None) -> None: ...
        def _update_gutter_width(self) -> None: ...
        def _refresh_extra_selections(self) -> None: ...
        def _line_at_gutter_y(self, y: float) -> int | None: ...

    def set_breakpoint_gutter_visible(self, visible: bool) -> None:
        """Show or hide the breakpoint gutter column."""
        self._show_breakpoint_gutter = visible
        self._bp_gutter_area.setVisible(visible)
        if not visible:
            self._set_breakpoint_hover_line(None)
        self._update_gutter_width()

    def _schedule_clear_breakpoint_hover_if_left_gutters(self) -> None:
        """After leaving a gutter, clear hover preview once the pointer settles."""
        QTimer.singleShot(0, self._deferred_clear_breakpoint_hover_if_left_gutters)

    def _deferred_clear_breakpoint_hover_if_left_gutters(self) -> None:
        """Clear breakpoint hover if the cursor is no longer over any gutter column."""
        w = QApplication.widgetAt(QCursor.pos())
        gutters = (
            self._line_number_area,
            self._bp_gutter_area,
            self._test_gutter_area,
            self._fold_gutter_area,
        )
        if w is None:
            self._set_breakpoint_hover_line(None)
            return
        for g in gutters:
            if w is g or g.isAncestorOf(w):
                return
        self._set_breakpoint_hover_line(None)

    def _breakpoint_add_preview_active(self) -> bool:
        """True when the hollow breakpoint hover ring is shown for the hover line."""
        line = self._breakpoint_hover_line
        if line is None or not self._show_breakpoint_gutter or self._read_only:
            return False
        if line in self._breakpoints:
            return False
        return self._debug_line is None or line != self._debug_line

    def _schedule_breakpoint_hover_tooltip(self) -> None:
        """After 1s on a row that can add a breakpoint, show a one-shot tooltip."""
        self._bp_hover_tip_timer.stop()
        QToolTip.hideText()
        if not self._breakpoint_add_preview_active():
            self._bp_hover_tip_target_line = None
            return
        self._bp_hover_tip_target_line = self._breakpoint_hover_line
        self._bp_hover_tip_timer.start()

    def _show_bp_hover_tooltip_if_valid(self) -> None:
        """Show gutter tooltip if the pointer is still over a gutter and preview applies."""
        target = self._bp_hover_tip_target_line
        if target is None or self._breakpoint_hover_line != target:
            return
        if not self._breakpoint_add_preview_active():
            return
        w = QApplication.widgetAt(QCursor.pos())
        gutters = (
            self._line_number_area,
            self._bp_gutter_area,
            self._test_gutter_area,
            self._fold_gutter_area,
        )
        if w is None or not any(w is g or g.isAncestorOf(w) for g in gutters):
            return
        QToolTip.showText(QCursor.pos(), _BP_HOVER_TOOLTIP_TEXT, self)

    def toggle_breakpoint(self, line: int) -> bool:
        """Toggle a breakpoint on *line* (0-based). Return True if now set."""
        if line in self._breakpoints:
            del self._breakpoints[line]
            result = False
        else:
            self._breakpoints[line] = None
            result = True
        self._bp_gutter_area.update()
        self._refresh_extra_selections()
        self.breakpoints_changed.emit()
        self._schedule_breakpoint_hover_tooltip()
        return result

    @property
    def breakpoints(self) -> dict[int, str | None]:
        """Return a copy of the current breakpoint map (line → condition)."""
        return dict(self._breakpoints)

    def replace_breakpoints(
        self,
        mapping: dict[int, str | None],
        *,
        emit: bool = False,
    ) -> None:
        """Replace all breakpoints with *mapping* (0-based line → condition)."""
        self._breakpoints = dict(mapping)
        self._bp_gutter_area.update()
        self._refresh_extra_selections()
        if emit:
            self.breakpoints_changed.emit()
        self._schedule_breakpoint_hover_tooltip()

    def set_breakpoint_condition(self, line: int, condition: str | None) -> None:
        """Set or update the condition for a breakpoint on *line* (0-based)."""
        text = (condition or "").strip()
        if line in self._breakpoints:
            self._breakpoints[line] = text or None
        else:
            self._breakpoints[line] = text or None
        self._bp_gutter_area.update()
        self._refresh_extra_selections()
        self.breakpoints_changed.emit()

    def breakpoint_gutter_context_menu(self, y: int, global_pos: Any) -> None:
        """Show add/edit/remove actions for breakpoints on the clicked line."""
        from PySide6.QtWidgets import QInputDialog, QMenu

        line = self._line_at_gutter_y(float(y))
        if line is None or not self._show_breakpoint_gutter or self._read_only:
            return
        menu = QMenu(self)
        if line in self._breakpoints:
            edit_act = menu.addAction("Edit condition…")
            remove_act = menu.addAction("Remove breakpoint")
        else:
            add_act = menu.addAction("Add breakpoint")
            edit_act = None
            remove_act = None
        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        if add_act is not None and chosen is add_act:
            self.toggle_breakpoint(line)
        elif edit_act is not None and chosen is edit_act:
            current = self._breakpoints.get(line) or ""
            text, ok = QInputDialog.getText(
                self,
                "Breakpoint condition",
                "Pause only when (leave empty for unconditional):",
                text=current,
            )
            if ok:
                if line not in self._breakpoints:
                    self._breakpoints[line] = None
                self.set_breakpoint_condition(line, text)
        elif remove_act is not None and chosen is remove_act and line in self._breakpoints:
            del self._breakpoints[line]
            self._bp_gutter_area.update()
            self._refresh_extra_selections()
            self.breakpoints_changed.emit()

    def set_top_level_lines(self, lines: set[int]) -> None:
        """Set lines (0-based) where the step-debugger can pause; empty means style all breakpoints as reachable."""
        self._top_level_lines = set(lines)
        self._bp_gutter_area.update()

    def set_debug_line(self, line: int | None) -> None:
        """Set the highlighted debug line (0-based), or None to clear."""
        self._debug_line = line
        self._bp_gutter_area.update()
        self.viewport().update()
        self._refresh_extra_selections()
        self._schedule_breakpoint_hover_tooltip()
