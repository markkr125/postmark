"""Tests for AI chat composer budget banner and send gate."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from services.ai.ai_config import AiModelEntry
from services.ai.chat.budget_status import ConnectionBudgetStatus
from ui.sidebar.ai import AiChatPanel


def _model(**kw: object) -> AiModelEntry:
    base: AiModelEntry = {
        "id": "m1",
        "provider": "openai",
        "label": "GPT-4o",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "token",
        "auth_ref": "ref-a",
        "input_cost_per_token": 0.0000025,
        "output_cost_per_token": 0.00001,
        "context": 128_000,
        "enabled": True,
    }
    base.update(kw)  # type: ignore[typeddict-item]
    return base


def _status(*, state: str, known: float = 0.56) -> ConnectionBudgetStatus:
    return ConnectionBudgetStatus(
        connection_key="ref-a",
        provider_label="OpenAI",
        rated=True,
        period="monthly",
        period_reset_label="monthly on the 1st at 00:00",
        period_known_usd=known,
        period_usd=known,
        partial_period=False,
        soft_limit_usd=0.53,
        hard_limit_usd=1.0,
        state=state,  # type: ignore[typeddict-item]
        dedupe_key="ref-a:2026-07-01T00:00:00",
    )


def test_budget_banner_visible_on_soft_exceed(qapp: QApplication, qtbot) -> None:
    """Soft exceed shows the composer banner but keeps send enabled."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models([_model()])
    panel.show()
    panel.refresh_connection_budget(_status(state="soft_exceeded"))
    assert panel._budget_banner.isVisible()
    assert panel._docked_composer._send_btn.isEnabled()


def test_budget_banner_blocks_send_on_hard_exceed(qapp: QApplication, qtbot) -> None:
    """Hard exceed shows the banner and disables send."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models([_model()])
    panel.show()
    panel.refresh_connection_budget(_status(state="hard_exceeded", known=1.0))
    assert panel._budget_banner.isVisible()
    assert not panel._docked_composer._send_btn.isEnabled()


def test_budget_banner_hidden_when_ok(qapp: QApplication, qtbot) -> None:
    """Under-cap spend hides the banner."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models([_model()])
    panel.refresh_connection_budget(_status(state="ok", known=0.10))
    assert not panel._budget_banner.isVisible()
    assert panel._docked_composer._send_btn.isEnabled()
