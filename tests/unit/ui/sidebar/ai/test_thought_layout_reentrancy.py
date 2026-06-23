"""Regression tests for thought-block layout reentrancy and wrap width."""

from __future__ import annotations

import sys
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QLayout, QPushButton, QVBoxLayout, QWidget

from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent
from ui.sidebar.ai.message_bubble.wrapping_label import _WrappingLabel


def _long_thinking() -> str:
    """Return thinking text with long unbroken segments."""
    return (
        "We need to search the knowledge base for UI workflows "
        "(collections, requests, environments, etc.) and use postmark_wiki_query. "
    ) * 10


def test_wrapping_label_height_for_width_is_reentrant(qapp: QApplication, qtbot) -> None:
    """Nested layout queries must not recurse through ``heightForWidth``."""
    label = _WrappingLabel(_long_thinking())
    qtbot.addWidget(label)
    label.resize(280, 20)
    label.show()
    qtbot.waitExposed(label)

    def parent_triggers_remeasure() -> QWidget | None:
        label.heightForWidth(280)
        return None

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(80)
    try:
        with patch.object(label, "parentWidget", side_effect=parent_triggers_remeasure):
            height = label.heightForWidth(280)
    finally:
        sys.setrecursionlimit(old_limit)

    assert height > label.fontMetrics().lineSpacing()


def test_markdown_height_for_width_is_reentrant(qapp: QApplication, qtbot) -> None:
    """Markdown bodies must survive nested ``heightForWidth`` probes."""
    body = MarkdownContent("Answer paragraph.\n\n" + "tail line\n" * 12)
    qtbot.addWidget(body)
    body.resize(280, 40)
    body.show()
    qtbot.waitExposed(body)

    def parent_triggers_remeasure() -> QWidget | None:
        body.heightForWidth(280)
        return None

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(80)
    try:
        with patch.object(body, "parentWidget", side_effect=parent_triggers_remeasure):
            height = body.heightForWidth(280)
    finally:
        sys.setrecursionlimit(old_limit)

    assert height > 20


def test_thought_expand_shows_full_wrapped_height(qapp: QApplication, qtbot) -> None:
    """Expanding a collapsed thought row must not clip the wrapped body."""
    thinking = (
        "Search.User asks about collections. We need to instruct them how to search. "
        "To find, open Collections panel, type search request and DiagnosticCollection. Provide steps."
    ) * 6
    host = QWidget()
    layout = QVBoxLayout(host)
    bubble = ChatMessageBubble(
        "assistant",
        "## Finding Collections\n\nSteps here.",
        thinking=thinking,
        thinking_duration_seconds=17,
    )
    layout.addWidget(bubble)
    qtbot.addWidget(host)
    host.resize(360, 800)
    host.show()
    qtbot.waitExposed(host)

    toggle = bubble.findChild(QPushButton, "aiChatThoughtToggle")
    assert toggle is not None
    toggle.click()
    qapp.processEvents()

    section = bubble._thought_section
    assert section is not None
    label = section._label
    assert label.isVisible()
    assert label.height() >= label.heightForWidth(label.width()) - 2
    assert label.text().rstrip().endswith("Provide steps.")


def test_thought_toggle_during_viewport_clamp_does_not_recurse(
    qapp: QApplication,
    qtbot,
) -> None:
    """Expanding thought while clamping transcript width must stay layout-safe."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 420)
    panel.add_message("user", "can you find collections named request?")
    bubble = panel.add_message(
        "assistant",
        "answer line\n" * 8,
        thinking=_long_thinking(),
        thinking_duration_seconds=6,
    )
    qapp.processEvents()

    panel._arm_scroll_lock()
    panel._turn_scroll_anchor = panel._find_last_turn_user_bubble()
    viewport_h = panel._scroll.viewport().height()
    panel._messages_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
    panel._messages.setFixedHeight(viewport_h)

    toggle = bubble.findChild(QPushButton, "aiChatThoughtToggle")
    assert toggle is not None

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(120)
    try:
        panel._clamp_messages_to_viewport_width()
        qapp.processEvents()
        toggle.click()
        for _ in range(12):
            qapp.processEvents()
        panel._on_transcript_bubble_layout_changed()
        qapp.processEvents()
        toggle.click()
        for _ in range(12):
            qapp.processEvents()
    finally:
        sys.setrecursionlimit(old_limit)

    thought_section = bubble._thought_section
    assert thought_section is not None
    label = thought_section._label
    assert label.width() <= panel._messages.width()
