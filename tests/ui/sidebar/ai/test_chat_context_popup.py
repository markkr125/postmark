"""Tests for the AI chat context breakdown popup."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from services.ai.chat.context_usage import ContextUsageBreakdown
from ui.sidebar.ai.chat_context_popup import AiChatContextUsagePopup, compute_bar_segments
from ui.sidebar.ai.chat_panel.context_ring_button import ContextUsageRingButton


def _breakdown(*, estimated: bool = True) -> ContextUsageBreakdown:
    return {
        "used_tokens": 42_000,
        "total_tokens": 128_000,
        "has_summarized": True,
        "is_estimated": estimated,
        "categories": [
            {"id": "system_prompt", "label": "System prompt", "tokens": 4000},
            {"id": "tools", "label": "Tools", "tokens": 2000},
            {"id": "rules", "label": "Rules", "tokens": 0},
            {"id": "skills", "label": "Skills", "tokens": 0},
            {"id": "mcp", "label": "MCP", "tokens": 0},
            {"id": "subagents", "label": "Subagents", "tokens": 0},
            {"id": "summarized_conversation", "label": "Summarized conversation", "tokens": 6000},
            {"id": "conversation", "label": "Conversation", "tokens": 30_000},
        ],
    }


def test_context_bar_fill_matches_used_fraction_of_total() -> None:
    """Stacked segments occupy only the used share of the context window."""
    categories = [
        {"id": "system_prompt", "label": "System prompt", "tokens": 29},
        {"id": "tools", "label": "Tools", "tokens": 0},
        {"id": "rules", "label": "Rules", "tokens": 0},
        {"id": "skills", "label": "Skills", "tokens": 0},
        {"id": "mcp", "label": "MCP", "tokens": 0},
        {"id": "subagents", "label": "Subagents", "tokens": 0},
        {"id": "summarized_conversation", "label": "Summarized conversation", "tokens": 0},
        {"id": "conversation", "label": "Conversation", "tokens": 14_100},
    ]
    segments = compute_bar_segments(
        bar_width=200,
        used_tokens=14_129,
        total_tokens=32_000,
        categories=categories,  # type: ignore[arg-type]
    )
    filled = segments[-1][1] + segments[-1][2]
    assert filled == round(200 * 14_129 / 32_000)
    assert filled < 200


def test_context_popup_bar_uses_window_fraction(qapp: QApplication, qtbot) -> None:
    """The popup bar leaves empty track when usage is below the model window."""
    popup = AiChatContextUsagePopup.instance()
    popup.hide_popup()
    qtbot.addWidget(popup)
    breakdown = _breakdown(estimated=False)
    breakdown["used_tokens"] = 14_129
    breakdown["total_tokens"] = 32_000
    breakdown["categories"] = [
        {"id": "system_prompt", "label": "System prompt", "tokens": 29},
        {"id": "tools", "label": "Tools", "tokens": 0},
        {"id": "rules", "label": "Rules", "tokens": 0},
        {"id": "skills", "label": "Skills", "tokens": 0},
        {"id": "mcp", "label": "MCP", "tokens": 0},
        {"id": "subagents", "label": "Subagents", "tokens": 0},
        {"id": "summarized_conversation", "label": "Summarized conversation", "tokens": 0},
        {"id": "conversation", "label": "Conversation", "tokens": 14_100},
    ]
    popup.set_breakdown(breakdown)
    assert popup._bar.fill_width() < popup._bar.width()


def test_context_popup_shows_summary_and_all_rows(qapp: QApplication, qtbot) -> None:
    """Popup renders the summary line and all 8 Cursor category rows."""
    popup = AiChatContextUsagePopup.instance()
    popup.hide_popup()
    qtbot.addWidget(popup)
    anchor = ContextUsageRingButton()
    qtbot.addWidget(anchor)
    anchor.show()

    popup.show_for(anchor, _breakdown())

    assert popup.isVisible()
    assert "33%" in popup._summary_left.text()
    assert "Estimated" in popup._summary_left.text()
    assert "42k" in popup._summary_right.text()
    assert len(popup._rows) == 8
    assert popup._rows[0]._label.text() == "System prompt"
    assert popup._rows[-1]._label.text() == "Conversation"
    assert popup._hint.isVisible()
    popup.hide_popup()


def test_context_popup_anchor_click_does_not_auto_close(qapp: QApplication, qtbot) -> None:
    """The click-away filter ignores clicks on the ring anchor itself."""
    popup = AiChatContextUsagePopup.instance()
    popup.hide_popup()
    qtbot.addWidget(popup)
    anchor = ContextUsageRingButton()
    qtbot.addWidget(anchor)
    anchor.show()

    popup.show_for(anchor, _breakdown(estimated=False))
    popup._opened_at_ms = 0
    qtbot.mouseClick(anchor, Qt.MouseButton.LeftButton)

    assert popup.isVisible()
    popup.hide_popup()


def test_context_popup_outside_click_closes_after_grace(qapp: QApplication, qtbot) -> None:
    """Clicks outside the popup close it once the grace window has elapsed."""
    popup = AiChatContextUsagePopup.instance()
    popup.hide_popup()
    qtbot.addWidget(popup)
    anchor = ContextUsageRingButton()
    qtbot.addWidget(anchor)
    anchor.show()

    popup.show_for(anchor, _breakdown())
    popup._opened_at_ms = 0
    outside = popup.geometry().bottomRight() + QPoint(20, 20)
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(0, 0),
        QPointF(outside),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    popup.eventFilter(qapp, press)

    assert not popup.isVisible()


def test_context_popup_close_button_hides(qapp: QApplication, qtbot) -> None:
    """The popup's close button dismisses it."""
    popup = AiChatContextUsagePopup.instance()
    popup.hide_popup()
    qtbot.addWidget(popup)
    anchor = ContextUsageRingButton()
    qtbot.addWidget(anchor)
    anchor.show()

    popup.show_for(anchor, _breakdown())
    qtbot.mouseClick(popup._close_btn, Qt.MouseButton.LeftButton)

    assert not popup.isVisible()


