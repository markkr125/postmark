"""Tests for chat panel streaming coalescing, scroll, and activity helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QTextTable, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QWidget,
)

from services.ai.chat.session_service import AiChatMessageDict
from tests.ui.sidebar.ai.conftest import load_transcript_sync
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.chat_panel.scroll import (
    _FOLLOW_THRESHOLD_PX,
    _STICKY_PROMPT_LEFT_SHIFT_PX,
    _STICKY_PROMPT_VIEWPORT_INSET_PX,
)
from ui.sidebar.ai.chat_panel_streaming import format_activity_status
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent


def _flush_stream_chunks(qtbot) -> None:
    """Wait for the coalesced chunk delivery timer (~50ms)."""
    qtbot.wait(60)
    QApplication.processEvents()


def _drain_follow_passes(qtbot, qapp: QApplication) -> None:
    """Wait for deferred stream-follow passes (0ms and 16ms)."""
    qtbot.wait(20)
    qapp.processEvents()


def _drain_smooth_scroll(
    panel: AiChatPanel,
    qapp: QApplication,
    qtbot,
    *,
    timeout_ms: int = 2000,
) -> None:
    """Wait until smooth-scroll animation on *panel* has settled."""
    if not hasattr(panel, "_smooth_scroller"):
        return
    elapsed = 0
    while panel._smooth_scroller.is_animating() and elapsed < timeout_ms:
        qtbot.wait(20)
        qapp.processEvents()
        elapsed += 20


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


def _wheel_on_widget(
    widget: QWidget,
    *,
    delta_y: int,
    pos: QPoint | None = None,
) -> None:
    """Send a wheel event to *widget* (for inner transcript text targets)."""
    local = pos or QPoint(max(1, widget.width() // 2), max(1, widget.height() // 2))
    global_pos = widget.mapToGlobal(QPointF(local))
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
    QApplication.sendEvent(widget, event)


def _sticky_label_column_bottom(sticky: QWidget) -> int:
    """Return the bottom edge of the visible sticky prompt column."""
    scroll = sticky.findChild(QScrollArea, "aiChatStickyScroll")
    host = sticky.findChild(QWidget, "aiChatStickyLabelHost")
    if scroll is not None and scroll.isVisible():
        return scroll.y() + scroll.height()
    assert host is not None
    return host.y() + host.height()


def _wait_for_bubble_in_viewport(
    panel: AiChatPanel,
    bubble: ChatMessageBubble,
    qtbot,
    *,
    timeout_ms: int = 3000,
) -> None:
    """Wait until *bubble* has non-zero height and overlaps the transcript viewport."""

    def _ready() -> bool:
        return bubble.height() > 0 and panel._bubble_intersects_viewport(bubble)

    qtbot.waitUntil(_ready, timeout=timeout_ms)


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
    return int(anchor.mapTo(panel._messages, QPoint(0, 0)).y() - bar.value())


def _viewport_top(panel: AiChatPanel, widget: QWidget) -> int:
    """Return *widget* top edge Y in viewport coordinates (scroll-aware)."""
    bar = panel._scroll.verticalScrollBar()
    return int(widget.mapTo(panel._messages, QPoint(0, 0)).y() - bar.value())


def _gap_user_bottom_to_assistant_top(
    panel: AiChatPanel,
    user: ChatMessageBubble,
    assistant: ChatMessageBubble,
) -> int:
    """Return viewport gap between *user* bottom and *assistant* row top."""
    user_bottom = _viewport_top(panel, user) + user.height()
    assistant_top = _viewport_top(panel, assistant)
    return assistant_top - user_bottom


def _gap_user_bottom_to_assistant_markdown(
    panel: AiChatPanel,
    user: ChatMessageBubble,
    assistant: ChatMessageBubble,
) -> int | None:
    """Return viewport gap between *user* bottom and visible assistant markdown."""
    body = assistant._markdown_body
    if body is None or not body.isVisible():
        return None
    user_bottom = _viewport_top(panel, user) + user.height()
    markdown_top = _viewport_top(panel, body)
    return markdown_top - user_bottom


def _large_slack_items_between(
    panel: AiChatPanel,
    before: QWidget,
    after: QWidget,
    *,
    min_slack_px: int = 48,
) -> list[str]:
    """Return layout items between two widgets that consume large vertical slack."""
    before_index = panel._messages_layout.indexOf(before)
    after_index = panel._messages_layout.indexOf(after)
    assert before_index >= 0
    assert after_index >= 0
    if before_index > after_index:
        before_index, after_index = after_index, before_index
    offenders: list[str] = []
    for index in range(before_index + 1, after_index):
        item = panel._messages_layout.itemAt(index)
        if item is None:
            continue
        spacer = item.spacerItem()
        if spacer is not None and item.geometry().height() >= min_slack_px:
            offenders.append(f"spacer[{index}]={item.geometry().height()}")
            continue
        widget = item.widget()
        if widget is None:
            continue
        slack = widget.height() - max(0, widget.sizeHint().height())
        if slack >= min_slack_px:
            name = widget.objectName() or type(widget).__name__
            offenders.append(f"{name}[{index}]={slack}")
    return offenders


def _scrollbar_maximum_px(panel: AiChatPanel) -> int:
    """Return the transcript vertical scrollbar maximum."""
    return int(panel._scroll.verticalScrollBar().maximum())


def _horizontal_scroll_maximum_px(panel: AiChatPanel) -> int:
    """Return the transcript horizontal scrollbar maximum (0 when not clipped)."""
    return int(panel._scroll.horizontalScrollBar().maximum())


def _assert_no_horizontal_scroll(panel: AiChatPanel) -> None:
    """Assert transcript content fits the viewport width."""
    viewport_w = panel._scroll.viewport().width()
    assert viewport_w > 0
    assert _horizontal_scroll_maximum_px(panel) == 0
    assert panel._messages.minimumWidth() <= viewport_w


def _stop_chunk_coalesce(panel: AiChatPanel) -> None:
    """Stop the pending chunk coalesce timer so a manual flush is deterministic."""
    if panel._chunk_coalesce_timer.isActive():
        panel._chunk_coalesce_timer.stop()


def _expected_spacer_height(panel: AiChatPanel) -> int:
    """Return dynamic spacer height for the active or just-completed turn."""
    viewport_h = panel._scroll.viewport().height()
    if viewport_h <= 0:
        return 0
    assistant = panel._streaming_bubble or panel._last_assistant_bubble()
    if assistant is None or panel._turn_scroll_anchor is None:
        return 0
    return int(panel._target_streaming_spacer_height(assistant))


def _turn_bottom_in_messages(panel: AiChatPanel, assistant: ChatMessageBubble | None = None) -> int:
    """Return assistant-row bottom Y in ``_messages`` coordinates."""
    bubble = assistant or panel._streaming_bubble or panel._last_assistant_bubble()
    assert bubble is not None
    bottom = panel._turn_bottom_y_in_messages(bubble)
    assert bottom is not None
    return int(bottom)


def _sticky_turn_prompt(panel: AiChatPanel):
    """Return the sticky turn prompt overlay on the transcript viewport, if any."""
    from ui.sidebar.ai.message_bubble.user_message.overlay import StickyUserPromptOverlay

    viewport = panel._scroll.viewport()
    for child in viewport.children():
        if isinstance(child, StickyUserPromptOverlay):
            return child
    return None


def _scroll_until_anchor_above_viewport(
    panel: AiChatPanel,
    qapp: QApplication,
    *,
    margin: int = 5,
) -> None:
    """Scroll until the turn anchor is above the viewport and sticky is eligible."""
    panel._detach_stream_follow_for_user_scroll()
    anchor = panel._turn_scroll_anchor or panel._find_last_turn_user_bubble()
    assert anchor is not None
    bar = panel._scroll.verticalScrollBar()
    cap = panel._sticky_prompt_height_cap()
    if bar.value() >= bar.maximum() - 1:
        while bar.value() > bar.minimum():
            if (
                panel._widget_top_in_viewport(anchor) < -margin
                and panel._sticky_turn_for_viewport(cap) is not None
            ):
                break
            bar.setValue(max(bar.minimum(), bar.value() - 48))
            qapp.processEvents()
    while panel._widget_top_in_viewport(anchor) >= -margin and bar.value() < bar.maximum():
        assistant = panel._assistant_bubble_for_turn(anchor)
        if (
            assistant is not None
            and panel._widget_bottom_in_viewport(assistant) <= cap + 4
            and panel._widget_top_in_viewport(anchor) < -margin
        ):
            break
        bar.setValue(min(bar.maximum(), bar.value() + 24))
        qapp.processEvents()
    panel._sync_sticky_turn_prompt()


def _assistant_for_sticky_turn(panel: AiChatPanel) -> ChatMessageBubble:
    """Return the assistant bubble paired with the sticky viewport turn."""
    anchor = panel._sticky_turn_anchor
    assert anchor is not None
    assistant = panel._assistant_bubble_for_turn(anchor)
    assert assistant is not None
    return assistant


def _user_bubble_with_text(panel: AiChatPanel, text: str) -> ChatMessageBubble:
    """Return the first user bubble whose text matches *text*."""
    for index in range(panel._messages_layout.count()):
        item = panel._messages_layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if (
            isinstance(widget, ChatMessageBubble)
            and widget.role == "user"
            and widget.text() == text
        ):
            return widget
    pytest.fail(f"user bubble with text {text!r} not found")


_SCREENSHOT_USER_PROMPT = (
    "how do i create scripts in this app? can you give an example for a pre request script? "
    "give one small example"
)
_USER_BUBBLE_HEIGHT_TOLERANCE_PX = 48


def _user_message_label_width(bubble: ChatMessageBubble) -> int:
    """Return inner label column width for *bubble*."""
    frame = bubble._user_frame
    if frame is None or bubble._user_section is None:
        return max(1, bubble.width())
    margins = frame.contentsMargins()
    return max(1, frame.width() - margins.left() - margins.right())


def _user_message_natural_label_height(bubble: ChatMessageBubble) -> int:
    """Return uncapped wrapped label height at the bubble's current width."""
    section = bubble._user_section
    assert section is not None
    return section.natural_label_height_for_width(_user_message_label_width(bubble))


def _assert_user_bubble_height_matches_content(
    bubble: ChatMessageBubble,
    *,
    tolerance_px: int = _USER_BUBBLE_HEIGHT_TOLERANCE_PX,
) -> None:
    """Guard: user bubble must not absorb transcript vertical slack."""
    section = bubble._user_section
    assert section is not None
    label = section.label_widget()
    natural_label_h = _user_message_natural_label_height(bubble)
    assert label.height() <= natural_label_h + 16, (
        f"label height {label.height()}px exceeds natural {natural_label_h}px"
    )
    expected_row_h = bubble.sizeHint().height()
    assert bubble.height() <= expected_row_h + tolerance_px, (
        f"bubble height {bubble.height()}px exceeds sizeHint {expected_row_h}px "
        f"by more than {tolerance_px}px"
    )


