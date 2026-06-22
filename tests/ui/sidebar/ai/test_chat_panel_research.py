"""Integration tests for workspace research flyout on AiChatPanel."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.research_activity_popup import AiResearchActivityPopup


def test_update_research_state_shows_findings_and_footer(qapp, qtbot) -> None:
    """Research JSON payload updates flyout text and shows the footer chip."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()

    payload = json.dumps(
        {
            "phase": "findings",
            "status": "",
            "findings": "## Matches\n- [request] GET Users",
        }
    )
    panel.update_research_state(payload)

    popup = panel._ensure_research_popup()
    assert "Matches" in popup._findings.toPlainText()

    bubble = panel._streaming_bubble
    assert bubble is not None
    footer = bubble.assistant_footer_widget()
    assert footer is not None
    assert footer.is_research_visible()


def test_research_toggle_shows_popup(qapp, qtbot) -> None:
    """Clicking the activity-row Research chip toggles the flyout."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    panel.update_research_state(
        json.dumps({"phase": "status", "status": "Researching workspace…", "findings": ""})
    )

    bubble = panel._streaming_bubble
    assert bubble is not None
    activity = bubble.activity_row_widget()
    assert activity is not None
    chip = activity.findChild(QPushButton, "aiChatResearchChip")
    assert chip is not None
    activity.set_research_chip_visible(True)
    activity.hide_activity()

    qtbot.mouseClick(chip, Qt.MouseButton.LeftButton)
    popup = panel.findChild(AiResearchActivityPopup)
    assert popup is not None
    assert popup.isVisible()


def test_research_grace_hides_activity_keeps_footer(qapp, qtbot) -> None:
    """After findings, activity hides after grace while footer chip stays."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    panel.update_research_state(
        json.dumps(
            {
                "phase": "findings",
                "status": "Searching workspace…",
                "findings": "done",
            }
        )
    )

    bubble = panel._streaming_bubble
    assert bubble is not None
    assert bubble.is_activity_visible()

    qtbot.wait(2100)

    assert not bubble.is_activity_visible()
    footer = bubble.assistant_footer_widget()
    assert footer is not None
    assert footer.is_research_visible()


def test_stopped_phase_hides_research_activity(qapp, qtbot) -> None:
    """Stopped research payload hides the activity row."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    panel.update_research_state(
        json.dumps({"phase": "status", "status": "Researching workspace…", "findings": ""})
    )
    panel.update_research_state(json.dumps({"phase": "stopped", "status": "", "findings": ""}))

    bubble = panel._streaming_bubble
    assert bubble is not None
    assert not bubble.is_activity_visible()