def test_context_popup_shows_estimation_hint_when_ring_high(qapp: QApplication, qtbot) -> None:
    """Estimated breakdowns above 70% explain that the ring is provisional."""
    popup = AiChatContextUsagePopup.instance()
    popup.hide_popup()
    qtbot.addWidget(popup)
    anchor = ContextUsageRingButton()
    qtbot.addWidget(anchor)
    anchor.show()

    breakdown = _breakdown(estimated=True)
    breakdown["used_tokens"] = 90_000
    breakdown["total_tokens"] = 128_000
    popup.show_for(anchor, breakdown)

    assert "estimated until the model context is available" in popup._hint.text().lower()
    popup.hide_popup()


def test_context_popup_shows_divergence_hint(qapp: QApplication, qtbot) -> None:
    """High usage plus transcript/SDK mismatch surfaces an extra honesty line."""
    popup = AiChatContextUsagePopup.instance()
    popup.hide_popup()
    qtbot.addWidget(popup)
    anchor = ContextUsageRingButton()
    qtbot.addWidget(anchor)
    anchor.show()

    breakdown = _breakdown(estimated=True)
    breakdown["used_tokens"] = 95_000
    breakdown["total_tokens"] = 128_000
    breakdown["transcript_larger_than_sdk"] = True
    popup.show_for(anchor, breakdown)

    hint = popup._hint.text().lower()
    assert "saved transcript is larger" in hint
    popup.hide_popup()


def _spend_breakdown() -> dict[str, object]:
    return {
        "total_usd": 0.042,
        "known_usd": 0.042,
        "assistant_turns": 3,
        "priced_turns": 3,
        "partial": False,
        "models": [
            {
                "model_id": "m-openai",
                "model_label": "gpt-5.4-mini",
                "provider_label": "OpenAI (work)",
                "prompt_tokens": 18_000,
                "completion_tokens": 400,
                "reasoning_tokens": 0,
                "cost_usd": 0.038,
                "turn_count": 2,
            },
            {
                "model_id": "m-claude",
                "model_label": "claude-3-5-sonnet",
                "provider_label": "Anthropic",
                "prompt_tokens": 1_000,
                "completion_tokens": 200,
                "reasoning_tokens": 0,
                "cost_usd": 0.004,
                "turn_count": 1,
            },
            {
                "model_id": "m-ollama",
                "model_label": "llama3.2",
                "provider_label": "Ollama",
                "prompt_tokens": 5_000,
                "completion_tokens": 300,
                "reasoning_tokens": 0,
                "cost_usd": None,
                "turn_count": 1,
            },
        ],
    }


