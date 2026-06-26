"""UI tests for Cursor-style subagent cards in assistant bubbles."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from services.ai.chat.subagent_events import SubagentRunRecord
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.subagent.body import SubagentCardBody


def test_subagent_card_running_shows_inline_loader(qapp: QApplication, qtbot) -> None:
    """Running subagent cards replace the generic activity row."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show()
    bubble.show_activity("Thinking…")
    record: SubagentRunRecord = {
        "id": "task_1",
        "kind": "task",
        "label": "Explore OpenHands AI integration",
        "subagent_type": "wiki-researcher",
        "status": "running",
        "steps": [{"id": "run", "icon": "circle-notch", "summary": "Working…"}],
    }
    bubble.upsert_subagent_record(record)
    assert bubble.subagent_active_count() == 1
    assert not bubble.is_activity_visible()
    assert bubble._subagent_group is not None
    card = bubble._subagent_group.cards()[0]
    assert card.isVisible()


def test_subagent_completed_card_shows_status_and_steps(qapp: QApplication, qtbot) -> None:
    """Completed cards show Cursor-style status and output blocks."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show()
    record: SubagentRunRecord = {
        "id": "task_2",
        "kind": "wiki",
        "label": "how to send request",
        "subagent_type": "wiki-researcher",
        "status": "completed",
        "result_preview": "Open the Collections sidebar.",
        "steps": [
            {
                "id": "search",
                "icon": "magnifying-glass",
                "summary": "how to send request",
            },
            {
                "id": "result",
                "icon": "article",
                "summary": "Read tool output",
                "detail": "Open the Collections sidebar.",
            },
        ],
    }
    bubble.upsert_subagent_record(record)
    group = bubble._subagent_group
    assert group is not None
    card = group.cards()[0]
    status_labels = card.findChildren(QLabel, "aiChatSubagentStatusLabel")
    assert status_labels
    assert status_labels[0].text() == "Completed"
    bodies = card.findChildren(SubagentCardBody)
    assert bodies
    assert bodies[0].has_steps()


def test_subagent_warming_not_clickable(qapp: QApplication, qtbot) -> None:
    """Warming cards use arrow cursor until active."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show()
    record: SubagentRunRecord = {
        "id": "delegate_a",
        "kind": "delegate",
        "label": "delegate_a",
        "subagent_type": "general-purpose",
        "status": "warming",
    }
    bubble.upsert_subagent_record(record)
    assert bubble._subagent_group is not None
    card = bubble._subagent_group.cards()[0]
    assert card.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_subagent_long_title_header_is_tall_enough(qapp: QApplication, qtbot) -> None:
    """Wrapped subagent titles must not clip inside the header row."""
    from ui.sidebar.ai.message_bubble.subagent.card import SubagentTaskCard

    card = SubagentTaskCard()
    qtbot.addWidget(card)
    card.resize(420, 400)
    card.show()
    record: SubagentRunRecord = {
        "id": "ts",
        "kind": "delegate",
        "label": "Search for TypeScript scripting documentation in Postmark wiki",
        "subagent_type": "wiki-researcher",
        "status": "completed",
        "steps": [{"id": "done", "summary": "Read tool output", "detail": "done"}],
    }
    card.apply_record(record)
    qtbot.wait(10)
    labels = card.findChildren(QLabel, "aiChatSubagentLabel")
    assert labels
    label = labels[0]
    line_h = label.fontMetrics().height()
    assert label.height() >= line_h
    assert card._header.minimumHeight() >= line_h


def test_primary_thought_frozen_when_subagent_card_appears(qapp: QApplication, qtbot) -> None:
    """Pre-delegation thought duration must not include subagent execution wait."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show()
    bubble.append_thinking("Planning parallel wiki lookups.")
    primary = bubble._thought_section
    assert primary is not None
    primary.finalize_thinking(collapse=True)
    frozen = primary.duration_seconds()
    assert frozen is not None

    bubble.upsert_subagent_record(
        {
            "id": "ts",
            "kind": "delegate",
            "label": "Find TypeScript scripting docs",
            "subagent_type": "wiki-researcher",
            "status": "completed",
        }
    )
    assert primary.duration_seconds() == frozen
    bubble.set_parts(
        thinking="Planning parallel wiki lookups.\nstream tail",
        content="Comparison table",
    )
    assert primary.duration_seconds() == frozen


def test_post_subagent_thinking_uses_new_block_below_cards(qapp: QApplication, qtbot) -> None:
    """After subagents complete, synthesis thinking goes in a new block under the cards."""
    bubble = ChatMessageBubble("assistant", "", thinking="Early planning only.")
    qtbot.addWidget(bubble)
    bubble.show()
    bubble.upsert_subagent_record(
        {
            "id": "ts",
            "kind": "delegate",
            "label": "TypeScript docs",
            "subagent_type": "wiki-researcher",
            "status": "running",
        }
    )
    bubble.upsert_subagent_record(
        {
            "id": "py",
            "kind": "delegate",
            "label": "Python docs",
            "subagent_type": "wiki-researcher",
            "status": "completed",
        }
    )
    bubble.upsert_subagent_record(
        {
            "id": "ts",
            "kind": "delegate",
            "label": "TypeScript docs",
            "subagent_type": "wiki-researcher",
            "status": "completed",
        }
    )
    assert bubble._subagents_all_complete
    primary = bubble._thought_section
    assert primary is not None
    bubble.append_thinking("Synthesizing comparison from subagent results.")
    post = bubble._post_subagent_thought_section
    assert post is not None
    assert "Early planning only." in primary.text()
    assert "Synthesizing" in post.text()
    assert "Synthesizing" not in primary.text()
    outer = bubble._assistant_outer
    assert outer is not None
    assert outer.indexOf(bubble._subagent_group) < outer.indexOf(post)  # type: ignore[arg-type]
    assert outer.indexOf(post) < outer.indexOf(bubble._markdown_body)  # type: ignore[arg-type]


def test_panel_shows_subagent_cards_on_deliver(qapp: QApplication, qtbot) -> None:
    """Full path: streaming bubble + deliver_subagent_update renders visible cards."""
    from ui.sidebar.ai import AiChatPanel

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.begin_assistant_stream()
    records: list[SubagentRunRecord] = [
        {
            "id": "ts",
            "kind": "delegate",
            "label": "Find TypeScript scripting docs",
            "subagent_type": "wiki-researcher",
            "status": "running",
        },
        {
            "id": "py",
            "kind": "delegate",
            "label": "Find Python scripting docs",
            "subagent_type": "wiki-researcher",
            "status": "running",
        },
    ]
    panel.deliver_subagent_update(records)
    qtbot.wait(10)
    bubble = panel._streaming_bubble
    assert bubble is not None
    assert bubble.subagent_active_count() == 2
    group = bubble._subagent_group
    assert group is not None and group.isVisible()
    assert len(group.cards()) == 2
    assert all(card.isVisible() for card in group.cards())
