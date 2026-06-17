"""UI tests for Settings → AI → Budgets page."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHeaderView,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QWidget,
)

from services.ai.ai_budget_config import AiBudgetConfig
from services.ai.ai_config import AiConfig, AiModelEntry
from ui.dialogs.settings.ai_budget import build_ai_budget_page
from ui.dialogs.settings.ai_budget.limits_dialog import (
    AiBudgetConnectionDialog,
    BudgetLimitsResult,
)


@pytest.fixture(autouse=True)
def _clear_budget_settings() -> Iterator[None]:
    """Use an isolated QSettings scope for each test."""
    settings = QSettings("Postmark", "Postmark")
    settings.remove("ai/provider_budgets")
    settings.sync()
    yield
    settings.remove("ai/provider_budgets")
    settings.sync()


@pytest.fixture(autouse=True)
def _close_stray_dialogs(qapp: QApplication) -> Iterator[None]:
    """Ensure modal budget dialogs never linger on the desktop after a test."""
    yield
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, QDialog):
            widget.close()
            widget.deleteLater()
    qapp.processEvents()


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


def _sample_connection_spend() -> dict[str, object]:
    return {
        "connection_key": "ref-a",
        "provider_label": "OpenAI",
        "period_usd": 0.12,
        "known_period_usd": 0.12,
        "overall_usd": 0.41,
        "known_overall_usd": 0.41,
        "period_tokens": 50_200,
        "overall_tokens": 312_700,
        "partial_period": False,
        "partial_overall": False,
        "models": [
            {
                "model_id": "m1",
                "model_label": "gpt-5.4-mini",
                "provider_label": "OpenAI",
                "prompt_tokens": 300_000,
                "completion_tokens": 12_700,
                "reasoning_tokens": 0,
                "cost_usd": 0.41,
                "turn_count": 3,
            }
        ],
    }


def _spend_panel(dialog: AiBudgetConnectionDialog) -> QWidget:
    """Return the Spend details panel widget inside the connection dialog."""
    tabs = dialog.findChild(QTabWidget, "aiBudgetConnectionTabs")
    assert tabs is not None
    tabs.setCurrentIndex(tabs.count() - 1)
    panel = tabs.findChild(
        QWidget,
        "aiBudgetSpendDetailsPanel",
        Qt.FindChildOption.FindChildrenRecursively,
    )
    assert panel is not None
    return panel


def _spend_tab_labels(dialog: AiBudgetConnectionDialog) -> list[str]:
    """Return label texts on the Spend details tab."""
    panel = _spend_panel(dialog)
    return [label.text() for label in panel.findChildren(QLabel)]


def _spend_tab_text(dialog: AiBudgetConnectionDialog) -> str:
    """Return concatenated label text from the Spend details tab."""
    return "\n".join(_spend_tab_labels(dialog))


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


def test_budget_page_persists_soft_limit_via_dialog(qapp, qtbot, monkeypatch) -> None:
    """Saving soft limits through the opener persists immediately (no modal ``exec``)."""
    monkeypatch.setattr(AiConfig, "get_models", lambda: [_model()])
    monkeypatch.setattr(
        "ui.dialogs.settings.ai_budget.page.global_spend_summary",
        lambda **_kw: _empty_spend_summary(),
    )
    monkeypatch.setattr(
        "ui.dialogs.settings.ai_budget.page.open_budget_connection_dialog",
        lambda **_kw: BudgetLimitsResult(
            period="none",
            period_anchor=None,
            soft_limit_usd=25.0,
            hard_limit_usd=None,
        ),
    )

    page, ctrl = build_ai_budget_page(lambda: None)
    qtbot.addWidget(page)
    ctrl.reload()
    ctrl._edit_limits("ref-a", "OpenAI")

    row = AiBudgetConfig.budget_for_connection("ref-a")
    assert row is not None
    assert row.get("soft_limit_usd") == 25.0


def test_budget_table_has_spend_columns_only(qapp, qtbot, monkeypatch) -> None:
    """Period reset lives in the connection dialog, not the table."""
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


def test_rated_connection_dialog_has_limits_and_spend_tabs(qapp, qtbot) -> None:
    """Rated connections expose Limits and Spend details tabs (widget-only, no ``exec``)."""
    dialog = AiBudgetConnectionDialog(
        provider_label="OpenAI",
        spend=None,
        rated=True,
        period="none",
        period_anchor=None,
        soft_limit_usd=None,
        hard_limit_usd=None,
    )
    qtbot.addWidget(dialog)
    tabs = dialog.findChild(QTabWidget, "aiBudgetConnectionTabs")
    assert tabs is not None
    assert tabs.count() == 2
    assert tabs.tabText(0) == "Limits"
    assert tabs.tabText(1) == "Spend details"


def test_reset_schedule_height_stable_across_periods(qapp, qtbot) -> None:
    """Yearly shows three schedule rows without shifting USD limits downward."""
    dialog = AiBudgetConnectionDialog(
        provider_label="OpenAI",
        spend=None,
        rated=True,
        period="daily",
        period_anchor=None,
        soft_limit_usd=None,
        hard_limit_usd=None,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qapp.processEvents()

    period_combo = dialog.findChild(QComboBox, "aiBudgetPeriodCombo")
    schedule = dialog.findChild(QWidget, "aiBudgetResetSchedule")
    soft_limit = dialog.findChild(QCheckBox, "aiBudgetSoftLimitEnable")
    assert period_combo is not None
    assert schedule is not None
    assert soft_limit is not None

    period_combo.setCurrentIndex(1)  # daily
    qapp.processEvents()
    daily_limits_y = soft_limit.mapTo(dialog, soft_limit.rect().topLeft()).y()

    period_combo.setCurrentIndex(4)  # yearly
    qapp.processEvents()

    assert schedule.height() == schedule.maximumHeight()
    assert soft_limit.mapTo(dialog, soft_limit.rect().topLeft()).y() == daily_limits_y


def test_unrated_connection_dialog_is_spend_only(qapp, qtbot) -> None:
    """Unrated connections show spend details without a Limits tab."""
    dialog = AiBudgetConnectionDialog(
        provider_label="Ollama (local)",
        spend=None,
        rated=False,
        period="none",
        period_anchor=None,
        soft_limit_usd=None,
        hard_limit_usd=None,
    )
    qtbot.addWidget(dialog)
    tabs = dialog.findChild(QTabWidget, "aiBudgetConnectionTabs")
    assert tabs is not None
    assert tabs.count() == 1
    assert tabs.tabText(0) == "Spend details"


def test_spend_details_shows_labeled_columns_and_summary(qapp, qtbot) -> None:
    """Spend tab exposes summary card, column headers, and all-time model rows."""
    dialog = AiBudgetConnectionDialog(
        provider_label="OpenAI",
        spend=_sample_connection_spend(),  # type: ignore[arg-type]
        rated=True,
        period="yearly",
        period_anchor="2026-01-01T00:00",
        soft_limit_usd=None,
        hard_limit_usd=None,
    )
    qtbot.addWidget(dialog)
    panel = _spend_panel(dialog)
    assert (
        panel.findChild(
            QWidget,
            "aiBudgetSpendDetailsHeader",
            Qt.FindChildOption.FindChildrenRecursively,
        )
        is not None
    )
    assert (
        panel.findChild(
            QFrame,
            "aiBudgetSpendSummaryCard",
            Qt.FindChildOption.FindChildrenRecursively,
        )
        is not None
    )
    text = _spend_tab_text(dialog)
    assert "This period" in text
    assert "All time" in text
    assert "Model" in text
    assert "Tokens" in text
    assert "Cost" in text
    assert "gpt-5.4-mini" in text
    assert "all-time usage" in text


def test_unrated_spend_details_summary_is_token_only(qapp, qtbot) -> None:
    """Unrated connections show tokens in the summary and em dash cost in rows."""
    spend = {
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
        "models": [
            {
                "model_id": "ollama-1",
                "model_label": "llama3.2",
                "provider_label": "Ollama (local)",
                "prompt_tokens": 1000,
                "completion_tokens": 200,
                "reasoning_tokens": 0,
                "cost_usd": None,
                "turn_count": 1,
            }
        ],
    }
    dialog = AiBudgetConnectionDialog(
        provider_label="Ollama (local)",
        spend=spend,  # type: ignore[arg-type]
        rated=False,
        period="none",
        period_anchor=None,
        soft_limit_usd=None,
        hard_limit_usd=None,
    )
    qtbot.addWidget(dialog)
    text = _spend_tab_text(dialog)
    assert "USD tracking requires model rates" in text
    assert "1.2k tokens" in text
    assert "$0." not in text
    assert "llama3.2" in text


def test_budget_row_gear_calls_connection_dialog(qapp, qtbot, monkeypatch) -> None:
    """Gear click routes to ``open_budget_connection_dialog`` (stubbed — no modal)."""
    monkeypatch.setattr(AiConfig, "get_models", lambda: [_model()])
    monkeypatch.setattr(
        "ui.dialogs.settings.ai_budget.page.global_spend_summary",
        lambda **_kw: _empty_spend_summary(),
    )
    calls: list[dict[str, object]] = []

    def _capture_open(**kwargs: object) -> None:
        calls.append(dict(kwargs))

    monkeypatch.setattr(
        "ui.dialogs.settings.ai_budget.page.open_budget_connection_dialog",
        _capture_open,
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

    qtbot.mouseClick(gear_btn, Qt.MouseButton.LeftButton)
    assert len(calls) == 1
    assert calls[0]["provider_label"] == "OpenAI"
    assert calls[0]["rated"] is True
    assert calls[0]["initial_tab"] == "limits"


def test_budget_table_columns_are_resizable(qapp, qtbot, monkeypatch) -> None:
    """Budget table fills its viewport while keeping data columns interactive."""
    monkeypatch.setattr(AiConfig, "get_models", lambda: [_model()])
    monkeypatch.setattr(
        "ui.dialogs.settings.ai_budget.page.global_spend_summary",
        lambda **_kw: _empty_spend_summary(),
    )
    page, _ctrl = build_ai_budget_page(lambda: None)
    qtbot.addWidget(page)
    page.resize(900, 500)
    page.show()
    qtbot.wait(10)
    table = page.findChild(QTableWidget, "aiProviderBudgetsTree")
    assert table is not None
    header = table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(5) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(6) == QHeaderView.ResizeMode.Fixed
    assert header.length() >= table.viewport().width()


def test_unrated_gear_calls_connection_dialog(qapp, qtbot, monkeypatch) -> None:
    """Unrated gear opens spend-only flow via the same entry point."""
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
    calls: list[dict[str, object]] = []

    def _capture_open(**kwargs: object) -> None:
        calls.append(dict(kwargs))

    monkeypatch.setattr(
        "ui.dialogs.settings.ai_budget.page.open_budget_connection_dialog",
        _capture_open,
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

    qtbot.mouseClick(gear_btn, Qt.MouseButton.LeftButton)
    assert len(calls) == 1
    assert calls[0]["provider_label"] == "Ollama (local)"
    assert calls[0]["rated"] is False
    assert calls[0]["initial_tab"] == "spend"
