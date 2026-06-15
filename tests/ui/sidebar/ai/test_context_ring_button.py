"""Tests for the AI chat context ring button."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.sidebar.ai.chat_panel.context_ring_button import ContextUsageRingButton
from ui.styling.theme_manager import ThemeManager


def test_context_ring_fill_fraction_and_tooltip(qapp: QApplication, qtbot) -> None:
    """The ring exposes its fill fraction and preserves the tooltip format."""
    ring = ContextUsageRingButton()
    qtbot.addWidget(ring)

    ring.set_usage(64_000, 128_000)

    assert ring.fill_fraction() == 0.5
    assert ring.used_tokens() == 64_000
    assert ring.total_tokens() == 128_000
    assert "50%" in ring.toolTip()


def test_context_ring_click_emits_signal(qapp: QApplication, qtbot) -> None:
    """Ring clicks emit the preserved ``context_requested`` signal."""
    ring = ContextUsageRingButton()
    qtbot.addWidget(ring)

    with qtbot.waitSignal(ring.context_requested, timeout=1000):
        ring.click()


def test_context_ring_theme_change_triggers_update(qapp: QApplication, qtbot) -> None:
    """Theme changes request a repaint for existing rings."""
    manager = ThemeManager(qapp)
    updates: list[bool] = []

    class _TrackingRing(ContextUsageRingButton):
        def update(self) -> None:  # type: ignore[override]
            updates.append(True)
            super().update()

    ring = _TrackingRing()
    qtbot.addWidget(ring)

    manager.theme_changed.emit()

    assert updates