def test_user_message_height_matches_content_during_stream(qapp: QApplication, qtbot) -> None:
    """First-turn user bubble stays compact through stream start, thinking, content, and end."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(420, 640)
    _ensure_transcript_scroll_range(panel, qapp)

    user = panel.add_message("user", _SCREENSHOT_USER_PROMPT)
    qapp.processEvents()
    _assert_user_bubble_height_matches_content(user)

    panel.begin_assistant_stream()
    qapp.processEvents()
    _assert_user_bubble_height_matches_content(user)

    panel.append_assistant_chunk("thinking about scripts\n" * 4, "")
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    _assert_user_bubble_height_matches_content(user)

    panel.append_assistant_chunk("", "Here is a small pre-request example...\n")
    _flush_stream_chunks(qtbot)
    qapp.processEvents()
    _assert_user_bubble_height_matches_content(user)

    panel.end_assistant_stream("Here is a small pre-request example...\n")
    qapp.processEvents()
    _assert_user_bubble_height_matches_content(user)


def _document_table_count(body: MarkdownContent) -> int:
    """Return the number of top-level QTextTable frames in *body*."""
    return sum(
        1 for frame in body.document().rootFrame().childFrames() if isinstance(frame, QTextTable)
    )


def _scroll_until_user_above_viewport(
    panel: AiChatPanel,
    user: ChatMessageBubble,
    qapp: QApplication,
    *,
    margin: int = 5,
) -> None:
    """Scroll down until *user* sits above the viewport top."""
    panel._detach_stream_follow_for_user_scroll()
    bar = panel._scroll.verticalScrollBar()
    while panel._widget_top_in_viewport(user) >= -margin and bar.value() < bar.maximum():
        bar.setValue(min(bar.maximum(), bar.value() + 24))
        qapp.processEvents()
    panel._sync_sticky_turn_prompt()


_SECOND_TURN_ANCHOR_TOLERANCE_PX = 128


def _assert_scrolled_to_turn_start(panel: AiChatPanel, *, tolerance: int = 2) -> None:
    """Assert the transcript is scrolled as far up as the turn anchor allows."""
    bar = panel._scroll.verticalScrollBar()
    target = panel._scroll_value_for_turn_start()
    assert bar.value() >= target - tolerance


def _scroll_until_sticky_shows_text(panel: AiChatPanel, qapp: QApplication, text: str) -> None:
    """Scroll until the sticky overlay shows *text*."""
    _scroll_until_anchor_above_viewport(panel, qapp)
    panel._sync_sticky_turn_prompt()
    sticky = _sticky_turn_prompt(panel)
    if sticky is not None and sticky.isVisible() and sticky.text() == text:
        return
    bar = panel._scroll.verticalScrollBar()
    start = bar.value()
    candidates: list[int] = [start]
    for step in range(1, 320):
        candidates.append(min(bar.maximum(), start + step * 20))
    for step in range(1, 320):
        candidates.append(max(bar.minimum(), start - step * 20))
    for value in candidates:
        bar.setValue(value)
        qapp.processEvents()
        panel._sync_sticky_turn_prompt()
        sticky = _sticky_turn_prompt(panel)
        if sticky is not None and sticky.isVisible() and sticky.text() == text:
            return
    pytest.fail(f"sticky never showed text {text!r}")


def _scroll_until_no_sticky_turn(panel: AiChatPanel, qapp: QApplication) -> None:
    """Scroll until no viewport turn is eligible for sticky."""
    bar = panel._scroll.verticalScrollBar()
    for _ in range(320):
        panel._sync_sticky_turn_prompt()
        cap = panel._sticky_prompt_height_cap()
        if panel._sticky_turn_for_viewport(cap) is None:
            sticky = _sticky_turn_prompt(panel)
            assert sticky is None or not sticky.isVisible()
            return
        if bar.value() >= bar.maximum():
            break
        bar.setValue(min(bar.maximum(), bar.value() + 24))
        qapp.processEvents()
    panel._sync_sticky_turn_prompt()
    pytest.fail("could not scroll past all sticky-eligible turns")


def _fill_transcript_and_start_stream(
    panel: AiChatPanel,
    qapp: QApplication,
    qtbot,
    *,
    user_text: str = "question",
    assistant_lines: int = 40,
) -> None:
    """Populate a long transcript and stream a multi-line assistant answer."""
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message("user", user_text)
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel.append_assistant_chunk("", "answer line\n" * assistant_lines)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    qapp.processEvents()


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


def test_streaming_markdown_table_finalizes_to_qt_table(
    qapp: QApplication,
    qtbot,
) -> None:
    """Incomplete streamed pipe tables render incrementally and finalize to rich tables."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.resize(360, 480)
    qtbot.waitExposed(panel)

    panel.add_message("user", "compare insomnia and postman")
    panel.begin_assistant_stream()
    chunks = [
        "## 1. Core Strengths\n\n",
        "| Feature | Insomnia | Postman |\n",
        "|---------|----------|---------|\n",
        "| UI & UX | Minimalist, tab-based, dark-theme-friendly. |",
        " Feature-heavy dashboard UI. |\n",
        "| Request building | One-window form. | Menu-driven panels. |\n",
    ]
    for chunk in chunks[:4]:
        panel.append_assistant_chunk("", chunk)
        _flush_stream_chunks(qtbot)

    assistant_bubbles = [
        bubble for bubble in panel.findChildren(ChatMessageBubble) if bubble.role == "assistant"
    ]
    assert len(assistant_bubbles) == 1
    body = assistant_bubbles[0].findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    assert body.is_streaming()
    assert _document_table_count(body) >= 1
    assert "Minimalist, tab-based" in body.document().toPlainText()

    for chunk in chunks[4:]:
        panel.append_assistant_chunk("", chunk)
        _flush_stream_chunks(qtbot)
    panel.end_assistant_stream("".join(chunks))

    assert not body.is_streaming()
    assert _document_table_count(body) >= 1
    assert "Request building" in body.document().toPlainText()


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


def test_transcript_no_horizontal_scroll_during_stream(qapp: QApplication, qtbot) -> None:
    """First-turn streaming must not introduce a horizontal transcript scrollbar."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 480)
    user_text = (
        "how do i create scripts in this app? can you give an example "
        "for a pre request script? give one small example"
    )
    panel.add_message("user", user_text)
    _assert_no_horizontal_scroll(panel)

    panel.begin_assistant_stream()
    qapp.processEvents()
    _assert_no_horizontal_scroll(panel)

    panel.append_assistant_chunk("thinking line\n" * 8, "")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    _assert_no_horizontal_scroll(panel)

    code = "```python\npm.response.json().get('id')\npm.environment.set('auth_token', token)\n```\n"
    panel.append_assistant_chunk("", "Sure:\n\n" + code)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    _assert_no_horizontal_scroll(panel)

    panel.end_assistant_stream("Sure.\n\n" + code)
    qapp.processEvents()
    _assert_no_horizontal_scroll(panel)


def test_scroll_down_hidden_during_locked_first_turn_stream(qapp: QApplication, qtbot) -> None:
    """Scroll-down stays hidden while scroll-lock follows the first turn."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 480)
    panel.add_message("user", "how do i create scripts? give one small example")
    panel.begin_assistant_stream()
    qapp.processEvents()
    assert panel._scroll_lock_enabled

    def assert_hidden() -> None:
        panel._update_scroll_down_button_visibility()
        assert not panel._scroll_down_btn.isVisible()

    assert_hidden()

    panel.append_assistant_chunk("thinking line\n" * 6, "")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    assert panel._scroll_lock_enabled
    assert_hidden()

    panel.append_assistant_chunk(
        "",
        "Here is a short answer with a fence:\n\n```python\nprint('ok')\n```\n",
    )
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    assert panel._scroll_lock_enabled
    assert_hidden()


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
    """Turn-boundary scroll runs once per send turn."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    panel.add_message("user", "hello")
    panel.begin_assistant_stream()
    assert panel._turn_scroll_pending is False
    assert abs(_anchor_viewport_y(panel)) <= 10


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
    viewport_h = panel._scroll.viewport().height()
    if viewport_h > 0:
        expected = _expected_spacer_height(panel)
        if expected > 2:
            assert spacer is not None
            assert abs(spacer.height() - expected) <= 4
        if panel._streaming_turn_extent_px() < viewport_h and spacer is not None:
            panel._messages_layout.activate()
            assert panel._messages.minimumSizeHint().height() <= viewport_h + 4


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
    panel.resize(360, 200)
    qapp.processEvents()
    viewport_h = panel._scroll.viewport().height()
    if viewport_h > 0:
        expected = _expected_spacer_height(panel)
        if expected > 2 and spacer is not None:
            assert abs(spacer.height() - expected) <= 4


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
    viewport_h = panel._scroll.viewport().height()
    if viewport_h > 0:
        assert panel._streaming_turn_extent_px() >= viewport_h - 2
        assert spacer is None or spacer.height() <= 2


def test_short_first_turn_stays_anchored_after_stream_ends(qapp: QApplication, qtbot) -> None:
    """The first short reply stays near the top after finalization, not mid-viewport."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    panel.add_message("user", "hello")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    anchor_y_before = _anchor_viewport_y(panel)
    panel.append_assistant_chunk("", "Sure.")
    _flush_stream_chunks(qtbot)
    panel.end_assistant_stream("Sure.")
    qapp.processEvents()
    qapp.processEvents()
    qtbot.wait(20)
    qapp.processEvents()
    viewport_h = panel._scroll.viewport().height()
    assistant = panel._last_assistant_bubble()
    assert assistant is not None
    extent = panel._streaming_turn_extent_px(assistant)
    if viewport_h > 0 and extent < viewport_h:
        if panel._streaming_viewport_spacer is not None:
            assert abs(_anchor_viewport_y(panel) - anchor_y_before) <= 10
        else:
            assert abs(_anchor_viewport_y(panel) - anchor_y_before) <= 10


