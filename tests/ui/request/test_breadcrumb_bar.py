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
        # 2 clickable labels + 1 editable label + 2 separators + 1 stretch = 6
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
        layout_item = bar._layout.itemAt(0)
        assert layout_item is not None
        label = layout_item.widget()
        assert label is not None
        with qtbot.waitSignal(bar.item_clicked, timeout=1000) as sig:
            qtbot.mouseClick(label, Qt.MouseButton.LeftButton)
        assert sig.args == ["folder", 1]

    def test_last_segment_info(self, qapp: QApplication, qtbot) -> None:
        """last_segment_info returns metadata for the last segment."""
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        segments = [
            {"name": "Root", "type": "folder", "id": 1},
            {"name": "My Request", "type": "request", "id": 42},
        ]
        bar.set_path(segments)
        info = bar.last_segment_info
        assert info is not None
        assert info["type"] == "request"
        assert info["id"] == 42
        assert info["name"] == "My Request"

    def test_update_last_segment_text(self, qapp: QApplication, qtbot) -> None:
        """update_last_segment_text changes the displayed name."""
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.set_path(
            [
                {"name": "Root", "type": "folder", "id": 1},
                {"name": "Old Name", "type": "request", "id": 10},
            ]
        )
        bar.update_last_segment_text("New Name")
        assert bar._editable_label is not None
        assert bar._editable_label.text() == "New Name"

    def test_last_segment_renamed_signal(self, qapp: QApplication, qtbot) -> None:
        """Committing a breadcrumb rename emits last_segment_renamed."""
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.set_path(
            [
                {"name": "Root", "type": "folder", "id": 1},
                {"name": "Old Name", "type": "request", "id": 10},
            ]
        )
        assert bar._editable_label is not None
        # Simulate entering edit mode and committing
        bar._editable_label._start_edit()
        bar._editable_label._edit.setText("Renamed")
        with qtbot.waitSignal(bar.last_segment_renamed, timeout=1000) as sig:
            bar._editable_label._commit()
        assert sig.args == ["Renamed"]

    def test_clear_resets_editable_label(self, qapp: QApplication, qtbot) -> None:
        """Clearing removes the editable label reference."""
        bar = BreadcrumbBar()
        qtbot.addWidget(bar)
        bar.set_path([{"name": "X", "type": "request", "id": 1}])
        assert bar._editable_label is not None
        bar.clear()
        assert bar._editable_label is None
        assert bar._last_segment is None
