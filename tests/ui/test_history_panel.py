"""Tests for the HistoryPanel widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.history_panel import HistoryPanel


class TestHistoryPanel:
    """Tests for the history panel widget."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """HistoryPanel can be created without errors."""
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        assert len(panel.entries) == 0

    def test_add_entry(self, qapp: QApplication, qtbot) -> None:
        """Adding an entry increases the entry count."""
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.add_entry("GET", "http://example.com", status_code=200, elapsed_ms=42)
        assert len(panel.entries) == 1
        assert panel.entries[0].method == "GET"
        assert panel.entries[0].url == "http://example.com"

    def test_add_multiple_entries(self, qapp: QApplication, qtbot) -> None:
        """Adding multiple entries keeps them in reverse order."""
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.add_entry("GET", "http://a.com")
        panel.add_entry("POST", "http://b.com")
        assert len(panel.entries) == 2
        # Most recent first
        assert panel.entries[0].method == "POST"
        assert panel.entries[1].method == "GET"

    def test_clear(self, qapp: QApplication, qtbot) -> None:
        """Clearing the panel removes all entries."""
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        panel.add_entry("GET", "http://example.com")
        panel.clear()
        assert len(panel.entries) == 0

    def test_max_entries(self, qapp: QApplication, qtbot) -> None:
        """History panel caps at 50 entries."""
        panel = HistoryPanel()
        qtbot.addWidget(panel)
        for i in range(55):
            panel.add_entry("GET", f"http://example.com/{i}")
        assert len(panel.entries) == 50