def test_retained_spacer_cleared_before_next_user_message(qapp: QApplication, qtbot) -> None:
    """A preserved short-turn spacer is removed before the next user message is appended."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    panel.add_message("user", "hello")
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "Sure.")
    _flush_stream_chunks(qtbot)
    panel.end_assistant_stream("Sure.")
    qapp.processEvents()
    panel.add_message("user", "follow up")
    assert panel._streaming_viewport_spacer is None


def test_completed_turn_spacer_reconciles_after_footer_layout(qapp: QApplication, qtbot) -> None:
    """Late assistant footer/layout growth resizes or clears the completed-turn spacer."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    panel.add_message("user", "hello")
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "Sure.")
    _flush_stream_chunks(qtbot)
    panel.end_assistant_stream("Sure.")
    qapp.processEvents()
    assistant = panel._last_assistant_bubble()
    assert assistant is not None
    spacer_before = (
        panel._streaming_viewport_spacer.height() if panel._streaming_viewport_spacer else 0
    )
    assistant.set_usage_metadata(
        model_id="gpt-test",
        model_label="gpt-test",
        prompt_tokens=100,
        completion_tokens=20,
    )
    qapp.processEvents()
    qapp.processEvents()
    viewport_h = panel._scroll.viewport().height()
    extent = panel._streaming_turn_extent_px(assistant)
    if viewport_h > 0 and extent < viewport_h:
        expected = _expected_spacer_height(panel)
        if expected > 2:
            assert panel._streaming_viewport_spacer is not None
            assert abs(panel._streaming_viewport_spacer.height() - expected) <= 4
    else:
        assert panel._streaming_viewport_spacer is None
    if panel._streaming_viewport_spacer is not None:
        assert panel._streaming_viewport_spacer.height() <= spacer_before + 2


def test_long_answer_clears_spacer_after_stream_ends(qapp: QApplication, qtbot) -> None:
    """Long completed turns do not retain the streaming viewport spacer."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 160)
    for index in range(20):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "line\n" * 80)
    _flush_stream_chunks(qtbot)
    panel.end_assistant_stream("line\n" * 80)
    qapp.processEvents()
    viewport_h = panel._scroll.viewport().height()
    assistant = panel._last_assistant_bubble()
    assert assistant is not None
    extent = panel._streaming_turn_extent_px(assistant)
    if viewport_h > 0 and extent >= viewport_h:
        assert panel._streaming_viewport_spacer is None


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
    user_top = _viewport_top(panel, user_bubble)
    user_bottom = user_top + user_bubble.height()
    activity_top = _viewport_top(panel, activity)
    assert user_top >= 0
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
    panel._scroll_lock_enabled = True
    assert not panel._stream_content_started
    anchor_y_before = _anchor_viewport_y(panel)
    panel.append_assistant_chunk("thinking line\n", "")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    viewport_h = panel._scroll.viewport().height()
    if panel._streaming_turn_extent_px() < viewport_h:
        assert abs(_anchor_viewport_y(panel) - anchor_y_before) <= 4


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


def test_first_turn_stream_follows_bottom_after_overflow(qapp: QApplication, qtbot) -> None:
    """A first short stream switches to bottom-follow once the answer exceeds the viewport."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 160)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel._scroll_lock_enabled = True
    panel.append_assistant_chunk("", "short answer\n")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    viewport_h = panel._scroll.viewport().height()
    if viewport_h > 0 and panel._streaming_turn_extent_px() < viewport_h:
        assert panel._streaming_viewport_spacer is not None
        assert _anchor_viewport_y(panel) <= 10

    panel.append_assistant_chunk("", "line\n" * 80)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    assistant = panel._streaming_bubble
    assert assistant is not None
    viewport_h = panel._scroll.viewport().height()
    if viewport_h > 0 and panel._streaming_turn_extent_px() >= viewport_h:
        spacer = panel._streaming_viewport_spacer
        assert spacer is None or spacer.height() <= 2
        bar = panel._scroll.verticalScrollBar()
        assert bar.value() >= bar.maximum() - 2
        assert panel._widget_bottom_in_viewport(assistant) <= viewport_h + 4


def test_second_turn_code_stream_keeps_anchor_stable(qapp: QApplication, qtbot) -> None:
    """Starting a second stream after a retained short-turn spacer does not jump."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    panel.add_message("user", "first question")
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "Short answer.")
    _flush_stream_chunks(qtbot)
    panel.end_assistant_stream("Short answer.")
    qapp.processEvents()

    panel.add_message("user", "Can you give code?")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    anchor_y_before = _anchor_viewport_y(panel)
    _assert_scrolled_to_turn_start(panel)
    chunks = [
        "Sure:\n\n",
        "```python\n",
        "pm.response.json().get('id')\n",
        "pm.environment.set('auth_token', token)\n",
        "```\n",
    ]
    for chunk in chunks:
        panel.append_assistant_chunk("", chunk)
        _flush_stream_chunks(qtbot)
        _drain_follow_passes(qtbot, qapp)
        viewport_h = panel._scroll.viewport().height()
        if panel._streaming_turn_extent_px() < viewport_h:
            assert (
                abs(_anchor_viewport_y(panel) - anchor_y_before) <= _SECOND_TURN_ANCHOR_TOLERANCE_PX
            )
        else:
            bar = panel._scroll.verticalScrollBar()
            assert bar.value() >= bar.maximum() - 2


def test_second_turn_small_chunks_do_not_step_anchor(qapp: QApplication, qtbot) -> None:
    """Small stream chunks keep the user prompt pinned instead of stepping by spacer deltas."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 360)
    panel.add_message("user", "first question")
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "Short answer.")
    _flush_stream_chunks(qtbot)
    panel.end_assistant_stream("Short answer.")
    qapp.processEvents()
    panel.add_message("user", "second question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    anchor_y_before = _anchor_viewport_y(panel)
    _assert_scrolled_to_turn_start(panel)

    for index in range(12):
        thinking = "t" if index % 2 == 0 else ""
        content = "x" if index % 2 else ""
        panel.append_assistant_chunk(thinking, content)
        _flush_stream_chunks(qtbot)
        _drain_follow_passes(qtbot, qapp)
        viewport_h = panel._scroll.viewport().height()
        if panel._streaming_turn_extent_px() < viewport_h:
            assert (
                abs(_anchor_viewport_y(panel) - anchor_y_before) <= _SECOND_TURN_ANCHOR_TOLERANCE_PX
            )


def test_second_turn_thought_to_answer_transition_keeps_anchor_stable(
    qapp: QApplication, qtbot
) -> None:
    """Collapsing the Thought body when answer text starts does not move the prompt."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 360)
    panel.add_message("user", "first question")
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "Short answer.")
    _flush_stream_chunks(qtbot)
    panel.end_assistant_stream("Short answer.")
    qapp.processEvents()
    panel.add_message("user", "second question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    anchor_y_before = _anchor_viewport_y(panel)
    _assert_scrolled_to_turn_start(panel)

    panel.append_assistant_chunk("thinking line\n" * 8, "")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    if panel._streaming_turn_extent_px() < panel._scroll.viewport().height():
        assert abs(_anchor_viewport_y(panel) - anchor_y_before) <= _SECOND_TURN_ANCHOR_TOLERANCE_PX

    panel.append_assistant_chunk("", "Here is the answer.\n")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    if panel._streaming_turn_extent_px() < panel._scroll.viewport().height():
        assert abs(_anchor_viewport_y(panel) - anchor_y_before) <= _SECOND_TURN_ANCHOR_TOLERANCE_PX


def _stream_chunk_and_settle(
    panel: AiChatPanel,
    qtbot,
    qapp: QApplication,
    *,
    thinking: str = "",
    content: str = "",
) -> None:
    """Append one coalesced stream chunk and wait for follow passes."""
    panel.append_assistant_chunk(thinking, content)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    qapp.processEvents()


def _measure_stream_anchor_movement(
    panel: AiChatPanel,
    qtbot,
    qapp: QApplication,
    *,
    thinking_chunks: int,
    content_chunks: int,
    chunk_content: str = "answer line with some text\n",
) -> list[tuple[int, int]]:
    """Return ``(anchor_viewport_y, turn_extent_px)`` after each streamed chunk."""
    samples: list[tuple[int, int]] = []
    for _ in range(thinking_chunks):
        _stream_chunk_and_settle(panel, qtbot, qapp, thinking="thinking line\n")
        samples.append((_anchor_viewport_y(panel), panel._streaming_turn_extent_px()))
    for _ in range(content_chunks):
        _stream_chunk_and_settle(panel, qtbot, qapp, content=chunk_content)
        samples.append((_anchor_viewport_y(panel), panel._streaming_turn_extent_px()))
    return samples


def _assert_no_anchor_oscillation(
    positions: list[int],
    *,
    threshold_px: int = 4,
) -> None:
    """Fail when the turn anchor bounces up then down (or vice versa)."""
    for index in range(len(positions) - 2):
        first_delta = positions[index + 1] - positions[index]
        second_delta = positions[index + 2] - positions[index + 1]
        if (
            first_delta * second_delta < 0
            and abs(first_delta) > threshold_px
            and abs(second_delta) > threshold_px
        ):
            pytest.fail(
                "anchor oscillated at "
                f"steps {index}->{index + 2}: {first_delta:+d}px then {second_delta:+d}px"
            )


def _assert_anchor_movement_bounded(
    positions: list[int],
    *,
    baseline: int,
    max_step_delta_px: int = 4,
    max_baseline_delta_px: int = 10,
) -> None:
    """Fail when the turn anchor oscillates or drifts during streaming."""
    assert positions, "expected at least one anchor measurement"
    for index, anchor_y in enumerate(positions):
        assert anchor_y >= -2, f"step {index}: anchor scrolled above viewport ({anchor_y})"
        assert abs(anchor_y - baseline) <= max_baseline_delta_px, (
            f"step {index}: anchor_y={anchor_y} drifted from baseline {baseline}"
        )
    for index, delta in enumerate(
        positions[index + 1] - positions[index] for index in range(len(positions) - 1)
    ):
        assert abs(delta) <= max_step_delta_px, (
            f"step {index}->{index + 1}: anchor jumped by {delta}px"
        )


def test_second_turn_event_samples_keep_anchor_pinned(qapp: QApplication, qtbot) -> None:
    """Second-turn stream transactions do not expose intermediate anchor jumps."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 360)
    panel.add_message("user", "first question")
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "Short answer.\n" * 10)
    _flush_stream_chunks(qtbot)
    panel.end_assistant_stream("Short answer.\n" * 10)
    qapp.processEvents()
    qapp.processEvents()

    samples: list[tuple[str, int, int]] = []

    def sample(label: str) -> None:
        anchor = panel._turn_scroll_anchor
        if anchor is None:
            return
        samples.append((label, _anchor_viewport_y(panel), panel._streaming_turn_extent_px()))

    bar = panel._scroll.verticalScrollBar()
    bar.rangeChanged.connect(lambda _min, _max: sample(f"range:{_max}"))
    bar.valueChanged.connect(lambda value: sample(f"value:{value}"))

    panel.add_message("user", "second question can you give code?")
    sample("after-user")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    sample("after-begin")
    if panel._streaming_bubble is not None:
        panel._streaming_bubble.layout_height_changed.connect(lambda: sample("assistant-layout"))

    for index in range(6):
        panel.append_assistant_chunk(
            "thinking line\n" if index < 3 else "",
            "content line\n" if index >= 2 else "",
        )
        _flush_stream_chunks(qtbot)
        _drain_follow_passes(qtbot, qapp)
        sample(f"after-chunk-{index}")

    viewport_h = panel._scroll.viewport().height()
    in_viewport = [
        anchor_y for _label, anchor_y, extent in samples if extent == 0 or extent < viewport_h
    ]
    assert in_viewport, "expected event samples while the turn fits"
    _assert_anchor_movement_bounded(in_viewport, baseline=in_viewport[0])
    _assert_no_anchor_oscillation(in_viewport)
    _assert_no_horizontal_scroll(panel)
    assert not panel._scroll_down_btn.isVisible()


