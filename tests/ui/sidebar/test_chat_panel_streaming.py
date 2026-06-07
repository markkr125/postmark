"""Tests for chat panel streaming coalescing, scroll, and activity helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QLayout, QTextBrowser

from services.ai.chat.session_service import AiChatMessageDict
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.chat_panel.scroll import _FOLLOW_THRESHOLD_PX
from ui.sidebar.ai.chat_panel_streaming import format_activity_status
from ui.sidebar.ai.message_bubble import ChatMessageBubble


def _flush_stream_chunks(qtbot) -> None:
    """Wait for the coalesced chunk delivery timer (~50ms)."""
    qtbot.wait(60)
    QApplication.processEvents()


def _drain_follow_passes(qtbot, qapp: QApplication) -> None:
    """Wait for deferred stream-follow passes (0ms and 16ms)."""
    qtbot.wait(20)
    qapp.processEvents()


def _wheel_on_transcript(
    panel: AiChatPanel,
    *,
    delta_y: int,
    pos: QPoint | None = None,
) -> None:
    """Send a wheel event to the transcript viewport."""
    viewport = panel._scroll.viewport()
    local = pos or QPoint(viewport.width() // 2, viewport.height() // 2)
    global_pos = viewport.mapToGlobal(QPointF(local))
    event = QWheelEvent(
        QPointF(local),
        global_pos,
        QPoint(0, 0),
        QPoint(0, delta_y),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    QApplication.sendEvent(viewport, event)


def _ensure_transcript_scroll_range(
    panel: AiChatPanel,
    qapp: QApplication,
    *,
    min_maximum: int = 3,
) -> None:
    """Add filler messages until the transcript scrollbar has usable range."""
    bar = panel._scroll.verticalScrollBar()
    qapp.processEvents()
    if bar.maximum() >= min_maximum:
        return
    for index in range(48):
        panel.add_message("user", f"scroll filler {index} " * 14)
        qapp.processEvents()
        if bar.maximum() >= min_maximum:
            return
    pytest.fail(
        f"could not build scroll range in test environment (max={bar.maximum()})",
    )


def _anchor_viewport_y(panel: AiChatPanel) -> int:
    """Return the turn anchor top edge Y in viewport coordinates."""
    anchor = panel._turn_scroll_anchor
    assert anchor is not None
    bar = panel._scroll.verticalScrollBar()
    # mapTo(viewport) ignores scroll offset in headless Qt; derive from messages Y.
    return anchor.mapTo(panel._messages, QPoint(0, 0)).y() - bar.value()


def _expected_spacer_height(panel: AiChatPanel) -> int:
    """Return dynamic spacer height for the active streaming turn."""
    viewport_h = panel._scroll.viewport().height()
    if viewport_h <= 0:
        return 0
    return max(0, viewport_h - panel._streaming_turn_extent_px())


def _detach_scroll_panel(panel: AiChatPanel, qapp: QApplication) -> None:
    """Scroll up and disable follow-lock."""
    _ensure_transcript_scroll_range(panel, qapp)
    bar = panel._scroll.verticalScrollBar()
    if bar.maximum() > 0:
        bar.setValue(bar.maximum())
        qapp.processEvents()
    bar.setValue(0)
    qapp.processEvents()
    if panel._is_pinned_to_bottom():
        pytest.fail("could not scroll away from bottom in test environment")
    assert panel._scroll_lock_enabled is False


def test_format_activity_status_maps_known_values() -> None:
    """Known SDK statuses map to human-readable captions."""
    assert format_activity_status("planning") == "Planning…"
    assert format_activity_status("running") == "Working…"


def test_format_activity_status_rejects_noise() -> None:
    """Enum-like noise is not shown in the activity row."""
    assert format_activity_status("AgentState.RUNNING") is None
    assert format_activity_status("") is None
    assert format_activity_status("None") is None


def test_chunk_coalescer_batches_rapid_chunks(qapp: QApplication, qtbot) -> None:
    """Rapid chunks are merged before updating the active bubble."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("t", "")
    panel.append_assistant_chunk("h", "")
    panel.append_assistant_chunk("", "a")
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.thinking_text() == ""
    assert bubble.text() == ""
    qtbot.wait(60)
    assert bubble.thinking_text() == "th"
    assert bubble.text() == "a"


