"""Tests for the shared BrailleSpinner widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.widgets.busy_spinner import BrailleSpinner


def test_braille_spinner_advances_frames(qapp: QApplication, qtbot) -> None:
    """Starting the spinner advances through animation frames."""
    spinner = BrailleSpinner()
    qtbot.addWidget(spinner)
    assert spinner.frame_index() == 0
    spinner.start()
    qtbot.wait(200)
    assert spinner.frame_index() > 0
    spinner.stop()