def test_first_turn_stream_user_anchor_movement_bounded(qapp: QApplication, qtbot) -> None:
    """First-turn streaming must not bounce the user prompt up and down."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 480)
    user_text = (
        "how do i create scripts in this app? can you give an example "
        "for a pre request script? give one small example"
    )
    panel.add_message("user", user_text)
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    baseline = _anchor_viewport_y(panel)
    _assert_scrolled_to_turn_start(panel)

    samples = _measure_stream_anchor_movement(
        panel,
        qtbot,
        qapp,
        thinking_chunks=8,
        content_chunks=24,
    )
    viewport_h = panel._scroll.viewport().height()
    in_viewport = [anchor_y for anchor_y, extent in samples if extent < viewport_h]
    assert in_viewport, "expected in-viewport streaming samples"
    _assert_anchor_movement_bounded(in_viewport, baseline=baseline)
    _assert_no_anchor_oscillation([anchor_y for anchor_y, _extent in samples])


def test_first_turn_no_scrollbar_when_content_fits(qapp: QApplication, qtbot) -> None:
    """A completed short first turn should not leave a transcript scrollbar."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 480)
    user_text = (
        "how do i create scripts in this app? can you give an example "
        "for a pre request script? give one small example"
    )
    panel.add_message("user", user_text)
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    assert _scrollbar_maximum_px(panel) == 0
    panel.append_assistant_chunk("thinking line\n" * 8, "")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    if panel._streaming_turn_extent_px() < panel._scroll.viewport().height():
        assert _scrollbar_maximum_px(panel) == 0
        assert abs(_anchor_viewport_y(panel) - 8) <= 4
    panel.append_assistant_chunk("", "Sure.")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    panel.end_assistant_stream("Sure.")
    qapp.processEvents()
    qapp.processEvents()
    viewport_h = panel._scroll.viewport().height()
    assistant = panel._last_assistant_bubble()
    assert assistant is not None
    if panel._streaming_turn_extent_px(assistant) < viewport_h:
        assert _scrollbar_maximum_px(panel) == 0
        assert abs(_anchor_viewport_y(panel) - 8) <= 10


def test_first_turn_assistant_starts_below_user(qapp: QApplication, qtbot) -> None:
    """Answer markdown appears directly below the user bubble, not mid-viewport."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 480)
    user = panel.add_message("user", "how do i create scripts? give one small example")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel.append_assistant_chunk("thinking line\n" * 8, "")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    assistant = panel._streaming_bubble
    assert assistant is not None
    panel.append_assistant_chunk("", "Here is a short answer.\n")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    gap = _gap_user_bottom_to_assistant_top(panel, user, assistant)
    assert gap <= 16


def test_first_turn_thinking_text_is_not_centered_in_viewport(qapp: QApplication, qtbot) -> None:
    """First-turn thinking text keeps natural row height instead of absorbing slack."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(420, 640)
    user = panel.add_message(
        "user",
        "how do i create scripts in this app? can you give an example for a pre request "
        "script? give one small example",
    )
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()

    thinking = (
        "We need answer about app scripts. Need explain pre-request script, small example. "
        "Need maybe mention variables, pm API, where to add it in Scripts tab. "
        "Need concise actionable steps and a tiny script that sets a token variable before send. "
    ) * 4
    panel.append_assistant_chunk(thinking, "")
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)

    assistant = panel._streaming_bubble
    assert assistant is not None
    thought = assistant._thought_section
    assert thought is not None
    thought_layout = thought.layout()
    assert thought_layout is not None
    thought_label = thought._label
    thought_header = thought.findChild(QPushButton, "aiChatThoughtToggle")
    assert thought_header is not None

    row_gap = _gap_user_bottom_to_assistant_top(panel, user, assistant)
    header_gap = _viewport_top(panel, thought_header) - _viewport_top(panel, assistant)
    label_gap = _viewport_top(panel, thought_label) - (
        _viewport_top(panel, thought_header) + thought_header.height()
    )

    assert row_gap <= panel._messages_layout.spacing() + 4
    assert header_gap <= 8
    assert label_gap <= thought_layout.spacing() + 4
    assert assistant.height() <= assistant.sizeHint().height() + 4
    assert thought.height() <= thought.sizeHint().height() + 4
    assert thought_label.height() <= thought_label.sizeHint().height() + 4
    assert _large_slack_items_between(panel, user, assistant) == []