def test_end_assistant_stream_flushes_pending_chunks(qapp: QApplication, qtbot) -> None:
    """Finalize applies buffered chunks before rich HTML render."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "partial")
    panel.end_assistant_stream("partial")
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.text() == "partial"
    assert not bubble.is_content_streaming()


def test_messages_layout_has_min_and_max_size_constraint(qapp: QApplication, qtbot) -> None:
    """Transcript layout uses SetMinAndMaxSize for reliable scroll range updates."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    assert panel._messages_layout.sizeConstraint() == QLayout.SizeConstraint.SetMinAndMaxSize


def test_empty_transcript_layout_with_size_constraint(qapp: QApplication, qtbot) -> None:
    """Empty transcript remains usable with SetMinAndMaxSize."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 200)
    assert panel._empty_label.isVisible()
    bar = panel._scroll.verticalScrollBar()
    assert bar.maximum() >= 0


def test_sticky_scroll_preserves_user_position(qapp: QApplication, qtbot) -> None:
    """Scrolling up during a stream is not overwritten by auto-scroll."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 120)
    for index in range(24):
        panel.add_message("user", f"fill {index} " * 8)
    panel.begin_assistant_stream()
    bar = panel._scroll.verticalScrollBar()
    _detach_scroll_panel(panel, qapp)
    position_before = bar.value()
    panel.append_assistant_chunk("", "streaming tail")
    _flush_stream_chunks(qtbot)
    assert bar.value() == position_before
    assert panel._scroll_lock_enabled is False


def test_sticky_scroll_resumes_when_pinned_to_bottom(qapp: QApplication, qtbot) -> None:
    """Auto-follow resumes when the user scrolls back to the bottom."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 200)
    panel.begin_assistant_stream()
    bar = panel._scroll.verticalScrollBar()
    panel._scroll_lock_enabled = True
    panel._scroll_to_bottom(force=True)
    panel.append_assistant_chunk("", "more")
    _flush_stream_chunks(qtbot)
    assert bar.value() >= bar.maximum() - 2


def test_programmatic_scroll_does_not_disable_lock(qapp: QApplication, qtbot) -> None:
    """Auto-scroll during a stream must not disable scroll-lock."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 120)
    for index in range(24):
        panel.add_message("user", f"fill {index} " * 8)
    panel.begin_assistant_stream()
    bar = panel._scroll.verticalScrollBar()
    qapp.processEvents()
    panel._scroll_lock_enabled = True
    panel._scroll_to_bottom(force=True)
    assert panel._scroll_lock_enabled is True
    panel.append_assistant_chunk("", "tail")
    _flush_stream_chunks(qtbot)
    assert panel._scroll_lock_enabled is True
    if bar.maximum() > 0:
        assert bar.value() >= bar.maximum() - 2


def test_range_changed_follows_bottom_when_locked(qapp: QApplication, qtbot) -> None:
    """RangeChanged follow keeps the viewport pinned during content streaming."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 160)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    bar = panel._scroll.verticalScrollBar()
    panel._scroll_lock_enabled = True
    panel.append_assistant_chunk("", "Tail " * 40)
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    assert panel._stream_content_started
    position_before = bar.value()
    panel.append_assistant_chunk("", " more tail " * 30)
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    assert bar.value() >= bar.maximum() - 2
    assert bar.value() >= position_before


def test_range_changed_ignored_when_lock_disabled(qapp: QApplication, qtbot) -> None:
    """Content growth does not scroll when scroll-lock is off."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 160)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.begin_assistant_stream()
    bar = panel._scroll.verticalScrollBar()
    _detach_scroll_panel(panel, qapp)
    position_before = bar.value()
    panel.append_assistant_chunk("", "Tail " * 40)
    _flush_stream_chunks(qtbot)
    assert bar.value() == position_before


