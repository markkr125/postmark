"""Resize performance and correctness tests for the AI chat panel."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from unittest.mock import patch

from PySide6.QtCore import QSize
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QApplication, QLayout

from services.ai.chat.session_service import AiChatMessageDict
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.chat_panel.scroll import _RESIZE_SETTLE_MS
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent
from ui.sidebar.ai.message_bubble.wrapping_label import _WrappingLabel


def _long_transcript_messages(count: int) -> list[AiChatMessageDict]:
    """Build alternating user/assistant messages for resize stress tests."""
    messages: list[AiChatMessageDict] = []
    for index in range(count):
        role = "user" if index % 2 == 0 else "assistant"
        body = (
            f"{role} line {index}\n" + "```python\nprint('block')\n```\n" * 2
            if role == "assistant"
            else f"Question {index}?"
        )
        messages.append(
            {
                "id": index,
                "session_id": "s1",
                "role": role,
                "content": body,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
    return messages


def _assistant_bodies(panel: AiChatPanel) -> list[MarkdownContent]:
    """Return markdown bodies for every assistant row in *panel*."""
    bodies: list[MarkdownContent] = []
    for bubble in panel.findChildren(ChatMessageBubble):
        if bubble.role == "assistant" and bubble._markdown_body is not None:
            bodies.append(bubble._markdown_body)
    return bodies


def test_hidden_panel_resize_skips_sticky_sync(qapp: QApplication, qtbot) -> None:
    """When the AI panel is hidden, resize must not schedule sticky overlay work."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.add_message("user", "hello")
    panel.add_message("assistant", "world")
    panel.hide()
    qapp.processEvents()
    with patch.object(panel, "_schedule_sticky_sync") as sticky_spy:
        panel.resizeEvent(QResizeEvent(QSize(320, 400), QSize(280, 400)))
        qapp.processEvents()
        sticky_spy.assert_not_called()


def test_markdown_height_cache_reuses_single_document_size(qapp: QApplication, qtbot) -> None:
    """Two height probes at the same width must measure the QTextDocument once."""
    body = MarkdownContent("**Hello** world\n\n" + "tail line\n" * 8)
    qtbot.addWidget(body)
    body.resize(280, 40)
    body.show()
    qtbot.waitExposed(body)
    body._invalidate_measured_height()
    with patch.object(
        body,
        "_measure_height_for_text_width",
        wraps=body._measure_height_for_text_width,
    ) as spy:
        first = body.heightForWidth(280)
        second = body.heightForWidth(280)
        qapp.processEvents()
    assert first == second
    assert spy.call_count == 1


def test_wrapping_label_height_cache_reuses_single_bounding_rect(qapp: QApplication, qtbot) -> None:
    """A second height probe at the same width must not remeasure wrapped text."""
    label = _WrappingLabel("Wrapped user prompt " * 12)
    qtbot.addWidget(label)
    label.resize(240, 20)
    label.show()
    qtbot.waitExposed(label)
    label._invalidate_measured_height()
    measure_calls: list[int] = []
    original_measure = label._measure_wrapped_height

    def counting_measure(text_width: int) -> int:
        if label._measured_text_width == text_width and label._measured_height is not None:
            return label._measured_height
        measure_calls.append(1)
        return original_measure(text_width)

    label._measure_wrapped_height = counting_measure  # type: ignore[method-assign]
    first = label.heightForWidth(240)
    second = label.heightForWidth(240)
    qapp.processEvents()
    assert first == second
    assert len(measure_calls) == 1


