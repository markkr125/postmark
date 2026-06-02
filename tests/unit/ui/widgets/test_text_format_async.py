"""Tests for async response body formatting."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QWidget

from ui.widgets.text_format_async import (
    AsyncTextFormatRunner,
    FormatTextRunnable,
    FormatTextSignals,
)


def test_format_text_runnable_pretty_json(qapp: QApplication, qtbot) -> None:
    """Runnable pretty-prints JSON on a thread-pool worker."""
    host = QWidget()
    qtbot.addWidget(host)
    signals = FormatTextSignals(host)
    with qtbot.waitSignal(signals.finished, timeout=5000) as blocker:
        runnable = FormatTextRunnable(signals, 1, '{"a":1}', "json", pretty=True)
        runnable.run()
    assert blocker.args[0] == 1
    assert '"a"' in blocker.args[1]
    assert "\n" in blocker.args[1]


def test_async_runner_emits_on_gui_thread(qapp: QApplication, qtbot) -> None:
    """Runner delivers formatted text via ``formatted`` on the main thread."""
    host = QWidget()
    qtbot.addWidget(host)
    runner = AsyncTextFormatRunner(host)
    with qtbot.waitSignal(runner.formatted, timeout=5000) as blocker:
        runner.format_async(3, '{"b":2}', "json", pretty=True)
    assert blocker.args[0] == 3
    assert '"b"' in blocker.args[1]
