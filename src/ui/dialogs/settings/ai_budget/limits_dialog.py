"""Soft/hard USD limit editor for one provider connection."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.ai.ai_budget_config import BudgetPeriod
from ui.dialogs.settings.ai_budget.period_reset_panel import BudgetPeriodResetPanel
from ui.styling.icons import phi
from ui.styling.theme import COLOR_SOLID_BUTTON_FG

_MIN_LIMIT_USD = 0.01
_DIALOG_MIN_WIDTH = 480
_DIALOG_MIN_HEIGHT = 420
_DIALOG_DEFAULT_WIDTH = 520
_DIALOG_DEFAULT_HEIGHT = 460


@dataclass(frozen=True)
class BudgetLimitsResult:
    """Limits and reset schedule chosen in the limits dialog."""

    period: BudgetPeriod
    period_anchor: str | None
    soft_limit_usd: float | None
    hard_limit_usd: float | None


class AiBudgetLimitsDialog(QDialog):
    """Edit reset schedule and optional soft/hard USD limits for one connection."""

    def __init__(
        self,
        *,
        provider_label: str,
        period: BudgetPeriod,
        period_anchor: str | None,
        soft_limit_usd: float | None,
        hard_limit_usd: float | None,
        parent: QWidget | None = None,
    ) -> None:
        """Build limit controls for *provider_label*."""
        super().__init__(parent)
        self.setObjectName("aiBudgetLimitsDialog")
        self.setWindowTitle(f"Limits — {provider_label}")
        self.setMinimumSize(_DIALOG_MIN_WIDTH, _DIALOG_MIN_HEIGHT)
        self.resize(_DIALOG_DEFAULT_WIDTH, _DIALOG_DEFAULT_HEIGHT)
        self._result = BudgetLimitsResult(
            period=period,
            period_anchor=period_anchor,
            soft_limit_usd=soft_limit_usd,
            hard_limit_usd=hard_limit_usd,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        intro = QLabel(
            "Choose when spend resets, then optionally set soft and hard USD caps. "
            "Soft limits warn when exceeded; hard limits block new messages once "
            "enforcement is enabled."
        )
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self._period_panel = BudgetPeriodResetPanel()
        self._period_panel.load(period=period, period_anchor=period_anchor)
        root.addWidget(self._period_panel)

        limits_heading = QLabel("USD limits")
        limits_heading.setObjectName("titleLabel")
        root.addWidget(limits_heading)

        self._soft_enable = QCheckBox("Soft limit")
        self._soft_enable.setObjectName("aiBudgetSoftLimitEnable")
        self._soft_spin = self._make_spin()
        if soft_limit_usd is not None and soft_limit_usd >= _MIN_LIMIT_USD:
            self._soft_enable.setChecked(True)
            self._soft_spin.setValue(float(soft_limit_usd))

        self._hard_enable = QCheckBox("Hard limit")
        self._hard_enable.setObjectName("aiBudgetHardLimitEnable")
        self._hard_spin = self._make_spin()
        if hard_limit_usd is not None and hard_limit_usd >= _MIN_LIMIT_USD:
            self._hard_enable.setChecked(True)
            self._hard_spin.setValue(float(hard_limit_usd))

        limits_row = QHBoxLayout()
        limits_row.setSpacing(16)
        limits_row.addWidget(self._make_limit_column(self._soft_enable, self._soft_spin), 1)
        limits_row.addWidget(self._make_limit_column(self._hard_enable, self._hard_spin), 1)
        root.addLayout(limits_row)

        self._soft_spin.setEnabled(self._soft_enable.isChecked())
        self._hard_spin.setEnabled(self._hard_enable.isChecked())
        self._soft_enable.toggled.connect(self._soft_spin.setEnabled)
        self._hard_enable.toggled.connect(self._hard_spin.setEnabled)

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
        root.addWidget(buttons)

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


def edit_budget_limits(
    *,
    provider_label: str,
    period: BudgetPeriod,
    period_anchor: str | None,
    soft_limit_usd: float | None,
    hard_limit_usd: float | None,
    parent: QWidget | None = None,
) -> BudgetLimitsResult | None:
    """Open the limits editor; return new limits when saved."""
    dialog = AiBudgetLimitsDialog(
        provider_label=provider_label,
        period=period,
        period_anchor=period_anchor,
        soft_limit_usd=soft_limit_usd,
        hard_limit_usd=hard_limit_usd,
        parent=parent,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.result_limits()


__all__ = ["AiBudgetLimitsDialog", "BudgetLimitsResult", "edit_budget_limits"]
