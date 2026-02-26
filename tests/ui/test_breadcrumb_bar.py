"""Tests for the BreadcrumbBar widget."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.request.breadcrumb_bar import BreadcrumbBar


class TestBreadcrumbBar:
    """Tests for the breadcrumb bar widget."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """BreadcrumbBar can be created without errors."""
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        # Should be empty initially (only a stretch)
        assert bar._layout.count() == 1

    def test_set_path_shows_segments(self, qapp: QApplication, qtbot) -> None:
        """Setting a path creates labels for each segment."""
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        segments = [
            {"name": "Root", "type": "folder", "id": 1},
            {"name": "Sub", "type": "folder", "id": 2},
            {"name": "Request", "type": "request", "id": 10},
        ]
        bar.set_path(segments)
        # 3 labels + 2 separators + 1 stretch = 6
        assert bar._layout.count() == 6

    def test_clear_removes_all(self, qapp: QApplication, qtbot) -> None:
        """Clearing the breadcrumb removes all segments."""
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.set_path(
            [
                {"name": "A", "type": "folder", "id": 1},
                {"name": "B", "type": "request", "id": 2},
            ]
        )
        bar.clear()
        assert bar._layout.count() == 0

    def test_item_clicked_signal(self, qapp: QApplication, qtbot) -> None:
        """Clicking a non-last segment emits item_clicked."""
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        segments = [
            {"name": "Root", "type": "folder", "id": 1},
            {"name": "Request", "type": "request", "id": 10},
        ]
        bar.set_path(segments)

        # The first label (index 0) is clickable ("Root")
        label = bar._layout.itemAt(0).widget()
        with qtbot.waitSignal(bar.item_clicked, timeout=1000) as sig:
            qtbot.mouseClick(label, Qt.MouseButton.LeftButton)
        assert sig.args == ["folder", 1]
