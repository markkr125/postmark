"""UI tests for main-agent tool activity cards."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.tool_activity.card import ToolActivityCard


def test_tool_activity_cards_render_and_hide_running_on_complete(
    qapp: QApplication,
    qtbot,
) -> None:
    """Running tool cards appear, then leave the layout when completed."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.set_tool_activity_records(
        [
            {
                "id": "tc-1",
                "tool_name": "postmark_workspace_query",
                "title": "Query workspace",
                "detail": "overview",
                "status": "running",
            }
        ]
    )
    cards = bubble.findChildren(ToolActivityCard)
    assert len(cards) == 1
    assert cards[0].status() == "running"

    bubble.set_tool_activity_records(
        [
            {
                "id": "tc-1",
                "tool_name": "postmark_workspace_query",
                "title": "Query workspace",
                "detail": "overview",
                "status": "completed",
            }
        ]
    )
    cards = bubble.findChildren(ToolActivityCard)
    assert len(cards) == 1
    assert cards[0].status() == "completed"

    bubble.set_tool_activity_records([])
    assert bubble._tool_activity_records == {}
    qtbot.wait(10)
    assert bubble.findChildren(ToolActivityCard) == []


def test_execute_handoff_removes_matching_tool_activity_card(
    qapp: QApplication,
    qtbot,
) -> None:
    """Execute result upsert clears the in-flight execute tool activity row."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.set_tool_activity_records(
        [
            {
                "id": "exec-1",
                "tool_name": "postmark_workspace_execute",
                "title": "Send request",
                "detail": "GET https://example.com",
                "status": "running",
            }
        ]
    )
    assert len(bubble.findChildren(ToolActivityCard)) == 1
    bubble.upsert_execute_record(
        {
            "id": "exec-1",
            "operation": "send_request",
            "label": "GET https://example.com -> 200",
            "status": "completed",
            "status_code": 200,
            "url": "https://example.com",
            "history_entry_id": 42,
            "request_id": 7,
            "local_script_id": None,
            "collection_id": None,
            "script_phase": None,
        }
    )
    assert bubble._tool_activity_records == {}
    qtbot.wait(10)
    assert bubble.findChildren(ToolActivityCard) == []
