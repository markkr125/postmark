"""Provider connection editor — limits and spend details tabs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.ai.ai_budget_config import BudgetPeriod
from services.ai.chat.spend_rollup import ConnectionSpendSummary
from ui.dialogs.settings.ai_budget.breakdown_dialog import (
    BudgetSpendDetailsContext,
    BudgetSpendDetailsPanel,
)
from ui.dialogs.settings.ai_budget.period_reset_panel import BudgetPeriodResetPanel
from ui.styling.icons import phi
from ui.styling.theme import COLOR_SOLID_BUTTON_FG

_MIN_LIMIT_USD = 0.01
_DIALOG_MIN_WIDTH = 560
_DIALOG_MIN_HEIGHT = 480
_DIALOG_DEFAULT_WIDTH = 600
_DIALOG_DEFAULT_HEIGHT = 520
_BudgetConnectionTab = Literal["limits", "spend"]


@dataclass(frozen=True)
class BudgetLimitsResult:
    """Limits and reset schedule chosen in the connection dialog."""

    period: BudgetPeriod
    period_anchor: str | None
    soft_limit_usd: float | None
    hard_limit_usd: float | None


class AiBudgetConnectionDialog(QDialog):
    """Edit limits and view per-model spend for one provider connection."""

    def __init__(
        self,
        *,
        provider_label: str,
        spend: ConnectionSpendSummary | None,
        rated: bool,
        period: BudgetPeriod,
        period_anchor: str | None,
        soft_limit_usd: float | None,
        hard_limit_usd: float | None,
        initial_tab: _BudgetConnectionTab = "limits",
        parent: QWidget | None = None,
    ) -> None:
        """Build tabbed limits and spend views for *provider_label*."""
        super().__init__(parent)
        self.setObjectName("aiBudgetConnectionDialog")
        self.setWindowTitle(f"{provider_label} — Postmark")
        self.setMinimumSize(_DIALOG_MIN_WIDTH, _DIALOG_MIN_HEIGHT)
        self.resize(_DIALOG_DEFAULT_WIDTH, _DIALOG_DEFAULT_HEIGHT)
        self._rated = rated
        self._result = BudgetLimitsResult(
            period=period,
            period_anchor=period_anchor,
            soft_limit_usd=soft_limit_usd,
            hard_limit_usd=hard_limit_usd,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("aiBudgetConnectionTabs")
        self._tabs.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)
        if rated:
            self._tabs.addTab(self._build_limits_tab(), "Limits")
        spend_context = BudgetSpendDetailsContext.from_spend(
            spend,
            rated=rated,
            period=period,
            period_anchor=period_anchor,
        )
        spend_tab = BudgetSpendDetailsPanel(spend_context)
        self._tabs.addTab(spend_tab, "Spend details")
        if rated and initial_tab == "spend":
            self._tabs.setCurrentIndex(1)
        root.addWidget(self._tabs, 1)

        if rated:
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
            )
            save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
            cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
            if save_btn is not None:
                save_btn.setObjectName("primaryButton")
                save_btn.setIcon(phi("floppy-disk", color=COLOR_SOLID_BUTTON_FG))
                save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if cancel_btn is not None:
                cancel_btn.setObjectName("outlineButton")
                cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.accepted.connect(self._on_save)
            buttons.rejected.connect(self.reject)
        else:
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
            if close_btn is not None:
                close_btn.setObjectName("outlineButton")
                close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.rejected.connect(self.reject)
            buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

    def _build_limits_tab(self) -> QWidget:
        """Return the limits and reset schedule tab."""
        tab = QWidget()
        tab.setObjectName("aiBudgetLimitsTab")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        intro = QLabel(
            "Choose when spend resets, then optionally set soft and hard USD caps. "
            "Soft limits warn when exceeded; hard limits block new messages once "
            "enforcement is enabled."
        )
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._period_panel = BudgetPeriodResetPanel()
        self._period_panel.load(
            period=self._result.period,
            period_anchor=self._result.period_anchor,
        )
        layout.addWidget(self._period_panel)

        limits_heading = QLabel("USD limits")
        limits_heading.setObjectName("titleLabel")
        layout.addWidget(limits_heading)

        self._soft_enable = QCheckBox("Soft limit")
        self._soft_enable.setObjectName("aiBudgetSoftLimitEnable")
        self._soft_spin = self._make_spin()
        soft = self._result.soft_limit_usd
        if soft is not None and soft >= _MIN_LIMIT_USD:
            self._soft_enable.setChecked(True)
            self._soft_spin.setValue(float(soft))

        self._hard_enable = QCheckBox("Hard limit")
        self._hard_enable.setObjectName("aiBudgetHardLimitEnable")
        self._hard_spin = self._make_spin()
        hard = self._result.hard_limit_usd
        if hard is not None and hard >= _MIN_LIMIT_USD:
            self._hard_enable.setChecked(True)
            self._hard_spin.setValue(float(hard))

        limits_row = QHBoxLayout()
        limits_row.setSpacing(16)
        limits_row.addWidget(self._make_limit_column(self._soft_enable, self._soft_spin), 1)
        limits_row.addWidget(self._make_limit_column(self._hard_enable, self._hard_spin), 1)
        layout.addLayout(limits_row)

        self._soft_spin.setEnabled(self._soft_enable.isChecked())
        self._hard_spin.setEnabled(self._hard_enable.isChecked())
        self._soft_enable.toggled.connect(self._soft_spin.setEnabled)
        self._hard_enable.toggled.connect(self._hard_spin.setEnabled)
        layout.addStretch(1)
        return tab

    def _make_limit_column(self, checkbox: QCheckBox, spin: QDoubleSpinBox) -> QWidget:
        """Stack one enable checkbox above its USD amount field."""
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(checkbox, 0)
        lay.addWidget(spin, 0)
        return host

    def _make_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setObjectName("aiBudgetLimitSpin")
        spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        spin.setDecimals(2)
        spin.setMinimum(_MIN_LIMIT_USD)
        spin.setMaximum(1_000_000.0)
        spin.setSingleStep(0.01)
        spin.setSuffix(" USD")
        spin.setValue(_MIN_LIMIT_USD)
        return spin

    def _on_save(self) -> None:
        soft = self._soft_spin.value() if self._soft_enable.isChecked() else None
        hard = self._hard_spin.value() if self._hard_enable.isChecked() else None
        self._result = BudgetLimitsResult(
            period=self._period_panel.period(),
            period_anchor=self._period_panel.period_anchor(),
            soft_limit_usd=soft,
            hard_limit_usd=hard,
        )
        self.accept()

    def result_limits(self) -> BudgetLimitsResult:
        """Return limits after the dialog is accepted."""
        return self._result


# Backward-compatible alias for docs and imports.
AiBudgetLimitsDialog = AiBudgetConnectionDialog


def open_budget_connection_dialog(
    *,
    provider_label: str,
    spend: ConnectionSpendSummary | None,
    rated: bool,
    period: BudgetPeriod = "none",
    period_anchor: str | None = None,
    soft_limit_usd: float | None = None,
    hard_limit_usd: float | None = None,
    initial_tab: _BudgetConnectionTab = "limits",
    parent: QWidget | None = None,
) -> BudgetLimitsResult | None:
    """Open the tabbed connection editor; return limits when saved on a rated row."""
    dialog = AiBudgetConnectionDialog(
        provider_label=provider_label,
        spend=spend,
        rated=rated,
        period=period,
        period_anchor=period_anchor,
        soft_limit_usd=soft_limit_usd,
        hard_limit_usd=hard_limit_usd,
        initial_tab=initial_tab,
        parent=parent,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    if not rated:
        return None
    return dialog.result_limits()


def edit_budget_limits(
    *,
    provider_label: str,
    period: BudgetPeriod,
    period_anchor: str | None,
    soft_limit_usd: float | None,
    hard_limit_usd: float | None,
    parent: QWidget | None = None,
) -> BudgetLimitsResult | None:
    """Open the limits tab for a rated connection; return new limits when saved."""
    return open_budget_connection_dialog(
        provider_label=provider_label,
        spend=None,
        rated=True,
        period=period,
        period_anchor=period_anchor,
        soft_limit_usd=soft_limit_usd,
        hard_limit_usd=hard_limit_usd,
        initial_tab="limits",
        parent=parent,
    )


__all__ = [
    "AiBudgetConnectionDialog",
    "AiBudgetLimitsDialog",
    "BudgetLimitsResult",
    "edit_budget_limits",
    "open_budget_connection_dialog",
]
