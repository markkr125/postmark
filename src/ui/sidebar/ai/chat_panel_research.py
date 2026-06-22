"""Workspace research flyout orchestration for :class:`AiChatPanel`."""

from __future__ import annotations

import json
from typing import Any, cast

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from ui.sidebar.ai.research_activity_popup import AiResearchActivityPopup

_RESEARCH_GRACE_MS = 2000


class _ChatPanelResearchMixin:
    """Research progress flyout, activity-row toggle, and footer chip."""

    _research_popup: AiResearchActivityPopup
    _research_progress_lines: list[str]
    _research_grace_timer: QTimer | None
    _research_findings_text: str

    def _init_research_state(self) -> None:
        """Reset per-turn research UI state (call from ``begin_assistant_stream``)."""
        self._research_progress_lines = []
        self._research_findings_text = ""
        self._research_grace_timer = None
        if hasattr(self, "_research_popup"):
            self._research_popup.hide()

    def _ensure_research_popup(self) -> AiResearchActivityPopup:
        """Lazily create the research flyout parented to the panel."""
        if not hasattr(self, "_research_popup"):
            self._research_popup = AiResearchActivityPopup(cast(QWidget, self))
        return self._research_popup

    def _research_anchor_widget(self) -> QWidget | None:
        """Return the widget to anchor the research flyout (activity row or footer)."""
        host = cast(Any, self)
        bubble = host._resolve_streaming_bubble()
        if bubble is None:
            return None
        if bubble.is_activity_visible():
            row = bubble.activity_row_widget()
            return cast(QWidget | None, row)
        footer = bubble.assistant_footer_widget()
        if footer is not None and footer.is_research_visible():
            return cast(QWidget | None, footer.research_button())
        return cast(QWidget, bubble)

    def _toggle_research_popup(self) -> None:
        """Show or hide the research flyout near the streaming bubble."""
        anchor = self._research_anchor_widget()
        if anchor is None:
            return
        popup = self._ensure_research_popup()
        popup.toggle_near(anchor)

    def _cancel_research_grace_timer(self) -> None:
        """Stop the post-findings activity grace timer."""
        timer = getattr(self, "_research_grace_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
        self._research_grace_timer = None

    def _schedule_research_activity_hide(self) -> None:
        """Keep the activity row visible briefly after findings, then hide it."""
        self._cancel_research_grace_timer()
        timer = QTimer(cast(QWidget, self))
        timer.setSingleShot(True)
        timer.setInterval(_RESEARCH_GRACE_MS)
        timer.timeout.connect(self._on_research_grace_elapsed)
        timer.start()
        self._research_grace_timer = timer

    def _on_research_grace_elapsed(self) -> None:
        """Hide activity after the grace window; leave the Research chip visible."""
        self._research_grace_timer = None
        bubble = cast(Any, self)._resolve_streaming_bubble()
        if bubble is None:
            return
        bubble.hide_activity()
        bubble.set_research_footer_visible(bool(self._research_findings_text.strip()))

    def _wire_streaming_bubble_research(self, bubble: Any) -> None:
        """Connect research toggle signals for one streaming assistant bubble."""
        bubble.research_toggle_requested.connect(self._toggle_research_popup)

    def update_research_state(self, payload: str) -> None:
        """Update research flyout from registry JSON payload."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {"phase": "status", "status": payload, "findings": ""}
        phase = str(data.get("phase") or "")
        status = str(data.get("status") or "")
        findings = str(data.get("findings") or "")

        bubble = cast(Any, self)._resolve_streaming_bubble()
        if bubble is None and not status and not findings:
            return

        if status:
            cast(Any, self).set_activity_status(status)
            if bubble is not None and not bubble.is_activity_visible():
                bubble.show_activity(status)

        if status and status not in self._research_progress_lines:
            self._research_progress_lines.append(status)

        popup = self._ensure_research_popup()
        popup.set_progress_lines(self._research_progress_lines)

        if findings:
            self._research_findings_text = findings
            popup.set_findings_text(findings)
            if bubble is not None:
                bubble.set_research_footer_visible(True)
                self._schedule_research_activity_hide()
            return

        if phase == "stopped":
            self._cancel_research_grace_timer()
            if bubble is not None:
                bubble.hide_activity()
                bubble.set_research_footer_visible(False)
            return

        if phase == "status" and status and bubble is not None:
            bubble.set_research_footer_visible(False)
            if not bubble.is_activity_visible():
                bubble.show_activity(status)

    def sync_research_from_handle(self, *, is_active: bool, findings_text: str) -> None:
        """Re-show activity while a background sub-agent run is still active."""
        if not is_active and not findings_text.strip():
            return
        bubble = cast(Any, self)._resolve_streaming_bubble()
        if bubble is None:
            return
        if is_active:
            bubble.set_research_footer_visible(False)
            if not bubble.is_activity_visible():
                last = (
                    self._research_progress_lines[-1]
                    if self._research_progress_lines
                    else ("Researching workspace…")
                )
                bubble.show_activity(last)
            return
        if findings_text.strip():
            self._research_findings_text = findings_text
            popup = self._ensure_research_popup()
            popup.set_findings_text(findings_text)
            bubble.set_research_footer_visible(True)


__all__ = ["_ChatPanelResearchMixin"]
