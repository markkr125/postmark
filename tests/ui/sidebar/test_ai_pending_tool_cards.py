"""UI tests for inline pending-tool Approve cards."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from ui.sidebar.ai.chat_panel.panel import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.confirm.card import PendingToolCard
from ui.sidebar.ai.message_bubble.confirm.group import PendingToolGroup
from ui.widgets.busy_spinner import BrailleSpinner


def test_pending_card_emits_approve_and_reject(qapp: QApplication, qtbot) -> None:
    """Allow / Reject on a single pending card emit bubble signals."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    payload = {
        "actions": [
            {
                "tool_name": "postmark_workspace_mutate",
                "kind": "mutate:create:collection",
                "title": "Create collection",
                "detail": "Payments API",
                "risk": "normal",
            }
        ]
    }
    bubble.show_pending_confirmation(payload)
    assert bubble.has_pending_confirmation()
    cards = bubble.findChildren(PendingToolCard)
    assert len(cards) == 1
    title = bubble.findChild(QLabel, "aiChatPendingToolTitle")
    detail = bubble.findChild(QLabel, "aiChatPendingToolDetail")
    assert title is not None and title.text() == "Create collection"
    assert detail is not None and detail.text() == "Payments API"

    approved: list[bool] = []
    rejected: list[bool] = []
    bubble.confirmation_approve_requested.connect(lambda: approved.append(True))
    bubble.confirmation_reject_requested.connect(lambda: rejected.append(True))

    allow = bubble.findChild(QPushButton, "aiChatPendingAllow")
    reject = bubble.findChild(QPushButton, "aiChatPendingReject")
    spinner = bubble.findChild(BrailleSpinner, "busyChipSpinner")
    assert allow is not None and reject is not None and spinner is not None
    initial_frame = spinner.frame_index()
    allow.click()
    reject.click()
    assert approved == [True]
    assert rejected == []
    assert detail.text().endswith(" — Starting…")
    assert not allow.isEnabled()
    assert not reject.isEnabled()
    assert not spinner.isHidden()
    qtbot.wait(120)
    assert spinner.frame_index() != initial_frame


def test_pending_always_allow_adds_rule(qapp: QApplication, qtbot, monkeypatch) -> None:
    """Always allow persists the kind then Approves."""
    added: list[str] = []
    monkeypatch.setattr(
        "ui.sidebar.ai.message_bubble.confirm.group.add_rule",
        lambda kind: added.append(kind),
    )

    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show_pending_confirmation(
        {
            "actions": [
                {
                    "kind": "mutate:create:collection",
                    "title": "Create collection",
                    "detail": "Payments API",
                }
            ]
        }
    )
    approved: list[bool] = []
    bubble.confirmation_approve_requested.connect(lambda: approved.append(True))
    always = bubble.findChild(QPushButton, "aiChatPendingAlwaysAllow")
    assert always is not None
    always.click()
    assert added == ["mutate:create:collection"]
    assert approved == [True]


def test_panel_show_confirmation_hosts_cards_on_bubble(qapp: QApplication, qtbot) -> None:
    """Panel show_confirmation mounts cards on the streaming bubble, not composer."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show_confirmation(
        {
            "actions": [
                {
                    "kind": "execute:send_request",
                    "title": "Send request",
                    "detail": "GET https://example.com/health",
                    "url": "https://example.com/health",
                }
            ]
        }
    )
    bubble = panel._streaming_bubble
    assert bubble is not None
    assert bubble.has_pending_confirmation()
    groups = bubble.findChildren(PendingToolGroup)
    assert len(groups) == 1
    assert panel.findChild(QLabel, "aiChatConfirmationBanner") is None
    panel.clear_confirmation()
    assert not bubble.has_pending_confirmation()


def test_pending_hides_activity_row(qapp: QApplication, qtbot) -> None:
    """Pending cards suppress the generic Waiting activity row."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show_activity("Waiting for approval…")
    assert bubble.is_activity_visible()
    bubble.show_pending_confirmation(
        {
            "actions": [
                {
                    "kind": "mutate:create:request",
                    "title": "Create request",
                    "detail": "Health",
                }
            ]
        }
    )
    assert not bubble.is_activity_visible()
    bubble.show_activity("Waiting for approval…")
    assert not bubble.is_activity_visible()


def test_confirmation_flushes_buffered_thinking_before_closing_phase(
    qapp: QApplication,
    qtbot,
) -> None:
    """Coalesced pre-tool thinking stays above approval instead of crossing its boundary."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("Buffered plan before tool.", "")
    panel.show_confirmation(
        {
            "actions": [
                {
                    "tool_call_id": "tool-buffered",
                    "title": "Create request",
                    "detail": "Health",
                }
            ]
        }
    )
    bubble = panel._streaming_bubble
    assert bubble is not None
    primary = bubble._thought_section
    assert primary is not None
    assert primary.text() == "Buffered plan before tool."
    assert primary.duration_seconds() is not None
    assert len(bubble._thought_sections) == 1
