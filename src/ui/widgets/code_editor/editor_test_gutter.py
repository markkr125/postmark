"""Per-``pm.test`` gutter helpers for :class:`~editor_widget.CodeEditorWidget`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMenu

from ui.widgets.code_editor.gutter import _TEST_GUTTER_WIDTH

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPlainTextEdit

    _TestGutterBase = QPlainTextEdit
else:
    _TestGutterBase = object


class _TestGutterMixin(_TestGutterBase):
    """Mixin providing the per-test script gutter column."""

    _test_gutter_enabled: bool
    _pm_tests: list[dict[str, Any]]
    _test_gutter_area: Any

    def set_test_gutter_enabled(self, enabled: bool) -> None:
        """Show or hide the per-``pm.test`` gutter column."""
        self._test_gutter_enabled = enabled
        self._test_gutter_area.setVisible(enabled)
        self._update_gutter_width()

    def test_gutter_width(self) -> int:
        """Return width of the per-test gutter in pixels (0 when disabled)."""
        return _TEST_GUTTER_WIDTH if self._test_gutter_enabled else 0

    def set_pm_tests(self, tests: list[dict[str, Any]]) -> None:
        """Set ``pm.test`` call sites as ``{name, line}`` (1-based lines)."""
        self._pm_tests = list(tests)
        self._test_gutter_area.update()

    def _line_has_pm_test_at_gutter_y(self, y: float) -> bool:
        """Return True if *y* (test-gutter coords) lies on a line with a ``pm.test`` marker."""
        if not self._test_gutter_enabled or self.test_gutter_width() <= 0:
            return False
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        while block.isValid():
            bottom = top + self.blockBoundingRect(block).height()
            if top <= y < bottom:
                line_1 = block.blockNumber() + 1
                return any(int(t.get("line", 0)) == line_1 for t in self._pm_tests)
            block = block.next()
            top = bottom
        return False

    def test_gutter_clicked(self, y: float, global_pos: QPoint) -> None:
        """Handle click in the per-test gutter at viewport y *y* (widget coords)."""
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        while block.isValid():
            bottom = top + self.blockBoundingRect(block).height()
            if top <= y < bottom:
                line_1 = block.blockNumber() + 1
                for t in self._pm_tests:
                    if int(t.get("line", 0)) == line_1:
                        self._show_test_menu(global_pos, str(t.get("name", "")))
                        return
                return
            block = block.next()
            top = bottom

    def _show_test_menu(self, global_pos: QPoint, name: str) -> None:
        """Show Run/Debug actions for a single named ``pm.test``."""
        menu = QMenu(self)
        run_act = menu.addAction(f"Run test '{name}'")
        debug_act = menu.addAction(f"Debug test '{name}'")
        chosen = menu.exec(global_pos)
        if chosen is run_act:
            self.run_single_test_requested.emit(name)
        elif chosen is debug_act:
            self.debug_single_test_requested.emit(name)
