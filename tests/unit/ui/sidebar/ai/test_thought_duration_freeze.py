"""Unit tests for thought-section duration freezing."""

from __future__ import annotations

from ui.sidebar.ai.message_bubble.thought_section import ThoughtSection


def test_finalize_thinking_preserves_first_duration(qapp) -> None:
    """Re-finalizing must not extend duration after subagent wait or turn end."""
    section = ThoughtSection()
    section.append_text("initial reasoning")
    section.finalize_thinking(collapse=False)
    first = section.duration_seconds()
    assert first is not None
    assert not section._timer.isValid()

    section._timer.start()
    section.finalize_thinking(collapse=False)
    assert section.duration_seconds() == first


def test_set_parts_finalize_does_not_extend_duration(qapp) -> None:
    """Turn-end set_parts must not overwrite an earlier frozen duration."""
    from ui.sidebar.ai.message_bubble import ChatMessageBubble

    bubble = ChatMessageBubble("assistant", "")
    bubble.append_thinking("pre-delegation plan")
    primary = bubble._thought_section
    assert primary is not None
    primary.finalize_thinking(collapse=True)
    frozen = primary.duration_seconds()
    assert frozen is not None

    bubble.set_parts(
        thinking="pre-delegation plan\nextra lines from stream",
        content="final answer",
    )
    assert primary.duration_seconds() == frozen