def test_second_user_message_anchor_stable_during_stream(qapp: QApplication, qtbot) -> None:
    """The second turn user prompt stays pinned while chunks stream in."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 480)
    panel.add_message("user", "first question")
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "Short answer.")
    _flush_stream_chunks(qtbot)
    panel.end_assistant_stream("Short answer.")
    qapp.processEvents()

    panel.add_message("user", "Can you give code?")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    baseline = _anchor_viewport_y(panel)
    _assert_scrolled_to_turn_start(panel)

    chunks = [
        "Sure:\n\n",
        "```python\n",
        "pm.response.json().get('id')\n",
        "pm.environment.set('auth_token', token)\n",
        "```\n",
    ]
    positions: list[int] = []
    for chunk in chunks:
        panel.append_assistant_chunk("thinking line\n" if chunk.startswith("```") else "", chunk)
        _flush_stream_chunks(qtbot)
        _drain_follow_passes(qtbot, qapp)
        positions.append(_anchor_viewport_y(panel))
        viewport_h = panel._scroll.viewport().height()
        if panel._streaming_turn_extent_px() < viewport_h:
            assert abs(positions[-1] - baseline) <= _SECOND_TURN_ANCHOR_TOLERANCE_PX
    _assert_no_anchor_oscillation(positions)


def test_thought_to_answer_transition_measures_anchor_even_when_overflowing(
    qapp: QApplication, qtbot
) -> None:
    """Thought collapse must not jump the prompt when the turn later fits the viewport."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 360)
    panel.add_message("user", "second question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    baseline = _anchor_viewport_y(panel)
    _assert_scrolled_to_turn_start(panel)

    samples = _measure_stream_anchor_movement(
        panel,
        qtbot,
        qapp,
        thinking_chunks=8,
        content_chunks=6,
        chunk_content="Here is the answer.\n",
    )
    viewport_h = panel._scroll.viewport().height()
    in_viewport = [anchor_y for anchor_y, extent in samples if extent < viewport_h]
    assert in_viewport, "expected at least one in-viewport measurement"
    _assert_anchor_movement_bounded(in_viewport, baseline=baseline)


def test_late_turn_scroll_uses_bottom_after_stream_overflows(qapp: QApplication, qtbot) -> None:
    """A delayed turn-start flush does not pull an overflowing stream back upward."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 160)
    panel.add_message("user", "first")
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "Short answer.")
    _flush_stream_chunks(qtbot)
    panel.end_assistant_stream("Short answer.")
    qapp.processEvents()
    panel.add_message("user", "second")
    panel.begin_assistant_stream()
    qapp.processEvents()
    panel._scroll_lock_enabled = True
    panel.append_assistant_chunk("", "line\n" * 80)
    _flush_stream_chunks(qtbot)
    panel._turn_scroll_pending = True
    panel._flush_turn_bottom_scroll()
    bar = panel._scroll.verticalScrollBar()
    if panel._streaming_turn_extent_px() >= panel._scroll.viewport().height():
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
    _assert_scrolled_to_turn_start(panel)
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
    assert names.count("_flush_stream_follow_frame") <= 1
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
    assert names.count("_flush_stream_follow_frame") <= 1
    assert names.count("_flush_stream_follow_retry") == 0
    assert "_apply_stream_follow" not in names


def test_chunk_flush_queues_deferred_follow_passes(qapp: QApplication, qtbot) -> None:
    """Overflow chunk flush queues coalesced frame and retry follow scheduler callbacks."""
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
    _stop_chunk_coalesce(panel)
    with patch.object(QTimer, "singleShot", side_effect=capture_single_shot):
        panel._flush_pending_chunks()
    _drain_follow_passes(qtbot, qapp)

    names = _scheduled_follow_scheduler_names(scheduled)
    assert names.count("_flush_stream_follow_frame") <= 1
    assert names.count("_flush_stream_follow_retry") == 0
    assert "_apply_stream_follow" not in names
    bar = panel._scroll.verticalScrollBar()
    assert bar.value() >= bar.maximum() - 2 or abs(bar.value() - panel._stream_follow_target()) <= 2


def test_follow_retry_scheduled_only_when_off_target_after_frame(qapp: QApplication, qtbot) -> None:
    """Late retry remains scoped to explicit frame-follow passes."""
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
    _stop_chunk_coalesce(panel)
    with patch.object(QTimer, "singleShot", side_effect=capture_single_shot):
        panel._flush_pending_chunks()
    frame_names = _scheduled_follow_scheduler_names(scheduled)
    assert frame_names.count("_flush_stream_follow_frame") <= 1
    assert frame_names.count("_flush_stream_follow_retry") == 0
    scheduled.clear()
    panel._stream_follow_dirty = True
    panel._stream_follow_frame_pending = True
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
    panel.append_assistant_chunk("", "answer line\n" * 12)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    # Spacer reconciliation may shrink scroll range when growth replaces slack.
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
    _drain_smooth_scroll(panel, qapp, qtbot)
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


def test_wheel_up_over_streaming_table_detaches_follow(qapp: QApplication, qtbot) -> None:
    """Wheel-up over a relayouting streaming table stays detached from auto-follow."""
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

    table = "| Browser | Notes |\n|---|---|\n"
    table += "".join(f"| **Opera {index}** | Fast `GET` row {index} |\n" for index in range(16))
    panel.append_assistant_chunk("", table)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)

    bubble = panel._streaming_bubble
    assert bubble is not None
    body = bubble.findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    bar = panel._scroll.verticalScrollBar()
    if bar.maximum() <= 0:
        pytest.skip("no scroll range in test environment")
    assert panel._scroll_lock_enabled is True

    _wheel_on_widget(body, delta_y=120)
    _drain_smooth_scroll(panel, qapp, qtbot)
    assert panel._scroll_lock_enabled is False
    position_after_scroll = bar.value()

    panel.append_assistant_chunk(
        "",
        "".join(f"| **Vivaldi {index}** | More streaming row {index} |\n" for index in range(8)),
    )
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
    _drain_smooth_scroll(panel, qapp, qtbot)
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


def test_clear_transcript_leaves_no_streaming_spacer(qapp: QApplication, qtbot) -> None:
    """Clearing the transcript leaves no streaming viewport spacer."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 400)
    panel.add_message("user", "hello")
    qapp.processEvents()
    panel.begin_assistant_stream()
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
    load_transcript_sync(panel, messages, qtbot)
    restored = panel.findChildren(ChatMessageBubble)[0]
    assert not restored.is_content_streaming()
    body = restored.findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    html = body.toHtml().lower()
    assert "font-weight:600" in html or "font-weight:700" in html


def test_sticky_user_prompt_shows_after_anchor_scrolls_above_viewport(
    qapp: QApplication, qtbot
) -> None:
    """Sticky clone appears once the real user bubble scrolls off the top."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _fill_transcript_and_start_stream(panel, qapp, qtbot)
    _scroll_until_anchor_above_viewport(panel, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert sticky.isVisible()
    assert sticky.text() == "question"


def test_sticky_user_prompt_footer_shows_stop_during_active_stream(
    qapp: QApplication, qtbot
) -> None:
    """Pinned sticky clone mirrors turn-scoped stop while the assistant streams."""
    from PySide6.QtWidgets import QFrame

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message("user", "question")
    panel.set_run_busy(True)
    panel.begin_assistant_stream()
    qapp.processEvents()
    _scroll_until_anchor_above_viewport(panel, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert sticky.isVisible()
    assert sticky.footer_mode() == "stop"
    frame = sticky.findChild(QFrame, "aiChatMessageUser")
    assert frame is not None
    stop_btn = frame.findChild(QPushButton, "smallPrimaryButton")
    assert stop_btn is not None
    assert stop_btn.toolTip() == "Stop"


def test_sticky_clone_copies_user_timestamp(qapp: QApplication, qtbot) -> None:
    """Sticky overlay includes the anchor user bubble send-time label."""
    from datetime import UTC, datetime

    from PySide6.QtWidgets import QFrame, QLabel

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    _ensure_transcript_scroll_range(panel, qapp)
    panel.add_message("user", "question", sent_at=datetime(2026, 1, 7, 14, 25, tzinfo=UTC))
    panel.add_message("assistant", "answer line\n" * 40)
    qapp.processEvents()
    _scroll_until_sticky_shows_text(panel, qapp, "question")
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert sticky.isVisible()
    frame = sticky.findChild(QFrame, "aiChatMessageUser")
    assert frame is not None
    label = frame.findChild(QLabel, "aiChatUserMessageTime")
    assert label is not None
    assert not label.isHidden()
    assert "Jan" in label.text()
    assert "7" in label.text()


def test_sticky_clone_respects_viewport_insets(qapp: QApplication, qtbot) -> None:
    """Sticky overlay compacts top margins and keeps viewport side insets."""
    from datetime import UTC, datetime

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    _ensure_transcript_scroll_range(panel, qapp)
    anchor = panel.add_message(
        "user",
        "How would you send an http request from a postman pre request script?",
        sent_at=datetime(2026, 6, 7, 14, 39, tzinfo=UTC),
    )
    panel.add_message("assistant", "answer line\n" * 40)
    qapp.processEvents()
    anchor_frame_h = anchor.user_message_frame_height()
    inset = _STICKY_PROMPT_VIEWPORT_INSET_PX
    _scroll_until_sticky_shows_text(panel, qapp, anchor.text())
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    viewport = panel._scroll.viewport()
    anchor_x = anchor.mapTo(viewport, QPoint(0, 0)).x()
    assert sticky.x() == max(inset, anchor_x - _STICKY_PROMPT_LEFT_SHIFT_PX)
    assert sticky.width() == viewport.width() - sticky.x() - inset
    assert sticky.height() <= anchor_frame_h
    assert sticky.height() > 0
    sticky_right = sticky.x() + sticky.width()
    assert sticky.x() >= inset
    assert sticky_right <= viewport.width() - inset


def test_sticky_user_prompt_hides_when_real_anchor_visible(qapp: QApplication, qtbot) -> None:
    """Sticky clone hides when the real user bubble is visible near the top."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _fill_transcript_and_start_stream(panel, qapp, qtbot)
    _scroll_until_anchor_above_viewport(panel, qapp)
    assert _sticky_turn_prompt(panel) is not None
    panel._scroll_to_turn_start(force=True)
    qapp.processEvents()
    panel._sync_sticky_turn_prompt()
    sticky = _sticky_turn_prompt(panel)
    assert sticky is None or not sticky.isVisible()


def test_sticky_user_prompt_persists_after_stream_for_same_turn(qapp: QApplication, qtbot) -> None:
    """Turn anchor and sticky prompt remain available after streaming ends."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _fill_transcript_and_start_stream(panel, qapp, qtbot)
    panel.end_assistant_stream("final answer\n" * 24)
    qapp.processEvents()
    assert panel._turn_scroll_anchor is not None
    _scroll_until_anchor_above_viewport(panel, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert sticky.isVisible()


def test_sticky_user_prompt_updates_to_later_turn_when_scrolling(qapp: QApplication, qtbot) -> None:
    """Scrolling into a later turn pins that turn's user prompt, not the first."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    _ensure_transcript_scroll_range(panel, qapp)
    panel.add_message("user", "first question")
    panel.add_message("assistant", "first answer line\n" * 40)
    panel.add_message("user", "second question")
    panel.add_message("assistant", "second answer line\n" * 40)
    qapp.processEvents()
    second_user = _user_bubble_with_text(panel, "second question")
    _scroll_until_user_above_viewport(panel, second_user, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert sticky.isVisible()
    assert sticky.text() == "second question"


def test_sticky_user_prompt_hides_while_later_turn_user_is_visible(
    qapp: QApplication, qtbot
) -> None:
    """Do not pin an older turn while the current turn's user bubble is on screen."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(12):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "first question")
    panel.add_message("assistant", "first answer line\n" * 40)
    panel.add_message("user", "second question")
    panel.add_message("assistant", "second answer line\n" * 40)
    qapp.processEvents()
    second_user = _user_bubble_with_text(panel, "second question")
    bar = panel._scroll.verticalScrollBar()
    for scroll_val in range(0, bar.maximum() + 1, 4):
        bar.setValue(scroll_val)
        qapp.processEvents()
        second_top = panel._widget_top_in_viewport(second_user)
        viewport_h = panel._scroll.viewport().height()
        if not (0 <= second_top < viewport_h):
            continue
        panel._sync_sticky_turn_prompt()
        sticky = _sticky_turn_prompt(panel)
        assert sticky is None or not sticky.isVisible() or sticky.text() != "first question"
        return
    pytest.fail("could not find scroll position with a visible later-turn user prompt")


def test_sticky_user_prompt_clears_on_new_turn(qapp: QApplication, qtbot) -> None:
    """Starting a new turn clears the previous sticky overlay."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _fill_transcript_and_start_stream(panel, qapp, qtbot)
    _scroll_until_anchor_above_viewport(panel, qapp)
    assert _sticky_turn_prompt(panel) is not None
    panel.end_assistant_stream("done")
    qapp.processEvents()
    panel.add_message("user", "next question")
    panel.begin_assistant_stream()
    qapp.processEvents()
    sticky = _sticky_turn_prompt(panel)
    assert sticky is None or not sticky.isVisible()


def test_sticky_user_prompt_does_not_change_scroll_range(qapp: QApplication, qtbot) -> None:
    """Sticky overlay is visual only and does not alter scrollbar range."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _fill_transcript_and_start_stream(panel, qapp, qtbot)
    bar = panel._scroll.verticalScrollBar()
    max_before = bar.maximum()
    _scroll_until_anchor_above_viewport(panel, qapp)
    assert bar.maximum() == max_before


def test_sticky_user_prompt_clamps_tall_user_message(qapp: QApplication, qtbot) -> None:
    """Very tall user prompts are clamped on the sticky overlay."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    long_prompt = "explain this\n" * 60
    _fill_transcript_and_start_stream(panel, qapp, qtbot, user_text=long_prompt, assistant_lines=30)
    _scroll_until_anchor_above_viewport(panel, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    cap = panel._sticky_prompt_height_cap()
    assert sticky.height() <= cap
    fade = sticky.findChild(QWidget, "aiChatUserMessageFade")
    assert fade is not None
    assert fade.isVisible()


def test_sticky_user_prompt_with_timestamp_keeps_label_visible(
    qapp: QApplication,
    qtbot,
) -> None:
    """Sticky overlay paints prompt text when the anchor row includes a sent-at timestamp."""
    from datetime import UTC, datetime

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    long_prompt = "are you sure?\n" + ("const line = 1;\n" * 40)
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message(
        "user",
        long_prompt,
        sent_at=datetime(2026, 6, 11, 18, 41, tzinfo=UTC),
    )
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "answer line\n" * 50)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    qapp.processEvents()
    _scroll_until_sticky_shows_text(panel, qapp, long_prompt)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    from PySide6.QtWidgets import QScrollArea

    label = sticky.findChild(QLabel, "aiChatUserMessageText")
    scroll_area = sticky.findChild(QScrollArea, "aiChatStickyScroll")
    label_host = sticky.findChild(QWidget, "aiChatStickyLabelHost")
    assert label is not None and scroll_area is not None and label_host is not None
    assert not scroll_area.isVisible()
    assert label_host.isVisible()
    assert label.text() == long_prompt
    assert label.height() >= 40
    assert sticky.height() >= label_host.height() + 20
    timestamp = sticky.findChild(QLabel, "aiChatUserMessageTime")
    assert timestamp is not None
    assert timestamp.isVisible()
    assert timestamp.height() >= 10
    assert label.maximumHeight() >= 40
    assert label.text().startswith("are you sure")


def test_sticky_toggle_positioned_after_unchanged_sync(qapp: QApplication, qtbot) -> None:
    """Deferred sticky sync must not leave Show more overlapping the timestamp."""
    from datetime import UTC, datetime

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    long_prompt = "are you sure?\n" + ("const line = 1;\n" * 40)
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message(
        "user",
        long_prompt,
        sent_at=datetime(2026, 6, 11, 18, 41, tzinfo=UTC),
    )
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "answer line\n" * 50)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    qapp.processEvents()
    _scroll_until_sticky_shows_text(panel, qapp, long_prompt)
    panel._sync_sticky_turn_prompt()
    panel._sync_sticky_turn_prompt()

    from PySide6.QtWidgets import QScrollArea

    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None and sticky.isVisible()
    scroll_area = sticky.findChild(QScrollArea, "aiChatStickyScroll")
    label_host = sticky.findChild(QWidget, "aiChatStickyLabelHost")
    toggle = sticky.findChild(QPushButton, "aiChatUserMessageToggle")
    footer = sticky.findChild(QWidget, "aiChatUserMessageFooter")
    timestamp = sticky.findChild(QLabel, "aiChatUserMessageTime")
    assert scroll_area is not None and label_host is not None
    assert toggle is not None and footer is not None
    assert timestamp is not None
    assert not scroll_area.isVisible() and label_host.isVisible()
    assert toggle.isVisible() and footer.isVisible() and timestamp.isVisible()
    label_bottom = _sticky_label_column_bottom(sticky)
    assert toggle.y() >= label_bottom - 2
    toggle_bottom = toggle.y() + toggle.height()
    assert footer.y() >= toggle_bottom - 2


def test_sticky_user_prompt_show_more_caps_to_content_without_timestamp_gap(
    qapp: QApplication,
    qtbot,
) -> None:
    """Expanded sticky height hugs content; timestamp stays directly below the prompt."""
    from datetime import UTC, datetime

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    long_prompt = "are you sure?\n" + ("const line = 1;\n" * 40)
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message(
        "user",
        long_prompt,
        sent_at=datetime(2026, 6, 11, 18, 41, tzinfo=UTC),
    )
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "answer line\n" * 50)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    qapp.processEvents()
    _scroll_until_sticky_shows_text(panel, qapp, long_prompt)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    toggle = sticky.findChild(QPushButton, "aiChatUserMessageToggle")
    assert toggle is not None
    assert toggle.text() == "Show more"
    toggle.click()
    panel._sync_sticky_turn_prompt()
    for _ in range(3):
        qapp.processEvents()
    assert sticky.is_user_message_expanded()
    cap = panel._sticky_prompt_height_cap()
    assert sticky.height() <= cap + 2
    label = sticky.findChild(QLabel, "aiChatUserMessageText")
    assert label is not None
    assert label.height() >= 40
    footer = sticky.findChild(QWidget, "aiChatUserMessageFooter")
    timestamp = footer.findChild(QLabel, "aiChatUserMessageTime") if footer is not None else None
    assert footer is not None and timestamp is not None
    assert footer.isVisible() and timestamp.isVisible()
    toggle_bottom = toggle.y() + toggle.height()
    assert footer.y() >= toggle_bottom - 2


