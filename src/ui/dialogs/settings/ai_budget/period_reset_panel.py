"""Period and reset schedule controls for the limits dialog."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from typing import cast

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from services.ai.ai_budget_config import BUDGET_PERIOD_LABELS, BUDGET_PERIODS, BudgetPeriod
from services.ai.budget_period import (
    daily_reset_anchor,
    monthly_reset_anchor,
    parse_period_reset,
    weekly_reset_anchor,
    yearly_reset_anchor,
)

_WEEKDAY_LABELS = list(calendar.day_name)
_MONTH_LABELS = [calendar.month_name[i] for i in range(1, 13)]
_LABEL_WIDTH = 108
_SCHEDULE_ROW_HEIGHT = 28
_SCHEDULE_ROW_GAP = 8
_SCHEDULE_MAX_ROWS = 3
_SCHEDULE_MIN_HEIGHT = (
    _SCHEDULE_MAX_ROWS * _SCHEDULE_ROW_HEIGHT
    + (_SCHEDULE_MAX_ROWS - 1) * _SCHEDULE_ROW_GAP
)


@dataclass
class _FormRow:
    """One label + control row in the reset schedule form."""

    host: QWidget
    label: QLabel


class BudgetPeriodResetPanel(QWidget):
    """Period combo plus reset schedule fields tied to the selected period."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build period and reset controls."""
        super().__init__(parent)
        self.setObjectName("aiBudgetPeriodResetPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        period_row = self._make_row("Reset period", self._build_period_combo())
        root.addWidget(period_row.host)

        self._schedule_host = QWidget()
        self._schedule_host.setObjectName("aiBudgetResetSchedule")
        self._schedule_host.setMinimumHeight(_SCHEDULE_MIN_HEIGHT)
        schedule = QVBoxLayout(self._schedule_host)
        schedule.setContentsMargins(0, 0, 0, 0)
        schedule.setSpacing(_SCHEDULE_ROW_GAP)

        self._weekday = QComboBox()
        self._weekday.setObjectName("aiBudgetResetWeekday")
        for index, label in enumerate(_WEEKDAY_LABELS):
            self._weekday.addItem(label, index)

        self._month = QComboBox()
        self._month.setObjectName("aiBudgetResetMonth")
        for index, label in enumerate(_MONTH_LABELS, start=1):
            self._month.addItem(label, index)

        self._day = QSpinBox()
        self._day.setObjectName("aiBudgetResetDay")
        self._day.setRange(1, 31)

        self._time = QTimeEdit()
        self._time.setObjectName("aiBudgetResetTime")
        self._time.setDisplayFormat("HH:mm")
        self._time.setTime(QTime(0, 0))

        self._row_month = self._make_row("Month", self._month)
        self._row_weekday = self._make_row("Day", self._weekday)
        self._row_day = self._make_row("Day of month", self._day)
        self._row_time = self._make_row("Time", self._time)

        for row in (
            self._row_month,
            self._row_weekday,
            self._row_day,
            self._row_time,
        ):
            schedule.addWidget(row.host)
        schedule.addStretch(1)

        root.addWidget(self._schedule_host)
        self._period.currentIndexChanged.connect(self._sync_schedule_visibility)
        self._sync_schedule_visibility()

    def _build_period_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("aiBudgetPeriodCombo")
        for value in BUDGET_PERIODS:
            combo.addItem(BUDGET_PERIOD_LABELS[value], value)
        self._period = combo
        return combo

    def _make_row(self, label: str, widget: QWidget) -> _FormRow:
        """Build one aligned label + control row."""
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        text = QLabel(label)
        text.setObjectName("mutedLabel")
        text.setFixedWidth(_LABEL_WIDTH)
        text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(text, 0)
        row.addWidget(widget, 1)
        return _FormRow(host=host, label=text)

    def load(self, *, period: BudgetPeriod, period_anchor: str | None) -> None:
        """Populate controls from persisted budget fields."""
        period_index = BUDGET_PERIODS.index(period) if period in BUDGET_PERIODS else 0
        self._period.setCurrentIndex(period_index)
        reset = parse_period_reset(period_anchor)
        if reset is None:
            self._time.setTime(QTime(0, 0))
            self._weekday.setCurrentIndex(0)
            self._month.setCurrentIndex(0)
            self._day.setValue(1)
        else:
            self._time.setTime(QTime(reset.hour, reset.minute))
            self._weekday.setCurrentIndex(reset.anchor_date.weekday())
            self._month.setCurrentIndex(max(reset.anchor_date.month - 1, 0))
            self._day.setValue(reset.anchor_date.day)
        self._sync_schedule_visibility()

    def period(self) -> BudgetPeriod:
        """Return the selected budget period."""
        value = self._period.currentData()
        if isinstance(value, str) and value in BUDGET_PERIODS:
            return cast(BudgetPeriod, value)
        return "none"

    def period_anchor(self) -> str | None:
        """Serialize the reset schedule for the selected period."""
        period = self.period()
        if period == "none":
            return None
        hour = self._time.time().hour()
        minute = self._time.time().minute()
        if period == "daily":
            return daily_reset_anchor(hour=hour, minute=minute)
        if period == "weekly":
            weekday = self._weekday.currentData()
            if not isinstance(weekday, int):
                weekday = 0
            return weekly_reset_anchor(weekday=weekday, hour=hour, minute=minute)
        if period == "monthly":
            return monthly_reset_anchor(day=self._day.value(), hour=hour, minute=minute)
        if period == "yearly":
            month = self._month.currentData()
            if not isinstance(month, int):
                month = 1
            return yearly_reset_anchor(
                month=month,
                day=self._day.value(),
                hour=hour,
                minute=minute,
            )
        return None

    def _sync_schedule_visibility(self) -> None:
        """Show the reset fields that match the selected period."""
        period = self.period()
        self._schedule_host.setVisible(True)

        show_month = period == "yearly"
        show_weekday = period == "weekly"
        show_day = period in {"monthly", "yearly"}
        show_time = period != "none"

        self._row_month.host.setVisible(show_month)
        self._row_weekday.host.setVisible(show_weekday)
        self._row_day.host.setVisible(show_day)
        self._row_time.host.setVisible(show_time)

        if period == "monthly":
            self._row_day.label.setText("Day of month")
        elif period == "yearly":
            self._row_day.label.setText("Day")
        self._row_time.label.setText("Reset at" if period == "daily" else "Time")


__all__ = ["BudgetPeriodResetPanel"]