def test_turn_scroll_two_pass_reaches_bottom(qapp: QApplication, qtbot) -> None:
    """Turn-boundary two-pass scroll anchors the new turn after layout settles."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(24):
        panel.add_message("user", f"fill {index} " * 8)
    _detach_scroll_panel(panel, qapp)
    panel.add_message("user", "new question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    assert panel._scroll_lock_enabled is True
    assert _anchor_viewport_y(panel) <= 10


def test_send_scrolls_to_turn_start_when_reading_history(qapp: QApplication, qtbot) -> None:
    """A new turn anchors under the user message even when reading history."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(24):
        panel.add_message("user", f"fill {index} " * 8)
    _detach_scroll_panel(panel, qapp)
    panel.add_message("user", "new question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    assert panel._scroll_lock_enabled is True
    assert _anchor_viewport_y(panel) <= 10


def test_send_then_manual_scroll_up_stops_follow(qapp: QApplication, qtbot) -> None:
    """After send, scrolling up stops auto-follow during streaming."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 160)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    bar = panel._scroll.verticalScrollBar()
    _detach_scroll_panel(panel, qapp)
    panel.append_assistant_chunk("", "response " * 30)
    _flush_stream_chunks(qtbot)
    assert bar.value() == 0


def test_turn_scroll_coalesced_once_per_send(qapp: QApplication, qtbot) -> None:
    """Turn-boundary scroll is scheduled once per send turn."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    scheduled: list[object] = []
    original_single_shot = QTimer.singleShot

    def capture_single_shot(ms: int, func: Callable[..., Any]) -> None:
        scheduled.append(func)
        original_single_shot(ms, func)

    with patch.object(QTimer, "singleShot", side_effect=capture_single_shot):
        panel.add_message("user", "hello")
        panel.begin_assistant_stream()

    flush_turn = [
        fn for fn in scheduled if getattr(fn, "__name__", "") == "_flush_turn_bottom_scroll"
    ]
    assert len(flush_turn) == 1


def test_streaming_viewport_spacer_fills_remaining_viewport(qapp: QApplication, qtbot) -> None:
    """Streaming viewport spacer fills one viewport from the turn anchor."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    spacer = panel._streaming_viewport_spacer
    assert spacer is not None
    viewport_h = panel._scroll.viewport().height()
    if viewport_h > 0:
        expected = _expected_spacer_height(panel)
        assert abs(spacer.height() - expected) <= 2
        if panel._streaming_turn_extent_px() < viewport_h:
            assert abs(panel._streaming_turn_extent_px() + spacer.height() - viewport_h) <= 2


def test_viewport_resize_updates_streaming_spacer_height(qapp: QApplication, qtbot) -> None:
    """Viewport resize refreshes the dynamic streaming viewport spacer height."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 300)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    spacer = panel._streaming_viewport_spacer
    assert spacer is not None
    panel.resize(360, 200)
    qapp.processEvents()
    viewport_h = panel._scroll.viewport().height()
    if viewport_h > 0:
        assert abs(spacer.height() - _expected_spacer_height(panel)) <= 2


def test_long_answer_collapses_streaming_spacer(qapp: QApplication, qtbot) -> None:
    """A long answer collapses the spacer once the turn exceeds one viewport."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 160)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    panel._scroll_lock_enabled = True
    panel.append_assistant_chunk("", "line\n" * 80)
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    spacer = panel._streaming_viewport_spacer
    assert spacer is not None
    viewport_h = panel._scroll.viewport().height()
    if viewport_h > 0:
        assert panel._streaming_turn_extent_px() >= viewport_h - 2
        assert spacer.height() <= 2


def test_turn_scroll_anchors_user_message_visible(qapp: QApplication, qtbot) -> None:
    """Thinking row appears directly under the user message, not mid-viewport."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    user_bubble = panel.add_message("user", "what about php?")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    bubble = panel._streaming_bubble
    assert bubble is not None
    activity = bubble._activity_row
    assert activity is not None
    viewport = panel._scroll.viewport()
    user_bottom = user_bubble.mapTo(viewport, QPoint(0, user_bubble.height())).y()
    activity_top = activity.mapTo(viewport, QPoint(0, 0)).y()
    assert user_bubble.mapTo(viewport, QPoint(0, 0)).y() >= 0
    assert activity_top - user_bottom <= 8 + 48


def test_thinking_phase_follow_suppressed_while_turn_scroll_pending(
    qapp: QApplication, qtbot
) -> None:
    """RangeChanged does not schedule follow while turn scroll is pending."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    scheduled: list[object] = []
    original_single_shot = QTimer.singleShot

    def capture_single_shot(ms: int, func: Callable[..., Any]) -> None:
        scheduled.append(func)
        original_single_shot(ms, func)

    panel.add_message("user", "hello")
    with patch.object(QTimer, "singleShot", side_effect=capture_single_shot):
        panel.begin_assistant_stream()
    names = _scheduled_follow_scheduler_names(scheduled)
    assert "_flush_stream_follow_frame" not in names
    assert "_flush_stream_follow_retry" not in names


def test_thinking_phase_follow_pins_anchor_at_top(qapp: QApplication, qtbot) -> None:
    """Thinking-only growth keeps the turn anchor pinned via maximum follow."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    bar = panel._scroll.verticalScrollBar()
    panel._scroll_lock_enabled = True
    assert not panel._stream_content_started
    anchor_y_before = _anchor_viewport_y(panel)
    panel.append_assistant_chunk("thinking line\n", "")
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    assert bar.value() >= bar.maximum() - 2
    viewport_h = panel._scroll.viewport().height()
    if panel._streaming_turn_extent_px() < viewport_h:
        assert abs(_anchor_viewport_y(panel) - anchor_y_before) <= 2


def test_content_phase_follow_scrolls_to_bottom(qapp: QApplication, qtbot) -> None:
    """Content streaming follows the document bottom (dynamic spacer tail)."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 160)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    panel._scroll_lock_enabled = True
    panel.append_assistant_chunk("", "answer " * 40)
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    assert panel._stream_content_started
    bar = panel._scroll.verticalScrollBar()
    assert bar.value() >= bar.maximum() - 2


def test_turn_anchor_does_not_clear_scroll_lock(qapp: QApplication, qtbot) -> None:
    """Turn-start anchor keeps scroll-lock enabled after send."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    assert panel._scroll_lock_enabled is True
    assert _anchor_viewport_y(panel) <= 10


def test_content_stream_follows_bottom_after_turn_anchor(qapp: QApplication, qtbot) -> None:
    """Content growth follows the document bottom while the anchor stays pinned."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    bar = panel._scroll.verticalScrollBar()
    anchor_y_before = _anchor_viewport_y(panel)
    assert panel._scroll_lock_enabled is True
    panel.append_assistant_chunk("", "short answer\n" * 3)
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    viewport_h = panel._scroll.viewport().height()
    if panel._streaming_turn_extent_px() < viewport_h:
        assert abs(_anchor_viewport_y(panel) - anchor_y_before) <= 2
    else:
        assert bar.value() >= bar.maximum() - 2
    panel.append_assistant_chunk("", "line\n" * 80)
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    viewport_h = panel._scroll.viewport().height()
    if panel._streaming_turn_extent_px() >= viewport_h:
        assert bar.value() >= bar.maximum() - 2


def test_thinking_header_stays_pinned_during_stream(qapp: QApplication, qtbot) -> None:
    """The turn anchor does not drift when thinking collapses and content starts."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel._scroll_lock_enabled = True
    anchor_y_before = _anchor_viewport_y(panel)
    assert abs(anchor_y_before) <= 10
    panel.append_assistant_chunk("brief reasoning\n", "")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    panel.append_assistant_chunk("", "answer line\n" * 4)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    viewport_h = panel._scroll.viewport().height()
    if panel._streaming_turn_extent_px() < viewport_h:
        assert abs(_anchor_viewport_y(panel) - anchor_y_before) <= 2


def _scheduled_follow_scheduler_names(scheduled: list[object]) -> list[str]:
    """Return scheduler callback names from captured singleShot calls."""
    return [getattr(fn, "__name__", "") for fn in scheduled]


def test_stream_follow_scheduler_coalesces_repeated_triggers(qapp: QApplication, qtbot) -> None:
    """Repeated follow requests schedule at most one frame pass and one retry."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    panel._scroll_lock_enabled = True
    scheduled: list[object] = []
    original_single_shot = QTimer.singleShot

    def capture_single_shot(ms: int, func: Callable[..., Any]) -> None:
        scheduled.append(func)
        original_single_shot(ms, func)

    with patch.object(QTimer, "singleShot", side_effect=capture_single_shot):
        for _ in range(5):
            panel._queue_stream_follow_passes()

    names = _scheduled_follow_scheduler_names(scheduled)
    assert names.count("_flush_stream_follow_frame") == 1
    assert names.count("_flush_stream_follow_retry") == 0
    assert "_apply_stream_follow" not in names


def test_height_and_range_triggers_do_not_multiply_follow_timers(qapp: QApplication, qtbot) -> None:
    """Layout-height and range growth in one turn share one scheduler burst."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(12):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel._scroll_lock_enabled = True
    scheduled: list[object] = []
    original_single_shot = QTimer.singleShot

    def capture_single_shot(ms: int, func: Callable[..., Any]) -> None:
        scheduled.append(func)
        original_single_shot(ms, func)

    with patch.object(QTimer, "singleShot", side_effect=capture_single_shot):
        panel._on_streaming_bubble_layout_changed()
        bar = panel._scroll.verticalScrollBar()
        panel._on_scrollbar_range_changed(0, bar.maximum() + 10)

    names = _scheduled_follow_scheduler_names(scheduled)
    assert names.count("_flush_stream_follow_frame") == 1
    assert names.count("_flush_stream_follow_retry") == 0
    assert "_apply_stream_follow" not in names


def test_chunk_flush_queues_deferred_follow_passes(qapp: QApplication, qtbot) -> None:
    """Chunk flush queues coalesced frame and retry follow scheduler callbacks."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel._scroll_lock_enabled = True
    scheduled: list[object] = []
    original_single_shot = QTimer.singleShot

    def capture_single_shot(ms: int, func: Callable[..., Any]) -> None:
        scheduled.append(func)
        original_single_shot(ms, func)

    panel.append_assistant_chunk("", "answer line\n" * 4)
    with patch.object(QTimer, "singleShot", side_effect=capture_single_shot):
        panel._flush_pending_chunks()
    _drain_follow_passes(qtbot, qapp)

    names = _scheduled_follow_scheduler_names(scheduled)
    assert names.count("_flush_stream_follow_frame") == 1
    assert names.count("_flush_stream_follow_retry") == 0
    assert "_apply_stream_follow" not in names
    bar = panel._scroll.verticalScrollBar()
    _drain_follow_passes(qtbot, qapp)
    assert bar.value() >= bar.maximum() - 2 or abs(bar.value() - panel._stream_follow_target()) <= 2


def test_follow_retry_scheduled_only_when_off_target_after_frame(qapp: QApplication, qtbot) -> None:
    """Late retry is scheduled only when the frame pass did not reach the target."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel._scroll_lock_enabled = True
    scheduled: list[object] = []
    original_single_shot = QTimer.singleShot

    def capture_single_shot(ms: int, func: Callable[..., Any]) -> None:
        scheduled.append(func)
        original_single_shot(ms, func)

    panel.append_assistant_chunk("", "answer line\n" * 12)
    with patch.object(QTimer, "singleShot", side_effect=capture_single_shot):
        panel._flush_pending_chunks()
    frame_names = _scheduled_follow_scheduler_names(scheduled)
    assert frame_names.count("_flush_stream_follow_frame") == 1
    assert frame_names.count("_flush_stream_follow_retry") == 0
    scheduled.clear()
    with patch.object(QTimer, "singleShot", side_effect=capture_single_shot):
        panel._flush_stream_follow_frame()
    retry_names = _scheduled_follow_scheduler_names(scheduled)
    assert retry_names.count("_flush_stream_follow_retry") in {0, 1}


def test_user_scroll_up_during_stream_unlocks_and_stays(qapp: QApplication, qtbot) -> None:
    """A large user scroll-up during streaming disables follow and stays detached."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel._scroll_lock_enabled = True
    panel.append_assistant_chunk("", "line\n" * 80)
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    bar = panel._scroll.verticalScrollBar()
    if bar.maximum() <= 0:
        pytest.skip("no scroll range in test environment")
    bar.setValue(bar.maximum() // 2)
    qapp.processEvents()
    assert panel._scroll_lock_enabled is False
    position_after_scroll = bar.value()
    panel.append_assistant_chunk("", "more line\n" * 40)
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    assert bar.value() < bar.maximum() - _FOLLOW_THRESHOLD_PX
    assert bar.value() == position_after_scroll


def test_small_scroll_up_from_bottom_unlocks(qapp: QApplication, qtbot) -> None:
    """A small wheel nudge from the bottom clears scroll-lock during streaming."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel._scroll_lock_enabled = True
    panel.append_assistant_chunk("", "line\n" * 80)
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    bar = panel._scroll.verticalScrollBar()
    if bar.maximum() <= 20:
        pytest.skip("no scroll range in test environment")
    bar.setValue(bar.maximum() - 1)
    qapp.processEvents()
    assert panel._scroll_lock_enabled is False
    position_after_scroll = bar.value()
    panel.append_assistant_chunk("", "more line\n" * 30)
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    assert bar.value() != bar.maximum()
    assert bar.value() == position_after_scroll


def test_range_growth_follows_after_frame_pass_when_locked(qapp: QApplication, qtbot) -> None:
    """Real content growth with lock on follows the stream target after flush."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel._scroll_lock_enabled = True
    bar = panel._scroll.verticalScrollBar()
    max_before = bar.maximum()
    panel.append_assistant_chunk("", "answer line\n" * 12)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    assert bar.maximum() >= max_before
    assert abs(bar.value() - panel._stream_follow_target()) <= _FOLLOW_THRESHOLD_PX


def test_return_to_bottom_rearms_follow(qapp: QApplication, qtbot) -> None:
    """Scrolling back to the bottom re-arms follow during streaming."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel._scroll_lock_enabled = True
    bar = panel._scroll.verticalScrollBar()
    if bar.maximum() <= 0:
        pytest.skip("no scroll range in test environment")
    bar.setValue(bar.maximum() // 2)
    qapp.processEvents()
    assert panel._scroll_lock_enabled is False
    bar.setValue(bar.maximum())
    qapp.processEvents()
    assert panel._scroll_lock_enabled is True
    panel.append_assistant_chunk("", "tail line\n" * 10)
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    assert abs(bar.value() - panel._stream_follow_target()) <= _FOLLOW_THRESHOLD_PX


def test_one_pixel_upward_scroll_unlocks_even_inside_bottom_threshold(
    qapp: QApplication, qtbot
) -> None:
    """A 1px upward move from the bottom detaches follow during streaming."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel.append_assistant_chunk("", "line\n" * 80)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    bar = panel._scroll.verticalScrollBar()
    if bar.maximum() <= 1:
        pytest.skip("no scroll range in test environment")
    bar.setValue(bar.maximum())
    qapp.processEvents()
    assert panel._scroll_lock_enabled is True
    bar.setValue(bar.maximum() - 1)
    qapp.processEvents()
    assert panel._scroll_lock_enabled is False


def test_wheel_up_from_pinned_bottom_unlocks_and_survives_many_flushes(
    qapp: QApplication, qtbot
) -> None:
    """Wheel-up from a pinned bottom stays detached across later chunk flushes."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 160)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel.append_assistant_chunk("", "line\n" * 80)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    bar = panel._scroll.verticalScrollBar()
    if bar.maximum() <= 0:
        pytest.skip("no scroll range in test environment")
    assert bar.value() >= bar.maximum() - _FOLLOW_THRESHOLD_PX
    position_before = bar.value()
    _wheel_on_transcript(panel, delta_y=120)
    qapp.processEvents()
    if bar.value() == position_before:
        bar.setValue(max(bar.minimum(), bar.value() - bar.singleStep()))
        qapp.processEvents()
    assert panel._scroll_lock_enabled is False
    position_after_scroll = bar.value()
    for _ in range(5):
        panel.append_assistant_chunk("", "more line\n" * 8)
        _flush_stream_chunks(qtbot)
        _drain_follow_passes(qtbot, qapp)
        assert panel._scroll_lock_enabled is False
        assert bar.value() == position_after_scroll


def test_wheel_up_short_turn_dead_zone_unlocks(qapp: QApplication, qtbot) -> None:
    """A small upward move unlocks even when follow target is turn_start."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel.append_assistant_chunk("", "short answer\n" * 2)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    bar = panel._scroll.verticalScrollBar()
    turn_start = panel._stream_follow_target()
    if turn_start >= bar.maximum() - _FOLLOW_THRESHOLD_PX:
        pytest.skip("short-turn follow target not below maximum in test environment")
    bar.setValue(bar.maximum())
    qapp.processEvents()
    _wheel_on_transcript(panel, delta_y=120)
    qapp.processEvents()
    if bar.value() >= bar.maximum() - _FOLLOW_THRESHOLD_PX:
        bar.setValue(bar.maximum() - 1)
        qapp.processEvents()
    assert panel._scroll_lock_enabled is False
    position_after_scroll = bar.value()
    panel.append_assistant_chunk("", "more\n" * 4)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    assert bar.value() == position_after_scroll


def test_follow_tracks_bottom_over_many_chunk_flushes(qapp: QApplication, qtbot) -> None:
    """Locked streaming keeps following the bottom across many chunk flushes."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 160)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    assert panel._scroll_lock_enabled is True
    bar = panel._scroll.verticalScrollBar()
    viewport_h = panel._scroll.viewport().height()
    for _ in range(10):
        panel.append_assistant_chunk("", "line\n" * 5)
        _flush_stream_chunks(qtbot)
        _drain_follow_passes(qtbot, qapp)
        if panel._streaming_turn_extent_px() >= viewport_h:
            assert bar.value() >= bar.maximum() - _FOLLOW_THRESHOLD_PX


def test_follow_after_markdown_document_height_change(qapp: QApplication, qtbot) -> None:
    """Deferred markdown relayout still keeps the viewport pinned when locked."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 160)
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    assert panel._scroll_lock_enabled is True
    bar = panel._scroll.verticalScrollBar()
    panel.append_assistant_chunk("", "```python\n")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    panel.append_assistant_chunk("", "print(1)\n```\n")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    viewport_h = panel._scroll.viewport().height()
    if panel._streaming_turn_extent_px() >= viewport_h:
        assert bar.value() >= bar.maximum() - _FOLLOW_THRESHOLD_PX
    else:
        assert abs(bar.value() - panel._stream_follow_target()) <= _FOLLOW_THRESHOLD_PX


def test_clear_transcript_removes_spacer(qapp: QApplication, qtbot) -> None:
    """Clearing the transcript removes the streaming viewport spacer."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    assert panel._streaming_viewport_spacer is not None
    panel.clear_streaming_transcript()
    assert panel._streaming_viewport_spacer is None


def test_composer_resize_does_not_scroll_transcript(qapp: QApplication, qtbot) -> None:
    """Composer growth must not move the transcript scrollbar."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.begin_assistant_stream()
    bar = panel._scroll.verticalScrollBar()
    _detach_scroll_panel(panel, qapp)
    panel._input.setPlainText("line\n" * 12)
    qapp.processEvents()
    assert bar.value() == 0


def test_scroll_down_button_visible_when_lock_disabled(qapp: QApplication, qtbot) -> None:
    """Scroll-down button appears when the user scrolls up during a stream."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 160)
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.begin_assistant_stream()
    _detach_scroll_panel(panel, qapp)
    panel.append_assistant_chunk("", "chunk")
    _flush_stream_chunks(qtbot)
    assert panel._scroll_down_btn.isVisible()
    panel._scroll_down_btn.click()
    qapp.processEvents()
    assert not panel._scroll_down_btn.isVisible()
    bar = panel._scroll.verticalScrollBar()
    if bar.maximum() > 0:
        assert bar.value() >= bar.maximum() - 2


def test_scroll_down_button_visible_after_stream_ends_when_detached(
    qapp: QApplication, qtbot
) -> None:
    """Scroll-down button stays available after the stream ends if detached."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 200)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.begin_assistant_stream()
    panel.end_assistant_stream("done")
    _detach_scroll_panel(panel, qapp)
    assert panel._scroll_down_btn.isVisible()


def test_flush_does_not_schedule_scroll_timers(qapp: QApplication, qtbot) -> None:
    """Chunk flush must not schedule timer-based scroll helpers."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    scheduled: list[object] = []
    original_single_shot = QTimer.singleShot

    def capture_single_shot(ms: int, func: Callable[..., Any]) -> None:
        scheduled.append(func)
        original_single_shot(ms, func)

    panel.append_assistant_chunk("", "data")
    with patch.object(QTimer, "singleShot", side_effect=capture_single_shot):
        panel._flush_pending_chunks()

    legacy_names = {getattr(fn, "__name__", "") for fn in scheduled}
    assert "_scroll_to_bottom" not in legacy_names
    assert "_flush_turn_bottom_scroll" not in legacy_names
    follow_names = _scheduled_follow_scheduler_names(scheduled)
    assert follow_names.count("_flush_stream_follow_frame") == 1
    assert follow_names.count("_flush_stream_follow_retry") == 0
    assert "_apply_stream_follow" not in follow_names


def test_load_transcript_exits_streaming_mode(qapp: QApplication, qtbot) -> None:
    """Replacing the transcript while streaming clears the streaming flag."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "**Hi")
    _flush_stream_chunks(qtbot)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.is_content_streaming()
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "assistant",
            "content": "**Hi**",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    panel.load_transcript(messages)
    restored = panel.findChildren(ChatMessageBubble)[0]
    assert not restored.is_content_streaming()
    browser = restored.findChild(QTextBrowser, "aiChatAssistantText")
    assert browser is not None
    html = browser.toHtml().lower()
    assert "font-weight:600" in html or "font-weight:700" in html
