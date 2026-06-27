"""E2E regression: the thinking block must not flicker/bounce during streaming.

The bug: while thinking text streams in, the collapsible "Thought for Ns" block
oscillates — its measured wrapped height shrinks then grows on alternating layout
passes, making the block visibly jump up and down. Scroll-follow (locking to the
bottom) is expected and correct; this test only guards against the height
oscillation and the resulting up-then-down viewport jitter.
"""

from __future__ import annotations

import itertools

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QWidget

from ui.sidebar.ai import AiChatPanel


def _flush_stream_chunks(qtbot) -> None:
    """Wait for coalesced chunk delivery (~50ms)."""
    qtbot.wait(60)
    QApplication.processEvents()


def _drain_follow_passes(qtbot, qapp: QApplication) -> None:
    """Wait for deferred stream-follow timer passes."""
    qtbot.wait(20)
    qapp.processEvents()


def _viewport_top(panel: AiChatPanel, widget: QWidget) -> int:
    """Return *widget* top Y in scroll viewport coordinates."""
    bar = panel._scroll.verticalScrollBar()
    return int(widget.mapTo(panel._messages, QPoint(0, 0)).y() - bar.value())


def _stream_thinking(
    panel: AiChatPanel,
    qtbot,
    qapp: QApplication,
    *,
    chunk: str,
    count: int,
) -> list[tuple[int, int, int]]:
    """Stream *count* thinking-only chunks; return (vp_top, section_h, label_h) per step."""
    assistant = panel._streaming_bubble
    assert assistant is not None
    thought = assistant._thought_section
    assert thought is not None

    samples: list[tuple[int, int, int]] = []
    for index in range(count):
        delta = chunk if index % 3 else chunk[: 6 + (index % 11)]
        panel.append_assistant_chunk(delta, "")
        _flush_stream_chunks(qtbot)
        _drain_follow_passes(qtbot, qapp)
        qapp.processEvents()
        qapp.processEvents()
        samples.append(
            (
                _viewport_top(panel, thought),
                thought.height(),
                thought._label.height(),
            )
        )
    return samples


def _assert_label_height_monotonic(label_heights: list[int]) -> None:
    """Thought label height must never shrink during a thinking-only stream."""
    assert label_heights[-1] > label_heights[0], "expected thought label to grow during stream"
    for index, (prev, nxt) in enumerate(itertools.pairwise(label_heights)):
        assert nxt >= prev - 1, (
            f"thought label shrank at step {index}: {prev}px -> {nxt}px (heights={label_heights})"
        )


def _assert_section_height_monotonic(section_heights: list[int]) -> None:
    """Thought section frame height must never shrink during a thinking-only stream."""
    for index, (prev, nxt) in enumerate(itertools.pairwise(section_heights)):
        assert nxt >= prev - 1, f"thought section shrank at step {index}: {prev}px -> {nxt}px"


def _assert_no_viewport_oscillation(viewport_tops: list[int], *, threshold_px: int = 6) -> None:
    """Fail when the block viewport top jitters up-then-down (bounce)."""
    for index in range(len(viewport_tops) - 2):
        first = viewport_tops[index + 1] - viewport_tops[index]
        second = viewport_tops[index + 2] - viewport_tops[index + 1]
        if first * second < 0 and abs(first) > threshold_px and abs(second) > threshold_px:
            window = viewport_tops[index : index + 3]
            raise AssertionError(
                f"thought viewport oscillated at steps {index}->{index + 2}: "
                f"{first:+d}px then {second:+d}px (tops={window})"
            )


def test_thought_block_no_bounce_during_long_thinking_at_bottom(
    qapp: QApplication,
    qtbot,
) -> None:
    """Long thinking-only stream, scroll locked at bottom: block grows without bouncing."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(493, 640)

    for index in range(10):
        panel.add_message("user", f"prior turn {index}: " + "context " * 12)
        panel.add_message("assistant", f"answer {index}")
    panel.add_message("user", "Compare TypeScript and Python scripting APIs in Postmark.")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()

    panel._scroll_lock_enabled = True
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    qapp.processEvents()
    assert not panel._stream_content_started

    chunk = "Search the wiki for TypeScript and Python scripting documentation and summarize. "
    samples = _stream_thinking(panel, qtbot, qapp, chunk=chunk, count=48)

    viewport_tops = [sample[0] for sample in samples]
    section_heights = [sample[1] for sample in samples]
    label_heights = [sample[2] for sample in samples]

    _assert_label_height_monotonic(label_heights)
    _assert_section_height_monotonic(section_heights)
    _assert_no_viewport_oscillation(viewport_tops)


def test_thought_block_no_bounce_first_turn(qapp: QApplication, qtbot) -> None:
    """First-turn thinking-only stream must grow the block monotonically (no flicker)."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 480)
    panel.add_message("user", "Explain scripting in this app with an example")
    panel.begin_assistant_stream()
    qapp.processEvents()
    qapp.processEvents()
    panel._scroll_lock_enabled = True

    chunk = "We need to explain how scripts work in Postmark including variables and examples. "
    samples = _stream_thinking(panel, qtbot, qapp, chunk=chunk, count=32)

    label_heights = [sample[2] for sample in samples]
    section_heights = [sample[1] for sample in samples]
    _assert_label_height_monotonic(label_heights)
    _assert_section_height_monotonic(section_heights)

    assistant = panel._streaming_bubble
    assert assistant is not None
    thought = assistant._thought_section
    assert thought is not None
    label = thought._label
    width = max(thought.width(), label.width(), 1)
    needed = label._measure_wrapped_height(label._text_width_for_widget_width(width))
    assert label.height() >= needed - 4