def test_spend_popup_shows_model_rows(qapp: QApplication, qtbot) -> None:
    """Spend tab lists per-model token and cost rows."""
    popup = AiChatContextUsagePopup.instance()
    popup.hide_popup()
    qtbot.addWidget(popup)
    anchor = ContextUsageRingButton()
    qtbot.addWidget(anchor)
    anchor.show()

    popup.show_for(anchor, _breakdown(estimated=False), spend_breakdown=_spend_breakdown())  # type: ignore[arg-type]
    popup.set_mode("spend")

    assert popup.isVisible()
    assert popup._mode == "spend"
    assert popup._cost_pill.text() == "Spend $0.042"
    assert "assistant turns" in popup._spend_summary.text().lower()
    assert popup._spend_rows[0].isVisible()
    assert popup._spend_rows[0]._model.text() == "gpt-5.4-mini"
    assert popup._spend_rows[0]._provider.text() == "OpenAI (work) · 2 turns"
    assert popup._spend_rows[2]._model.text() == "llama3.2"
    assert popup._spend_rows[2]._cost.text() == "—"
    popup.hide_popup()


def test_spend_popup_height_is_clamped(qapp: QApplication, qtbot) -> None:
    """Spend tab keeps a stable min height and scrolls when many models are listed."""
    popup = AiChatContextUsagePopup.instance()
    popup.hide_popup()
    qtbot.addWidget(popup)
    anchor = ContextUsageRingButton()
    qtbot.addWidget(anchor)
    anchor.show()

    popup.show_for(anchor, _breakdown(estimated=False), spend_breakdown=_spend_breakdown())  # type: ignore[arg-type]
    popup.set_mode("spend")

    assert popup.minimumHeight() == 300
    assert popup.maximumHeight() == 420
    assert popup._spend_scroll.minimumHeight() == 140
    assert popup._spend_scroll.maximumHeight() == 260
    assert popup.height() >= 300
    popup.hide_popup()


def test_popup_mode_pills_switch_in_place(qapp: QApplication, qtbot) -> None:
    """Context and Spend pills inside the flyout swap body without closing."""
    popup = AiChatContextUsagePopup.instance()
    popup.hide_popup()
    qtbot.addWidget(popup)
    ring = ContextUsageRingButton()
    qtbot.addWidget(ring)
    ring.show()

    popup.show_for(ring, _breakdown(estimated=False), spend_breakdown=_spend_breakdown())  # type: ignore[arg-type]
    assert popup._mode == "context"
    assert popup._context_body.isVisible()
    assert not popup._spend_body.isVisible()

    popup.set_mode("spend")
    assert popup.isVisible()
    assert popup._mode == "spend"
    assert popup._anchor is ring
    assert popup._spend_body.isVisible()
    assert not popup._context_body.isVisible()
    popup.hide_popup()


def test_spend_tab_shows_connection_budget_card(qapp: QApplication, qtbot) -> None:
    """Spend mode shows period spend against configured caps when limits exist."""
    from services.ai.chat.budget_status import ConnectionBudgetStatus

    popup = AiChatContextUsagePopup.instance()
    popup.hide_popup()
    qtbot.addWidget(popup)
    ring = ContextUsageRingButton()
    qtbot.addWidget(ring)
    ring.show()
    popup.show_for(ring, _breakdown(estimated=False), spend_breakdown=_spend_breakdown())  # type: ignore[arg-type]
    status = ConnectionBudgetStatus(
        connection_key="ref-a",
        provider_label="OpenAI",
        rated=True,
        period="monthly",
        period_reset_label="monthly on the 1st at 00:00",
        period_known_usd=0.56,
        period_usd=0.56,
        partial_period=False,
        soft_limit_usd=0.53,
        hard_limit_usd=1.0,
        state="soft_exceeded",
        dedupe_key="ref-a:2026-07-01T00:00:00",
    )
    popup.set_mode("spend")
    popup.set_connection_budget(status)
    assert popup._budget_card.isVisible()
    assert "OpenAI" in popup._budget_title.text()
    assert "soft" in popup._budget_amounts.text().lower()
    assert popup._budget_reset.isVisible()
    popup.hide_popup()


def test_spend_tab_hides_budget_card_without_limits(qapp: QApplication, qtbot) -> None:
    """Spend mode hides the budget card when no caps are configured."""
    from services.ai.chat.budget_status import ConnectionBudgetStatus

    popup = AiChatContextUsagePopup.instance()
    popup.hide_popup()
    qtbot.addWidget(popup)
    status = ConnectionBudgetStatus(
        connection_key="ref-a",
        provider_label="OpenAI",
        rated=True,
        period="none",
        period_reset_label="",
        period_known_usd=0.10,
        period_usd=0.10,
        partial_period=False,
        soft_limit_usd=None,
        hard_limit_usd=None,
        state="no_limits",
        dedupe_key="ref-a",
    )
    popup.set_mode("spend")
    popup.set_connection_budget(status)
    assert not popup._budget_card.isVisible()
