"""Tests for the ConsolePanel widget."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QApplication

from ui.panels.console_panel import ConsolePanel


class TestConsolePanel:
    """Tests for the debug console panel widget."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """ConsolePanel can be created without errors."""
        panel = ConsolePanel()
        qtbot.addWidget(panel)
        assert panel._output.toPlainText() == ""
        panel.cleanup()

    def test_captures_log_messages(self, qapp: QApplication, qtbot) -> None:
        """ConsolePanel displays messages from the Python logger."""
        panel = ConsolePanel()
        qtbot.addWidget(panel)

        logger = logging.getLogger("test.console")
        logger.warning("hello from test")
        qapp.processEvents()

        text = panel._output.toPlainText()
        assert "hello from test" in text
        panel.cleanup()

    def test_clear(self, qapp: QApplication, qtbot) -> None:
        """Clearing the console removes all text."""
        panel = ConsolePanel()
        qtbot.addWidget(panel)

        logger = logging.getLogger("test.console.clear")
        logger.warning("some message")
        qapp.processEvents()

        panel._clear()
        assert panel._output.toPlainText() == ""
        panel.cleanup()

    def test_cleanup_removes_handler(self, qapp: QApplication, qtbot) -> None:
        """After cleanup, the handler is removed from the root logger."""
        panel = ConsolePanel()
        qtbot.addWidget(panel)
        handler = panel._handler
        assert handler in logging.getLogger().handlers
        panel.cleanup()
        assert handler not in logging.getLogger().handlers