def test_sticky_user_prompt_toggle_does_not_mutate_anchor(qapp: QApplication, qtbot) -> None:
    """Show more on the sticky overlay expands only the overlay, not the transcript row."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    long_prompt = "user prompt line\n" * 24
    _fill_transcript_and_start_stream(
        panel,
        qapp,
        qtbot,
        user_text=long_prompt,
        assistant_lines=30,
    )
    user = _user_bubble_with_text(panel, long_prompt)
    _scroll_until_anchor_above_viewport(panel, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    toggle = sticky.findChild(QPushButton, "aiChatUserMessageToggle")
    assert toggle is not None
    assert toggle.isVisible()
    assert toggle.text() == "Show more"
    anchor_expanded_before = user.is_user_message_expanded()
    scroll_before = panel._scroll.verticalScrollBar().value()
    toggle.click()
    panel._sync_sticky_turn_prompt()
    for _ in range(3):
        qapp.processEvents()
    assert sticky.is_user_message_expanded()
    assert toggle.text() == "Show less"
    assert user.is_user_message_expanded() == anchor_expanded_before
    assert panel._scroll.verticalScrollBar().value() == scroll_before


def test_sticky_toggle_roundtrip_stays_clickable_without_manual_sync(
    qapp: QApplication,
    qtbot,
) -> None:
    """Expand/collapse/expand on sticky stays clickable via deferred sync only."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    long_prompt = "user prompt line\n" * 24
    _fill_transcript_and_start_stream(
        panel,
        qapp,
        qtbot,
        user_text=long_prompt,
        assistant_lines=30,
    )
    _scroll_until_anchor_above_viewport(panel, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    toggle = sticky.findChild(QPushButton, "aiChatUserMessageToggle")
    label = sticky.findChild(QLabel, "aiChatUserMessageText")
    label_host = sticky.findChild(QWidget, "aiChatStickyLabelHost")
    assert toggle is not None and label is not None and label_host is not None
    assert toggle.text() == "Show more"

    toggle.click()
    _drain_follow_passes(qtbot, qapp)
    qapp.processEvents()
    assert sticky.is_user_message_expanded()
    assert toggle.text() == "Show less"
    assert label.height() <= label_host.height()

    toggle.click()
    _drain_follow_passes(qtbot, qapp)
    qapp.processEvents()
    assert not sticky.is_user_message_expanded()
    assert toggle.text() == "Show more"
    assert label.height() <= label_host.height()

    qtbot.mouseClick(toggle, Qt.MouseButton.LeftButton)
    _drain_follow_passes(qtbot, qapp)
    qapp.processEvents()
    assert sticky.is_user_message_expanded()
    assert toggle.text() == "Show less"


def test_sticky_user_prompt_expanded_is_internally_scrollable(qapp: QApplication, qtbot) -> None:
    """Expanding a very long sticky prompt yields an internal scrollbar, not a clamp."""
    from PySide6.QtWidgets import QScrollArea

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    long_prompt = "scrollable prompt line\n" * 60
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message("user", long_prompt)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "answer line\n" * 60)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    qapp.processEvents()
    _scroll_until_sticky_shows_text(panel, qapp, long_prompt)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    toggle = sticky.findChild(QPushButton, "aiChatUserMessageToggle")
    assert toggle is not None
    toggle.click()
    panel._sync_sticky_turn_prompt()
    for _ in range(3):
        qapp.processEvents()
    assert sticky.is_user_message_expanded()
    scroll_area = sticky.findChild(QScrollArea, "aiChatStickyScroll")
    assert scroll_area is not None and scroll_area.isVisible()
    bar = scroll_area.verticalScrollBar()
    assert bar.maximum() > 0


def test_sticky_user_prompt_expand_grows_without_moving_transcript(
    qapp: QApplication,
    qtbot,
) -> None:
    """Show more makes the sticky overlay taller while the transcript scroll stays put."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    long_prompt = "scrollable prompt line\n" * 60
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message("user", long_prompt)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "answer line\n" * 60)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    qapp.processEvents()
    _scroll_until_sticky_shows_text(panel, qapp, long_prompt)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    collapsed_h = sticky.height()
    scroll_before = panel._scroll.verticalScrollBar().value()
    toggle = sticky.findChild(QPushButton, "aiChatUserMessageToggle")
    assert toggle is not None
    toggle.click()
    panel._sync_sticky_turn_prompt()
    for _ in range(6):
        qapp.processEvents()
    qtbot.wait(20)
    qapp.processEvents()
    assert sticky.is_user_message_expanded()
    assert sticky.height() >= collapsed_h
    assert panel._scroll.verticalScrollBar().value() == scroll_before


def test_sticky_wheel_at_internal_top_scrolls_transcript(qapp: QApplication, qtbot) -> None:
    """At the sticky's internal scroll top, wheeling up scrolls the transcript, not nothing."""
    from PySide6.QtWidgets import QScrollArea

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    long_prompt = "scrollable prompt line\n" * 60
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message("user", long_prompt)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "answer line\n" * 60)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    qapp.processEvents()
    _scroll_until_sticky_shows_text(panel, qapp, long_prompt)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    toggle = sticky.findChild(QPushButton, "aiChatUserMessageToggle")
    assert toggle is not None
    toggle.click()
    panel._sync_sticky_turn_prompt()
    for _ in range(3):
        qapp.processEvents()
    assert sticky.is_user_message_expanded()
    inner = sticky.findChild(QScrollArea, "aiChatStickyScroll")
    assert inner is not None and inner.isVisible()
    inner.verticalScrollBar().setValue(0)
    qapp.processEvents()
    transcript_before = panel._scroll.verticalScrollBar().value()
    label = sticky.findChild(QLabel, "aiChatUserMessageText")
    assert label is not None
    _wheel_on_widget(label, delta_y=120)
    _drain_smooth_scroll(panel, qapp, qtbot)
    qapp.processEvents()
    assert panel._scroll.verticalScrollBar().value() < transcript_before


