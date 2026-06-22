"""UI tests for research activity popup."""

from __future__ import annotations

from ui.sidebar.ai.research_activity_popup import AiResearchActivityPopup


def test_research_popup_shows_findings(qapp) -> None:
    """Popup displays progress lines and findings text."""
    popup = AiResearchActivityPopup()
    popup.set_progress_lines(["Researching workspace…"])
    popup.set_findings_text("## Matches\n- [request] GET Users (id=1)")
    assert "Researching" in popup._progress.toPlainText()
    assert "Matches" in popup._findings.toPlainText()
