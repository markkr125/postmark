"""UI tests for Settings → AI → Budgets page."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QTableWidget

from collections.abc import Iterator

import pytest

from services.ai.ai_budget_config import AiBudgetConfig
from services.ai.ai_config import AiConfig, AiModelEntry
from ui.dialogs.settings.ai_budget import build_ai_budget_page


@pytest.fixture(autouse=True)
def _clear_budget_settings() -> Iterator[None]:
    """Use an isolated QSettings scope for each test."""
    settings = QSettings("Postmark", "Postmark")
    settings.remove("ai/provider_budgets")
    settings.sync()
    yield
    settings.remove("ai/provider_budgets")
    settings.sync()


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
        "input_cost_per_token": 0.0,
        "output_cost_per_token": 0.0,
    }
    base.update(kw)  # type: ignore[typeddict-item]
    return base


def test_budget_page_persists_soft_limit_on_edit(qapp, qtbot, monkeypatch) -> None:
    """Enabling a soft limit persists immediately."""
    monkeypatch.setattr(AiConfig, "get_models", lambda: [_model()])
    page, ctrl = build_ai_budget_page(lambda: None)
    qtbot.addWidget(page)
    ctrl.reload()

    table = page.findChild(QTableWidget, "aiProviderBudgetsTree")
    assert table is not None
    assert table.rowCount() == 1

    soft_host = table.cellWidget(0, 2)
    assert soft_host is not None
    from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox

    enable = soft_host.findChild(QCheckBox)
    spin = soft_host.findChild(QDoubleSpinBox)
    assert enable is not None
    assert spin is not None

    enable.setChecked(True)
    spin.setValue(25.0)
    qtbot.wait(50)

    row = AiBudgetConfig.budget_for_connection("ref-a")
    assert row is not None
    assert row.get("soft_limit_usd") == 25.0