def test_sticky_user_prompt_short_non_collapsible_shows_label_text(
    qapp: QApplication,
    qtbot,
) -> None:
    """Short expanded prompts paint visible label text on the sticky overlay."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(14):
        panel.add_message("user", f"fill {index} " * 8)
    panel.add_message("user", "Hi there")
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "answer line\n" * 40)
    _flush_stream_chunks(qtbot)
    _drain_follow_passes(qtbot, qapp)
    qapp.processEvents()
    _scroll_until_sticky_shows_text(panel, qapp, "Hi there")
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert sticky.isVisible()
    label = sticky.findChild(QLabel, "aiChatUserMessageText")
    assert label is not None
    assert label.text() == "Hi there"
    assert label.height() >= 10
    assert sticky.is_user_message_expanded()


def test_sticky_user_prompt_expanded_long_anchor_stays_visible(
    qapp: QApplication,
    qtbot,
) -> None:
    """Expanding the sticky overlay shows a tall readable prompt independent of the anchor."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    long_prompt = "user prompt line\n" * 24
    _fill_transcript_and_start_stream(panel, qapp, qtbot, user_text=long_prompt, assistant_lines=30)
    user = _user_bubble_with_text(panel, long_prompt)
    _scroll_until_anchor_above_viewport(panel, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    sticky_toggle = sticky.findChild(QPushButton, "aiChatUserMessageToggle")
    assert sticky_toggle is not None
    sticky_toggle.click()
    panel._sync_sticky_turn_prompt()
    for _ in range(3):
        qapp.processEvents()
    assert sticky.is_user_message_expanded()
    assert not user.is_user_message_expanded()
    label = sticky.findChild(QLabel, "aiChatUserMessageText")
    assert label is not None
    assert label.height() >= 40


def test_sticky_user_prompt_unchanged_sync_repairs_label_geometry(
    qapp: QApplication,
    qtbot,
) -> None:
    """A second sync with unchanged geometry must not leave a zero-height label."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    long_prompt = "are you sure?\n" + ("line\n" * 30)
    _fill_transcript_and_start_stream(panel, qapp, qtbot, user_text=long_prompt, assistant_lines=30)
    _scroll_until_anchor_above_viewport(panel, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    panel._sync_sticky_turn_prompt()
    qapp.processEvents()
    label = sticky.findChild(QLabel, "aiChatUserMessageText")
    assert label is not None
    assert label.height() >= 40


def test_sticky_sync_runs_after_smooth_wheel_scroll_finishes(
    qapp: QApplication,
    qtbot,
) -> None:
    """Smooth-scroll settle flushes deferred sticky sync without a manual sync call."""
    from unittest.mock import patch

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _fill_transcript_and_start_stream(panel, qapp, qtbot, assistant_lines=40)
    anchor = panel._turn_scroll_anchor
    assert anchor is not None
    bar = panel._scroll.verticalScrollBar()
    while panel._widget_top_in_viewport(anchor) >= -5 and bar.value() < bar.maximum():
        bar.setValue(min(bar.maximum(), bar.value() + 48))
        qapp.processEvents()
    original_sync = panel._sync_sticky_turn_prompt
    sync_calls: list[int] = []

    def counting_sync() -> None:
        sync_calls.append(1)
        original_sync()

    with patch.object(panel, "_sync_sticky_turn_prompt", side_effect=counting_sync):
        _wheel_on_transcript(panel, delta_y=320)
        qapp.processEvents()
        _drain_smooth_scroll(panel, qapp, qtbot, timeout_ms=600)
        panel._flush_sticky_sync()
        qapp.processEvents()
    assert sync_calls


def test_scroll_down_button_stays_above_sticky_prompt(qapp: QApplication, qtbot) -> None:
    """Scroll-down button remains visible above the sticky prompt when detached."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _fill_transcript_and_start_stream(panel, qapp, qtbot)
    _detach_scroll_panel(panel, qapp)
    _scroll_until_anchor_above_viewport(panel, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    panel._reposition_scroll_down_button()
    assert panel._scroll_down_btn.isVisible()
    assert panel._scroll_down_btn.parent() is panel._scroll.viewport()
    assert panel._scroll_down_btn.y() > sticky.y()


def test_sticky_user_prompt_hides_when_scrolled_above_turn(qapp: QApplication, qtbot) -> None:
    """Sticky clone hides once the active turn answer no longer extends below the overlay."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _fill_transcript_and_start_stream(panel, qapp, qtbot, assistant_lines=40)
    panel.end_assistant_stream("answer line\n" * 40)
    qapp.processEvents()
    for index in range(12):
        panel.add_message("user", f"tail {index} " * 10)
        panel.add_message("assistant", f"tail reply {index}\n" * 8)
    qapp.processEvents()
    _scroll_until_anchor_above_viewport(panel, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert sticky.isVisible()
    _scroll_until_no_sticky_turn(panel, qapp)


def test_sticky_user_prompt_clears_on_load_transcript(qapp: QApplication, qtbot) -> None:
    """Replacing the transcript clears any visible sticky overlay."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _fill_transcript_and_start_stream(panel, qapp, qtbot)
    _scroll_until_anchor_above_viewport(panel, qapp)
    assert _sticky_turn_prompt(panel) is not None
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "assistant",
            "content": "replaced",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    load_transcript_sync(panel, messages, qtbot)
    qtbot.wait(10)
    qapp.processEvents()
    sticky = _sticky_turn_prompt(panel)
    assert sticky is None or not sticky.isVisible()


def test_sticky_user_prompt_works_after_load_transcript(qapp: QApplication, qtbot) -> None:
    """Loaded sessions restore the turn anchor so sticky works on the last turn."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(16):
        panel.add_message("user", f"fill {index} " * 8)
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "user",
            "content": "question",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": 2,
            "session_id": "s1",
            "role": "assistant",
            "content": "answer line\n" * 40,
            "created_at": "2026-01-01T00:00:01+00:00",
        },
    ]
    load_transcript_sync(panel, messages, qtbot)
    qtbot.wait(10)
    qapp.processEvents()
    assert panel._turn_scroll_anchor is not None
    assert panel._turn_scroll_anchor.text() == "question"
    _scroll_until_anchor_above_viewport(panel, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert sticky.isVisible()


def test_sticky_user_prompt_works_after_startup_style_load(qapp: QApplication, qtbot) -> None:
    """Sticky works when the transcript loads before the panel is first shown."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "user",
            "content": "question",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": 2,
            "session_id": "s1",
            "role": "assistant",
            "content": "answer line\n" * 40,
            "created_at": "2026-01-01T00:00:01+00:00",
        },
    ]
    load_transcript_sync(panel, messages, qtbot)
    qtbot.wait(10)
    qapp.processEvents()
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    qapp.processEvents()
    panel._finish_load_transcript_layout()
    assert panel._turn_scroll_anchor is not None
    _scroll_until_anchor_above_viewport(panel, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert sticky.isVisible()


def test_sticky_user_prompt_hysteresis_near_viewport_top(qapp: QApplication, qtbot) -> None:
    """Sticky hides inside the hysteresis band when the real anchor re-enters the top edge."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _fill_transcript_and_start_stream(panel, qapp, qtbot)
    _scroll_until_anchor_above_viewport(panel, qapp, margin=8)
    assert _sticky_turn_prompt(panel) is not None
    anchor = panel._turn_scroll_anchor
    assert anchor is not None
    bar = panel._scroll.verticalScrollBar()
    while panel._widget_top_in_viewport(anchor) < -2 and bar.value() > 0:
        bar.setValue(max(0, bar.value() - 12))
        qapp.processEvents()
    panel._sync_sticky_turn_prompt()
    sticky = _sticky_turn_prompt(panel)
    assert sticky is None or not sticky.isVisible()


def test_sticky_pins_closest_older_turn_in_restored_history(qapp: QApplication, qtbot) -> None:
    """Sticky pins the closest older user prompt while reading an earlier answer."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(12):
        panel.add_message("user", f"fill {index} " * 10)
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "user",
            "content": "first question",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": 2,
            "session_id": "s1",
            "role": "assistant",
            "content": "first answer line\n" * 40,
            "created_at": "2026-01-01T00:00:01+00:00",
        },
        {
            "id": 3,
            "session_id": "s1",
            "role": "user",
            "content": "second question",
            "created_at": "2026-01-01T00:00:02+00:00",
        },
        {
            "id": 4,
            "session_id": "s1",
            "role": "assistant",
            "content": "second answer line\n" * 40,
            "created_at": "2026-01-01T00:00:03+00:00",
        },
    ]
    load_transcript_sync(panel, messages, qtbot)
    qtbot.wait(10)
    qapp.processEvents()
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(0)
    qapp.processEvents()
    _scroll_until_sticky_shows_text(panel, qapp, "first question")
    first_user = _user_bubble_with_text(panel, "first question")
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert sticky.isVisible()
    assert panel._sticky_turn_anchor is first_user


def test_sticky_hides_between_turns_in_multi_turn_history(qapp: QApplication, qtbot) -> None:
    """Sticky hides in the gap after one turn ends and before the next begins."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(12):
        panel.add_message("user", f"fill {index} " * 10)
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "user",
            "content": "first question",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": 2,
            "session_id": "s1",
            "role": "assistant",
            "content": "first answer line\n" * 40,
            "created_at": "2026-01-01T00:00:01+00:00",
        },
        {
            "id": 3,
            "session_id": "s1",
            "role": "user",
            "content": "second question",
            "created_at": "2026-01-01T00:00:02+00:00",
        },
        {
            "id": 4,
            "session_id": "s1",
            "role": "assistant",
            "content": "second answer line\n" * 40,
            "created_at": "2026-01-01T00:00:03+00:00",
        },
    ]
    load_transcript_sync(panel, messages, qtbot)
    qtbot.wait(10)
    qapp.processEvents()
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(0)
    qapp.processEvents()
    _scroll_until_sticky_shows_text(panel, qapp, "first question")
    first_user = _user_bubble_with_text(panel, "first question")
    first_assistant = panel._assistant_bubble_for_turn(first_user)
    assert first_assistant is not None
    while panel._widget_bottom_in_viewport(first_assistant) > 0 and bar.value() < bar.maximum():
        bar.setValue(min(bar.maximum(), bar.value() + 24))
        qapp.processEvents()
    second_user = _user_bubble_with_text(panel, "second question")
    for scroll_val in range(bar.value(), -1, -4):
        bar.setValue(scroll_val)
        qapp.processEvents()
        panel._sync_sticky_turn_prompt()
        sticky = _sticky_turn_prompt(panel)
        if (sticky is None or not sticky.isVisible()) and panel._widget_top_in_viewport(
            second_user
        ) >= -8:
            assert panel._sticky_turn_anchor is None
            return
    pytest.fail("could not find between-turn scroll position with sticky hidden")


def test_sticky_switches_to_second_turn_when_scrolling_into_its_answer(
    qapp: QApplication, qtbot
) -> None:
    """Sticky switches from the first turn prompt to the second while scrolling down."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(12):
        panel.add_message("user", f"fill {index} " * 10)
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "user",
            "content": "first question",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": 2,
            "session_id": "s1",
            "role": "assistant",
            "content": "first answer line\n" * 40,
            "created_at": "2026-01-01T00:00:01+00:00",
        },
        {
            "id": 3,
            "session_id": "s1",
            "role": "user",
            "content": "second question",
            "created_at": "2026-01-01T00:00:02+00:00",
        },
        {
            "id": 4,
            "session_id": "s1",
            "role": "assistant",
            "content": "second answer line\n" * 40,
            "created_at": "2026-01-01T00:00:03+00:00",
        },
    ]
    load_transcript_sync(panel, messages, qtbot)
    qtbot.wait(10)
    qapp.processEvents()
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(0)
    qapp.processEvents()
    _scroll_until_sticky_shows_text(panel, qapp, "first question")
    _scroll_until_sticky_shows_text(panel, qapp, "second question")
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert sticky.text() == "second question"
    second_user = _user_bubble_with_text(panel, "second question")
    assert panel._sticky_turn_anchor is second_user


def test_sticky_user_prompt_survives_viewport_resize(qapp: QApplication, qtbot) -> None:
    """Sticky overlay stays visible and reclamps after the panel is resized."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _fill_transcript_and_start_stream(panel, qapp, qtbot)
    _scroll_until_anchor_above_viewport(panel, qapp)
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    panel.resize(360, 220)
    qapp.processEvents()
    panel._sync_sticky_turn_prompt()
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert sticky.isVisible()
    cap = panel._sticky_prompt_height_cap()
    assert sticky.height() <= cap


def _build_scrollable_assistant_panel(
    panel: AiChatPanel,
    qapp: QApplication,
    qtbot,
) -> tuple[ChatMessageBubble, MarkdownContent]:
    """Show a long assistant answer and return its bubble and markdown body."""
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    _ensure_transcript_scroll_range(panel, qapp)
    panel.add_message("user", "question")
    bubble = panel.add_message("assistant", "answer line\n" * 48)
    qapp.processEvents()
    body = bubble.findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    return bubble, body


def test_wheel_over_assistant_text_scrolls_transcript(qapp: QApplication, qtbot) -> None:
    """Wheel over assistant markdown scrolls the outer transcript."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _, body = _build_scrollable_assistant_panel(panel, qapp, qtbot)
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    qapp.processEvents()
    value_before = bar.value()
    _wheel_on_widget(body, delta_y=120)
    _drain_smooth_scroll(panel, qapp, qtbot)
    assert bar.value() < value_before