def test_sticky_sync_deferred_until_resize_settles(qapp: QApplication, qtbot) -> None:
    """Rapid resize defers sticky sync; one pass runs after the settle timer."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    panel.add_message("user", "question")
    panel.add_message("assistant", "answer\n" * 20)
    qapp.processEvents()
    sync_calls: list[int] = []
    original = panel._sync_sticky_turn_prompt

    def counting_sync() -> None:
        sync_calls.append(1)
        original()

    panel._sync_sticky_turn_prompt = counting_sync  # type: ignore[method-assign]
    panel.resize(400, 280)
    panel.resize(420, 280)
    panel.resize(440, 280)
    qapp.processEvents()
    assert len(sync_calls) == 0
    qtbot.wait(_RESIZE_SETTLE_MS + 30)
    qapp.processEvents()
    assert len(sync_calls) == 1


def test_sticky_extents_still_invalidate_on_visible_resize(qapp: QApplication, qtbot) -> None:
    """Visible resize still marks sticky extents dirty (reconcile streaming test)."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    panel.add_message("user", "question")
    panel.add_message("assistant", "answer line\n" * 30)
    qapp.processEvents()
    panel._ensure_sticky_turn_extents()
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


def test_transcript_rows_skip_document_layout_during_active_resize(
    qapp: QApplication, qtbot
) -> None:
    """Historical rows skip QTextDocument layout while the pane width is changing."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 140)
    panel.load_transcript(_long_transcript_messages(80))
    qapp.processEvents()
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    qapp.processEvents()
    bodies = _assistant_bodies(panel)
    assert len(bodies) >= 10
    measure_counts: dict[int, int] = {}

    def make_counter(
        body: MarkdownContent,
        original: Callable[[int], float],
    ) -> Callable[[int], float]:
        def _wrapped(text_width: int) -> float:
            measure_counts[id(body)] = measure_counts.get(id(body), 0) + 1
            return original(text_width)

        return _wrapped

    with contextlib.ExitStack() as stack:
        for body in bodies:
            stack.enter_context(
                patch.object(
                    body,
                    "_measure_height_for_text_width",
                    make_counter(body, body._measure_height_for_text_width),
                )
            )
        panel._prepare_panel_resize_coalescing()
        panel.resize(350, 140)
        qapp.processEvents()
        for width in range(352, 380, 8):
            panel._prepare_panel_resize_coalescing()
            panel.resize(width, 140)
            qapp.processEvents()
    assert measure_counts == {}


def test_resize_settle_flushes_all_deferred_rows(qapp: QApplication, qtbot) -> None:
    """After resize settles, every deferred row is flushed and remeasured."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 140)
    panel.load_transcript(_long_transcript_messages(24))
    qapp.processEvents()
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    qapp.processEvents()

    panel._prepare_panel_resize_coalescing()
    panel.resize(350, 140)
    qapp.processEvents()
    bodies = _assistant_bodies(panel)
    assert panel._resize_active is True

    panel._on_resize_settled()
    qapp.processEvents()
    assert panel._resize_active is False
    assert all(not body._reflow_flush_pending for body in bodies)


def test_messages_layout_keeps_min_and_max_size_constraint(qapp: QApplication, qtbot) -> None:
    """SetMinAndMaxSize is required for reliable transcript scroll range."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    assert panel._messages_layout.sizeConstraint() == QLayout.SizeConstraint.SetMinAndMaxSize


def test_streaming_bubble_reflows_during_active_resize(qapp: QApplication, qtbot) -> None:
    """The active streaming assistant row keeps height sync while resize is coalesced."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 280)
    panel.add_message("user", "question")
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "streaming line\n" * 6)
    qtbot.wait(60)
    qapp.processEvents()
    bubble = panel._streaming_bubble
    assert bubble is not None
    body = bubble._markdown_body
    assert body is not None
    sync_calls: list[int] = []
    original_sync = body._sync_height

    def counting_sync(*args: object) -> None:
        sync_calls.append(1)
        original_sync(*args)

    panel._mark_resize_active()
    with patch.object(body, "_sync_height", side_effect=counting_sync):
        panel.resize(400, 280)
        qapp.processEvents()
    assert body._reflow_deferred is False
    assert len(sync_calls) >= 1
