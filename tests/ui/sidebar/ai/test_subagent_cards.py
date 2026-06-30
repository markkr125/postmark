"""UI tests for Cursor-style subagent cards in assistant bubbles."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from services.ai.chat.subagent_events import SubagentRunRecord
from ui.sidebar.ai.message_bubble import ChatMessageBubble


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


def test_subagent_completed_card_shows_status(qapp: QApplication, qtbot) -> None:
    """Completed cards show status without an inline expandable body."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show()
    record: SubagentRunRecord = {
        "id": "task_2",
        "kind": "wiki",
        "label": "how to send request",
        "subagent_type": "wiki-researcher",
        "status": "completed",
        "task_prompt": "how to send request with variables",
        "result_preview": "Open the Collections sidebar.",
    }
    bubble.upsert_subagent_record(record)
    group = bubble._subagent_group
    assert group is not None
    card = group.cards()[0]
    status_labels = card.findChildren(QLabel, "aiChatSubagentStatusLabel")
    assert status_labels
    assert status_labels[0].text() == "Completed"


def test_subagent_card_click_emits_record_id(qapp: QApplication, qtbot) -> None:
    """Running cards emit clicked with their record id."""
    from ui.sidebar.ai.message_bubble.subagent.card import SubagentTaskCard

    card = SubagentTaskCard()
    qtbot.addWidget(card)
    card.show()
    seen: list[str] = []
    card.clicked.connect(seen.append)
    card.apply_record(
        {
            "id": "py",
            "kind": "delegate",
            "label": "Find Python scripting docs",
            "subagent_type": "wiki-researcher",
            "status": "running",
            "task_prompt": "Find Python scripting docs",
        }
    )
    qtbot.mouseClick(card, Qt.MouseButton.LeftButton)
    assert seen == ["py"]


def test_subagent_card_entire_surface_clickable(qapp: QApplication, qtbot) -> None:
    """Clicks on nested labels route to the card and open the detail dialog."""
    from PySide6.QtWidgets import QLabel

    from ui.sidebar.ai.message_bubble.subagent.card import SubagentTaskCard

    card = SubagentTaskCard()
    qtbot.addWidget(card)
    card.resize(420, 120)
    card.show()
    seen: list[str] = []
    card.clicked.connect(seen.append)
    card.apply_record(
        {
            "id": "py",
            "kind": "delegate",
            "label": "Find Python scripting docs",
            "subagent_type": "wiki-researcher",
            "status": "completed",
            "task_prompt": "Find Python scripting docs",
        }
    )
    status = card.findChild(QLabel, "aiChatSubagentStatusLabel")
    assert status is not None
    click_pos = status.geometry().center()
    click_pos = status.mapTo(card, click_pos)
    qtbot.mouseClick(card, Qt.MouseButton.LeftButton, pos=click_pos)
    assert seen == ["py"]


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
        "task_prompt": "Search for TypeScript scripting documentation in Postmark wiki",
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


def test_frozen_primary_thought_stays_collapsed_during_subagent_run(
    qapp: QApplication, qtbot
) -> None:
    """Continued thinking while subagents run must not re-open the frozen primary block."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show()
    bubble.append_thinking("Planning parallel wiki lookups.")
    primary = bubble._thought_section
    assert primary is not None
    assert primary.is_expanded()

    bubble.upsert_subagent_record(
        {
            "id": "ts",
            "kind": "delegate",
            "label": "Find TypeScript scripting docs",
            "subagent_type": "wiki-researcher",
            "status": "running",
        }
    )
    assert primary.duration_seconds() is not None
    assert not primary.is_expanded()
    assert not bubble._subagents_all_complete

    bubble.append_thinking(" continued deliberation while subagents are still running")
    assert not primary.is_expanded(), "frozen primary thought re-opened on continued thinking"
    assert primary.duration_seconds() is not None


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
            "task_prompt": "Find TypeScript scripting docs",
        },
        {
            "id": "py",
            "kind": "delegate",
            "label": "Find Python scripting docs",
            "subagent_type": "wiki-researcher",
            "status": "running",
            "task_prompt": "Find Python scripting docs",
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


def test_panel_card_click_opens_detail_dialog(qapp: QApplication, qtbot) -> None:
    """Clicking a subagent card opens the non-modal detail window."""
    from ui.sidebar.ai import AiChatPanel

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.begin_assistant_stream()
    record: SubagentRunRecord = {
        "id": "ts",
        "kind": "delegate",
        "label": "Find TypeScript scripting docs",
        "subagent_type": "wiki-researcher",
        "status": "completed",
        "task_prompt": "Find TypeScript scripting docs in the Postmark wiki",
        "result_preview": "## TypeScript\n\nSee quickref.",
    }
    panel.deliver_subagent_update([record])
    bubble = panel._streaming_bubble
    assert bubble is not None
    group = bubble._subagent_group
    assert group is not None
    card = group.cards()[0]
    qtbot.mouseClick(card, Qt.MouseButton.LeftButton)
    dialog = panel._subagent_detail_dialog
    assert dialog is not None
    assert dialog.isVisible()
    assert dialog.record_id() == "ts"
    assert "Find TypeScript scripting docs in the Postmark wiki" in dialog._task.text()