def test_thought_toggle_compensates_scroll_to_avoid_answer_jump(qapp: QApplication, qtbot) -> None:
    """Expanding thought keeps the answer body at the same viewport position."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 400)
    panel.add_message("user", "what about python?")
    bubble = panel.add_message(
        "assistant",
        "answer line\n" * 40,
        thinking="internal reasoning line\n" * 10,
        thinking_duration_seconds=18,
    )
    body = bubble.findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    toggle = bubble.findChild(QPushButton, "aiChatThoughtToggle")
    assert toggle is not None
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(0)
    _drain_follow_passes(qtbot, qapp)
    _wait_for_bubble_in_viewport(panel, bubble, qtbot)
    answer_top_before = panel._widget_top_in_viewport(body)
    scroll_before = bar.value()
    toggle.click()
    for _ in range(3):
        qapp.processEvents()
    qtbot.wait(30)
    qapp.processEvents()
    assert bubble.is_thinking_expanded()
    answer_top_after = panel._widget_top_in_viewport(body)
    assert abs(answer_top_after - answer_top_before) <= 4
    if scroll_before < bar.maximum():
        assert bar.value() > scroll_before


def test_wheel_over_thought_text_scrolls_transcript(qapp: QApplication, qtbot) -> None:
    """Wheel over thinking labels scrolls the outer transcript."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    _ensure_transcript_scroll_range(panel, qapp)
    panel.add_message("user", "question")
    bubble = panel.add_message(
        "assistant",
        "answer line\n" * 40,
        thinking="thinking line\n" * 40,
    )
    qapp.processEvents()
    thought = bubble.findChild(QLabel, "aiChatThoughtText")
    assert thought is not None
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    qapp.processEvents()
    value_before = bar.value()
    _wheel_on_widget(thought, delta_y=120)
    _drain_smooth_scroll(panel, qapp, qtbot)
    assert bar.value() < value_before


def test_wheel_over_user_message_text_scrolls_transcript(qapp: QApplication, qtbot) -> None:
    """Wheel over user message labels scrolls the outer transcript."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    _ensure_transcript_scroll_range(panel, qapp)
    user = panel.add_message("user", "user prompt line\n" * 24)
    panel.add_message("assistant", "answer line\n" * 40)
    qapp.processEvents()
    label = user.findChild(QLabel, "aiChatUserMessageText")
    assert label is not None
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    qapp.processEvents()
    value_before = bar.value()
    _wheel_on_widget(label, delta_y=120)
    _drain_smooth_scroll(panel, qapp, qtbot)
    assert bar.value() < value_before


def test_sticky_turn_pairs_rebuild_after_load_transcript(qapp: QApplication, qtbot) -> None:
    """Batch transcript load rebuilds cached turn pairs once after layout settles."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "user",
            "content": "first question",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": 2,
            "session_id": "s1",
            "role": "assistant",
            "content": "first answer",
            "created_at": "2026-01-01T00:00:01+00:00",
        },
        {
            "id": 3,
            "session_id": "s1",
            "role": "user",
            "content": "second question",
            "created_at": "2026-01-01T00:00:02+00:00",
        },
        {
            "id": 4,
            "session_id": "s1",
            "role": "assistant",
            "content": "second answer",
            "created_at": "2026-01-01T00:00:03+00:00",
        },
    ]
    load_transcript_sync(panel, messages, qtbot)
    assert panel._sticky_turn_pairs_dirty is False
    assert len(panel._sticky_turn_pairs) == 2
    assert panel._sticky_turn_pairs == list(panel._iter_chat_turns())


def test_sticky_turn_pairs_invalidate_on_new_stream(qapp: QApplication, qtbot) -> None:
    """Starting a new assistant stream rebuilds cached turn pairs for the active turn."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.add_message("user", "question")
    panel.add_message("assistant", "answer")
    panel._rebuild_sticky_turn_pairs()
    assert panel._sticky_turn_pairs_dirty is False
    panel.add_message("user", "next")
    panel.begin_assistant_stream()
    assert panel._sticky_turn_pairs_dirty is False
    streaming = panel._streaming_bubble
    assert streaming is not None
    assert any(assistant is streaming for _user, assistant in panel._sticky_turn_pairs)


def test_sticky_turn_selection_uses_cached_pairs_for_closest_turn(
    qapp: QApplication, qtbot
) -> None:
    """Cached turn pairs preserve closest-turn sticky selection at turn boundaries."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(12):
        panel.add_message("user", f"fill {index} " * 10)
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "user",
            "content": "first question",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": 2,
            "session_id": "s1",
            "role": "assistant",
            "content": "first answer line\n" * 40,
            "created_at": "2026-01-01T00:00:01+00:00",
        },
        {
            "id": 3,
            "session_id": "s1",
            "role": "user",
            "content": "second question",
            "created_at": "2026-01-01T00:00:02+00:00",
        },
        {
            "id": 4,
            "session_id": "s1",
            "role": "assistant",
            "content": "second answer line\n" * 40,
            "created_at": "2026-01-01T00:00:03+00:00",
        },
    ]
    load_transcript_sync(panel, messages, qtbot)
    qtbot.wait(10)
    qapp.processEvents()
    panel._finish_load_transcript_layout()
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(0)
    qapp.processEvents()
    _scroll_until_sticky_shows_text(panel, qapp, "first question")
    first_user = _user_bubble_with_text(panel, "first question")
    cap = panel._sticky_prompt_height_cap()
    selected = panel._sticky_turn_for_viewport(cap)
    assert selected is not None
    assert selected.user is first_user
    assert selected.assistant is panel._assistant_bubble_for_turn(first_user)
    _scroll_until_sticky_shows_text(panel, qapp, "second question")
    second_user = _user_bubble_with_text(panel, "second question")
    cap = panel._sticky_prompt_height_cap()
    selected = panel._sticky_turn_for_viewport(cap)
    assert selected is not None
    assert selected.user is second_user
    assert selected.assistant is panel._assistant_bubble_for_turn(second_user)


def test_sticky_extents_cache_stays_warm_across_scroll_values(qapp: QApplication, qtbot) -> None:
    """Cached layout-space extents avoid per-tick mapTo while scroll offset changes."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    for index in range(12):
        panel.add_message("user", f"fill {index} " * 10)
    panel.add_message("user", "first question")
    panel.add_message("assistant", "first answer line\n" * 40)
    panel.add_message("user", "second question")
    panel.add_message("assistant", "second answer line\n" * 40)
    qapp.processEvents()
    panel._ensure_sticky_turn_extents()
    assert panel._sticky_extents_dirty is False
    bar = panel._scroll.verticalScrollBar()
    cap = panel._sticky_prompt_height_cap()
    bar.setValue(0)
    qapp.processEvents()
    _scroll_until_sticky_shows_text(panel, qapp, "first question")
    first_user = _user_bubble_with_text(panel, "first question")
    first = panel._sticky_turn_for_viewport(cap)
    assert first is not None
    assert first.user is first_user
    assert first.assistant is panel._assistant_bubble_for_turn(first_user)
    bar.setValue(min(bar.maximum(), bar.value() + 40))
    qapp.processEvents()
    panel._sync_sticky_turn_prompt()
    assert panel._sticky_extents_dirty is False


def test_sticky_extents_invalidate_on_panel_resize(qapp: QApplication, qtbot) -> None:
    """Panel resize marks cached turn extents dirty for reclamp on next sync."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    panel.add_message("user", "question")
    panel.add_message("assistant", "answer line\n" * 30)
    qapp.processEvents()
    panel._ensure_sticky_turn_extents()
    qtbot.wait(20)
    qapp.processEvents()
    invalidate = panel._invalidate_sticky_extents
    with (
        patch.object(panel, "_schedule_sticky_sync"),
        patch.object(panel, "_sync_sticky_turn_prompt"),
        patch.object(panel, "_invalidate_sticky_extents", wraps=invalidate) as spy,
    ):
        panel.resize(360, 220)
        qapp.processEvents()
        assert spy.call_count >= 1
    assert panel._sticky_extents_dirty is True


def test_sticky_sync_skips_overlay_mutation_when_unchanged(qapp: QApplication, qtbot) -> None:
    """Repeated sync at the same scroll position does not reapply overlay geometry."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _fill_transcript_and_start_stream(panel, qapp, qtbot)
    _scroll_until_anchor_above_viewport(panel, qapp)
    panel._sync_sticky_turn_prompt()
    applied_geom = panel._sticky_applied_geom
    applied_anchor = panel._sticky_applied_anchor
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert panel._sticky_applied_visible is True
    position_before = sticky.pos()
    panel._sync_sticky_turn_prompt()
    assert panel._sticky_applied_geom == applied_geom
    assert panel._sticky_applied_anchor is applied_anchor
    assert sticky.pos() == position_before


def test_sticky_extents_invalidate_on_add_message(qapp: QApplication, qtbot) -> None:
    """Transcript growth marks cached turn extents dirty."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.add_message("user", "question")
    panel.add_message("assistant", "answer")
    panel._ensure_sticky_turn_extents()
    assert panel._sticky_extents_dirty is False
    panel.add_message("user", "next")
    assert panel._sticky_extents_dirty is True


def test_sticky_extents_invalidate_on_layout_height_changed(qapp: QApplication, qtbot) -> None:
    """Assistant layout-height hooks mark cached turn extents dirty."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.add_message("user", "question")
    panel.add_message("assistant", "answer line\n" * 20)
    panel._attach_transcript_layout_hooks()
    panel._ensure_sticky_turn_extents()
    assert panel._sticky_extents_dirty is False
    panel._on_transcript_bubble_layout_changed()
    assert panel._sticky_extents_dirty is True


def test_schedule_sticky_sync_coalesces_to_one_frame_pass(qapp: QApplication, qtbot) -> None:
    """Burst schedule calls collapse to one deferred sticky sync pass."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    calls: list[int] = []
    original = panel._sync_sticky_turn_prompt

    def counting_sync() -> None:
        calls.append(1)
        original()

    panel._sync_sticky_turn_prompt = counting_sync  # type: ignore[method-assign]
    panel._schedule_sticky_sync()
    panel._schedule_sticky_sync()
    panel._schedule_sticky_sync()
    qtbot.wait(10)
    qapp.processEvents()
    assert len(calls) == 1


def test_long_transcript_has_no_assistant_qtext_browsers(qapp: QApplication, qtbot) -> None:
    """Long restored transcripts must not instantiate one QTextBrowser per assistant row."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(420, 600)
    messages: list[AiChatMessageDict] = []
    for i in range(80):
        messages.append(
            {
                "id": i * 2,
                "session_id": "s1",
                "role": "user",
                "content": f"user question {i}",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
        messages.append(
            {
                "id": i * 2 + 1,
                "session_id": "s1",
                "role": "assistant",
                "content": f"answer {i} with **bold** and `code`\n" * 12,
                "created_at": "2026-01-01T00:00:01+00:00",
            }
        )
    load_transcript_sync(panel, messages, qtbot)
    qapp.processEvents()
    browsers = panel.findChildren(QTextBrowser, "aiChatAssistantText")
    bodies = panel.findChildren(MarkdownContent, "aiChatAssistantText")
    assert browsers == []
    assert len(bodies) == 80
