"""Tests for AI chat smooth scrolling."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from ui.sidebar.ai import AiChatPanel

from .test_chat_panel_streaming import (
    _drain_smooth_scroll,
    _ensure_transcript_scroll_range,
    _wheel_on_transcript,
)


def test_smooth_wheel_animates_before_settling(qapp: QApplication, qtbot) -> None:
    """Wheel input animates across multiple ticks instead of jumping once."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    _ensure_transcript_scroll_range(panel, qapp)
    bar = panel._scroll.verticalScrollBar()
    if bar.maximum() <= bar.singleStep():
        pytest.skip("no scroll range in test environment")
    start_pos = max(bar.maximum() // 2, bar.singleStep() * 5)
    start_pos = min(start_pos, bar.maximum())
    bar.setValue(start_pos)
    qapp.processEvents()
    start = bar.value()
    if start <= 0:
        pytest.skip("could not position transcript away from top in test environment")
    _wheel_on_transcript(panel, delta_y=120)
    qapp.processEvents()
    mid = bar.value()
    _drain_smooth_scroll(panel, qapp, qtbot)
    end = bar.value()
    assert end < start
    assert mid != start or end != start


def test_programmatic_scroll_cancels_smooth_animation(qapp: QApplication, qtbot) -> None:
    """Instant programmatic scroll cancels an in-flight smooth animation."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    _ensure_transcript_scroll_range(panel, qapp)
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    qapp.processEvents()
    _wheel_on_transcript(panel, delta_y=240)
    qapp.processEvents()
    assert panel._smooth_scroller.is_animating()
    panel._scroll_to_bottom(force=True)
    assert not panel._smooth_scroller.is_animating()
    assert bar.value() == bar.maximum()


def test_sticky_sync_runs_during_and_after_smooth_scroll(qapp: QApplication, qtbot) -> None:
    """Sticky overlay sync tracks smooth-scroll steps and settles with a final pass."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    _ensure_transcript_scroll_range(panel, qapp)
    panel.add_message("user", "first")
    panel.add_message("assistant", "answer\n" * 30)
    panel.add_message("user", "second")
    panel.add_message("assistant", "more\n" * 30)
    qapp.processEvents()
    panel._rebuild_sticky_turn_pairs()
    panel._rebuild_sticky_turn_extents()
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    qapp.processEvents()
    with patch.object(panel, "_sync_sticky_turn_prompt") as sync_mock:
        _wheel_on_transcript(panel, delta_y=120)
        qapp.processEvents()
        assert panel._smooth_scroller.is_animating()
        during_count = sync_mock.call_count
        _drain_smooth_scroll(panel, qapp, qtbot)
        assert sync_mock.call_count >= during_count + 1


def test_smooth_scroll_repeated_wheel_extends_target_without_hanging(
    qapp: QApplication,
    qtbot,
) -> None:
    """Repeated wheel input stacks momentum and settles quickly."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(420, 520)
    _ensure_transcript_scroll_range(panel, qapp)
    bar = panel._scroll.verticalScrollBar()
    if bar.maximum() <= 0:
        pytest.skip("no scroll range in test environment")

    scroller = panel._smooth_scroller
    bar.setValue(bar.maximum())
    qapp.processEvents()
    start = bar.value()
    if start <= 0:
        pytest.skip("could not position transcript away from top in test environment")
    for _ in range(4):
        _wheel_on_transcript(panel, delta_y=120)
    qapp.processEvents()
    assert scroller.is_animating()
    assert scroller._target_value < start
    _drain_smooth_scroll(panel, qapp, qtbot, timeout_ms=600)
    assert not scroller.is_animating()
    assert bar.value() == scroller._target_value
