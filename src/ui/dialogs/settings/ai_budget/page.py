"""Settings dialog — AI provider budgets page."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.ai.ai_budget_config import (
    BUDGET_PERIOD_LABELS,
    BUDGET_PERIODS,
    AiBudgetConfig,
    ProviderBudgetEntry,
    validate_budget_entry,
)
from services.ai.ai_config import AiConfig, AiModelEntry
from services.ai.provider_catalog import provider_connection_key, provider_group_label

_MIN_LIMIT_USD = 0.01


@dataclass
class _BudgetRowWidgets:
    """Widgets for one provider budget table row."""

    period: QComboBox
    soft_enable: QCheckBox
    soft_spin: QDoubleSpinBox
    hard_enable: QCheckBox
    hard_spin: QDoubleSpinBox


class AiBudgetPageController:
    """Owns provider budget rows and persistence."""

    def __init__(self, page: QWidget, on_changed: Callable[[], None]) -> None:
        """Wire table widgets and load persisted budgets."""
        self._page = page
        self._on_changed = on_changed
        self._table = page.findChild(QTableWidget, "aiProviderBudgetsTree")
        self._status = page.findChild(QLabel, "aiBudgetStatusLabel")
        self._empty = page.findChild(QLabel, "aiBudgetEmptyLabel")
        self._row_widgets: dict[str, _BudgetRowWidgets] = {}
        self._loading = False
        if self._table is not None:
            self.reload()

    def reload(self) -> None:
        """Rebuild rows from configured models and stored budgets."""
        if self._table is None:
            return
        self._loading = True
        models = AiConfig.get_models()
        budgets = {entry["connection_key"]: entry for entry in AiBudgetConfig.get_budgets()}
        groups: dict[str, AiModelEntry] = {}
        for entry in models:
            key = provider_connection_key(entry)
            groups.setdefault(key, entry)
        self._table.setRowCount(0)
        self._row_widgets.clear()
        if not groups:
            if self._empty is not None:
                self._empty.show()
            self._table.hide()
            self._set_status("")
            self._loading = False
            return
        if self._empty is not None:
            self._empty.hide()
        self._table.show()
        self._table.setRowCount(len(groups))
        sorted_groups = sorted(groups.items(), key=lambda kv: provider_group_label(kv[1]).lower())
        for row_index, (key, sample) in enumerate(sorted_groups):
            stored = budgets.get(key, {})
            name_item = QTableWidgetItem(provider_group_label(sample))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setData(Qt.ItemDataRole.UserRole, key)
            self._table.setItem(row_index, 0, name_item)
            widgets = self._make_limit_cell(stored)
            self._row_widgets[key] = widgets
            self._table.setCellWidget(row_index, 1, widgets.period)
            self._table.setCellWidget(
                row_index, 2, self._wrap_limit(widgets.soft_enable, widgets.soft_spin)
            )
            self._table.setCellWidget(
                row_index, 3, self._wrap_limit(widgets.hard_enable, widgets.hard_spin)
            )
        self._table.resizeColumnsToContents()
        self._set_status("")
        self._loading = False

    def apply(self) -> None:
        """Persist current table state (no-op when budgets already saved live)."""
        self._persist_if_valid()

    def _make_limit_cell(self, stored: ProviderBudgetEntry) -> _BudgetRowWidgets:
        """Build period combo and soft/hard limit controls for one row."""
        period = QComboBox()
        period.setObjectName("aiBudgetPeriodCombo")
        for value in BUDGET_PERIODS:
            period.addItem(BUDGET_PERIOD_LABELS[value], value)
        stored_period = stored.get("period") or "none"
        period_index = BUDGET_PERIODS.index(stored_period) if stored_period in BUDGET_PERIODS else 0
        period.setCurrentIndex(period_index)
        period.currentIndexChanged.connect(self._on_row_edited)

        soft_enable = QCheckBox()
        soft_spin = self._make_spin()
        soft_val = stored.get("soft_limit_usd")
        if soft_val is not None and soft_val >= _MIN_LIMIT_USD:
            soft_enable.setChecked(True)
            soft_spin.setValue(float(soft_val))
        soft_enable.toggled.connect(
            lambda checked, spin=soft_spin: self._set_limit_spin_enabled(spin, checked)
        )
        soft_spin.valueChanged.connect(self._on_row_edited)

        hard_enable = QCheckBox()
        hard_spin = self._make_spin()
        hard_val = stored.get("hard_limit_usd")
        if hard_val is not None and hard_val >= _MIN_LIMIT_USD:
            hard_enable.setChecked(True)
            hard_spin.setValue(float(hard_val))
        hard_enable.toggled.connect(
            lambda checked, spin=hard_spin: self._set_limit_spin_enabled(spin, checked)
        )
        hard_spin.valueChanged.connect(self._on_row_edited)

        soft_spin.setEnabled(soft_enable.isChecked())
        hard_spin.setEnabled(hard_enable.isChecked())
        return _BudgetRowWidgets(
            period=period,
            soft_enable=soft_enable,
            soft_spin=soft_spin,
            hard_enable=hard_enable,
            hard_spin=hard_spin,
        )

    def _make_spin(self) -> QDoubleSpinBox:
        """Return a USD limit spin box."""
        spin = QDoubleSpinBox()
        spin.setObjectName("aiBudgetLimitSpin")
        spin.setDecimals(2)
        spin.setMinimum(_MIN_LIMIT_USD)
        spin.setMaximum(1_000_000.0)
        spin.setSingleStep(0.01)
        spin.setSuffix(" USD")
        spin.setValue(_MIN_LIMIT_USD)
        return spin

    def _wrap_limit(self, enable: QCheckBox, spin: QDoubleSpinBox) -> QWidget:
        """Lay out enable checkbox and limit spin on one table cell."""
        host = QWidget()
        lay = QHBoxLayout(host)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(6)
        lay.addWidget(enable, 0)
        lay.addWidget(spin, 1)
        return host

    def _set_limit_spin_enabled(self, spin: QDoubleSpinBox, checked: bool) -> None:
        """Enable or disable a limit spin box and persist when valid."""
        spin.setEnabled(checked)
        self._on_row_edited()

    def _on_row_edited(self) -> None:
        if self._loading:
            return
        if self._persist_if_valid():
            self._on_changed()

    def _collect_entries(self) -> list[ProviderBudgetEntry]:
        """Read budget rows from the table widgets."""
        entries: list[ProviderBudgetEntry] = []
        for key, widgets in self._row_widgets.items():
            period = widgets.period.currentData()
            if not isinstance(period, str):
                period = "none"
            entry: ProviderBudgetEntry = {
                "connection_key": key,
                "period": period,  # type: ignore[typeddict-item]
                "soft_limit_usd": widgets.soft_spin.value()
                if widgets.soft_enable.isChecked()
                else None,
                "hard_limit_usd": widgets.hard_spin.value()
                if widgets.hard_enable.isChecked()
                else None,
            }
            entries.append(entry)
        return entries

    def _persist_if_valid(self) -> bool:
        entries = self._collect_entries()
        for entry in entries:
            err = validate_budget_entry(entry)
            if err is not None:
                self._set_status(err)
                return False
        AiBudgetConfig.save_all(entries)
        self._set_status("")
        return True

    def _set_status(self, text: str) -> None:
        if self._status is not None:
            self._status.setText(text)


def build_ai_budget_page(on_changed: Callable[[], None]) -> tuple[QWidget, AiBudgetPageController]:
    """Build the AI Budgets settings page."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(12)

    heading = QLabel("Budgets")
    heading.setObjectName("titleLabel")
    layout.addWidget(heading)

    intro = QLabel(
        "Set optional spending limits per provider connection (same groups as Models). "
        "Soft limits warn when exceeded; hard limits block new messages once enforcement "
        "is enabled. Limits are saved per connection. Local providers without model "
        "pricing can set limits, but spend tracking requires rates from Settings → Models."
    )
    intro.setObjectName("mutedLabel")
    intro.setWordWrap(True)
    layout.addWidget(intro)

    empty = QLabel("No provider connections configured. Add providers under AI → Models.")
    empty.setObjectName("aiBudgetEmptyLabel")
    empty.setWordWrap(True)
    layout.addWidget(empty)

    table = QTableWidget(0, 4)
    table.setObjectName("aiProviderBudgetsTree")
    table.setHorizontalHeaderLabels(["Provider", "Period", "Soft limit", "Hard limit"])
    table.verticalHeader().setVisible(False)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    layout.addWidget(table, 1)

    status = QLabel("")
    status.setObjectName("aiBudgetStatusLabel")
    status.setWordWrap(True)
    layout.addWidget(status)

    ctrl = AiBudgetPageController(page, on_changed)
    return page, ctrl


__all__ = ["AiBudgetPageController", "build_ai_budget_page"]
