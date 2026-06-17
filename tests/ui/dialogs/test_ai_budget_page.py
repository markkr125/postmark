"""UI tests for Settings → AI → Budgets page."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHeaderView,
    QMenu,
    QPushButton,
    QTableWidget,
)

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


def _empty_spend_summary() -> dict[str, object]:
    return {
        "connections": [],
        "period_usd": None,
        "known_period_usd": 0.0,
        "overall_usd": None,
        "known_overall_usd": 0.0,
        "period_tokens": 0,
        "overall_tokens": 0,
        "partial_period": False,
        "partial_overall": False,
        "models": [],
    }


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
    }
    base.update(kw)  # type: ignore[typeddict-item]
    return base


def _trigger_limits_editor(qtbot, ctrl, *, connection_key: str, provider_label: str) -> None:
    """Open the limits editor (same path as the gear menu Limits action)."""
    QTimer.singleShot(0, lambda: ctrl._edit_limits(connection_key, provider_label))
    qtbot.waitUntil(
        lambda: AiBudgetConfig.budget_for_connection(connection_key) is not None,
        timeout=3000,
    )


def _schedule_limits_save(qtbot, *, soft_usd: float) -> None:
    """Fill and accept the limits dialog once ``exec()`` opens it."""

    def _accept_dialog() -> None:
        for widget in QApplication.topLevelWidgets():
            if widget.objectName() != "aiBudgetLimitsDialog":
                continue
            if not isinstance(widget, QDialog):
                continue
            enable = widget.findChild(QCheckBox, "aiBudgetSoftLimitEnable")
            spin = widget.findChild(QDoubleSpinBox)
            buttons = widget.findChild(QDialogButtonBox)
            assert enable is not None
            assert spin is not None
            assert buttons is not None
            enable.setChecked(True)
            spin.setValue(soft_usd)
            save = buttons.button(QDialogButtonBox.StandardButton.Save)
            assert save is not None
            qtbot.mouseClick(save, Qt.MouseButton.LeftButton)
            return
        QTimer.singleShot(0, _accept_dialog)

    QTimer.singleShot(0, _accept_dialog)


def test_budget_page_persists_soft_limit_via_dialog(qapp, qtbot, monkeypatch) -> None:
    """Saving soft limits in the limits dialog persists immediately."""
    monkeypatch.setattr(AiConfig, "get_models", lambda: [_model()])
    monkeypatch.setattr(
        "ui.dialogs.settings.ai_budget.page.global_spend_summary",
        lambda **_kw: _empty_spend_summary(),
    )
    page, ctrl = build_ai_budget_page(lambda: None)
    qtbot.addWidget(page)
    ctrl.reload()

    table = page.findChild(QTableWidget, "aiProviderBudgetsTree")
    assert table is not None
    assert table.rowCount() == 1

    _schedule_limits_save(qtbot, soft_usd=25.0)
    _trigger_limits_editor(qtbot, ctrl, connection_key="ref-a", provider_label="OpenAI")

    row = AiBudgetConfig.budget_for_connection("ref-a")
    assert row is not None
    assert row.get("soft_limit_usd") == 25.0


def test_budget_table_has_spend_columns_only(qapp, qtbot, monkeypatch) -> None:
    """Period reset lives in the limits dialog, not the table."""
    monkeypatch.setattr(AiConfig, "get_models", lambda: [_model()])
    monkeypatch.setattr(
        "ui.dialogs.settings.ai_budget.page.global_spend_summary",
        lambda **_kw: _empty_spend_summary(),
    )
    page, ctrl = build_ai_budget_page(lambda: None)
    qtbot.addWidget(page)
    ctrl.reload()
    table = page.findChild(QTableWidget, "aiProviderBudgetsTree")
    assert table is not None
    headers: list[str] = []
    for i in range(table.columnCount()):
        item = table.horizontalHeaderItem(i)
        assert item is not None
        headers.append(item.text())
    assert headers == [
        "Provider",
        "Period spend",
        "Period tokens",
        "All-time spend",
        "All-time tokens",
        "Limits",
        "",
    ]


def test_budget_row_has_gear_menu(qapp, qtbot, monkeypatch) -> None:
    """Rated rows expose Limits and Spend details in the gear menu."""
    monkeypatch.setattr(AiConfig, "get_models", lambda: [_model()])
    monkeypatch.setattr(
        "ui.dialogs.settings.ai_budget.page.global_spend_summary",
        lambda **_kw: _empty_spend_summary(),
    )
    page, ctrl = build_ai_budget_page(lambda: None)
    qtbot.addWidget(page)
    ctrl.reload()
    table = page.findChild(QTableWidget, "aiProviderBudgetsTree")
    assert table is not None
    actions = table.cellWidget(0, 6)
    assert actions is not None
    gear_btn = actions.findChild(QPushButton, "aiBudgetActionsButton")
    assert gear_btn is not None
    menu = actions.findChild(QMenu, "aiBudgetActionsMenu")
    assert menu is not None
    assert [action.text() for action in menu.actions()] == ["Limits", "Spend details"]


def test_budget_table_stretches_provider_column(qapp, qtbot, monkeypatch) -> None:
    """Provider column uses stretch resize mode."""
    monkeypatch.setattr(AiConfig, "get_models", lambda: [_model()])
    monkeypatch.setattr(
        "ui.dialogs.settings.ai_budget.page.global_spend_summary",
        lambda **_kw: _empty_spend_summary(),
    )
    page, _ctrl = build_ai_budget_page(lambda: None)
    qtbot.addWidget(page)
    table = page.findChild(QTableWidget, "aiProviderBudgetsTree")
    assert table is not None
    header = table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch


def test_unrated_connection_omits_limits_menu_item(qapp, qtbot, monkeypatch) -> None:
    """Unrated providers only offer spend details in the gear menu."""
    ollama = _model(
        id="ollama-1",
        provider="ollama",
        auth_ref="local",
        label="llama3.2",
        model="ollama/llama3.2",
    )
    del ollama["input_cost_per_token"]  # type: ignore[misc]
    del ollama["output_cost_per_token"]  # type: ignore[misc]
    monkeypatch.setattr(AiConfig, "get_models", lambda: [ollama])
    monkeypatch.setattr(
        "ui.dialogs.settings.ai_budget.page.global_spend_summary",
        lambda **_kw: {
            "connections": [
                {
                    "connection_key": "local",
                    "provider_label": "Ollama (local)",
                    "period_usd": None,
                    "known_period_usd": 0.0,
                    "overall_usd": None,
                    "known_overall_usd": 0.0,
                    "period_tokens": 1200,
                    "overall_tokens": 1200,
                    "partial_period": False,
                    "partial_overall": False,
                    "models": [],
                }
            ],
            "period_usd": None,
            "known_period_usd": 0.0,
            "overall_usd": None,
            "known_overall_usd": 0.0,
            "period_tokens": 1200,
            "overall_tokens": 1200,
            "partial_period": False,
            "partial_overall": False,
            "models": [],
        },
    )
    page, ctrl = build_ai_budget_page(lambda: None)
    qtbot.addWidget(page)
    ctrl.reload()
    table = page.findChild(QTableWidget, "aiProviderBudgetsTree")
    assert table is not None
    actions = table.cellWidget(0, 6)
    assert actions is not None
    menu = actions.findChild(QMenu, "aiBudgetActionsMenu")
    assert menu is not None
    assert [action.text() for action in menu.actions()] == ["Spend details"]


def test_view_breakdown_button_exists(qapp, qtbot, monkeypatch) -> None:
    """Page-level breakdown button is present."""
    monkeypatch.setattr(AiConfig, "get_models", lambda: [])
    page, _ctrl = build_ai_budget_page(lambda: None)
    qtbot.addWidget(page)
    button = page.findChild(QPushButton, "aiBudgetViewBreakdownBtn")
    assert button is not None
