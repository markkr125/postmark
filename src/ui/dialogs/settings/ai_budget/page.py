"""Settings dialog — AI provider budgets page."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import cast

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from services.ai.ai_budget_config import (
    AiBudgetConfig,
    BUDGET_PERIODS,
    BudgetPeriod,
    ProviderBudgetEntry,
    validate_budget_entry,
)
from services.ai.ai_config import AiConfig, AiModelEntry
from services.ai.chat.spend_rollup import (
    ConnectionSpendSummary,
    GlobalSpendSummary,
    format_budget_limits_summary,
    format_budget_tokens_cell,
    format_budget_usd_cell,
    format_global_spend_summary_line,
    global_spend_summary,
)
from services.ai.provider_catalog import (
    connection_has_usd_pricing,
    provider_connection_key,
    provider_group_label,
)
from ui.dialogs.settings.ai_budget.breakdown_dialog import show_budget_spend_breakdown
from ui.dialogs.settings.ai_budget.limits_dialog import edit_budget_limits
from ui.dialogs.settings.ai_budget.row_actions import make_budget_row_gear_button

_MIN_LIMIT_USD = 0.01
_COL_PROVIDER = 0
_COL_PERIOD_USD = 1
_COL_PERIOD_TOKENS = 2
_COL_OVERALL_USD = 3
_COL_OVERALL_TOKENS = 4
_COL_LIMITS = 5
_COL_ACTIONS = 6


@dataclass
class _BudgetRowWidgets:
    """Editable state for one provider budget table row."""

    rated: bool
    period: BudgetPeriod
    period_anchor: str | None
    soft_limit_usd: float | None
    hard_limit_usd: float | None


class AiBudgetPageController:
    """Owns provider budget rows and persistence."""

    def __init__(self, page: QWidget, on_changed: Callable[[], None]) -> None:
        """Wire table widgets and load persisted budgets."""
        self._page = page
        self._on_changed = on_changed
        self._table = page.findChild(QTableWidget, "aiProviderBudgetsTree")
        self._status = page.findChild(QLabel, "aiBudgetStatusLabel")
        self._empty = page.findChild(QLabel, "aiBudgetEmptyLabel")
        self._summary = page.findChild(QLabel, "aiBudgetSpendSummaryLabel")
        self._row_widgets: dict[str, _BudgetRowWidgets] = {}
        self._row_keys: list[str] = []
        self._spend_by_key: dict[str, ConnectionSpendSummary] = {}
        self._global_spend: GlobalSpendSummary | None = None
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
        groups: dict[str, list[AiModelEntry]] = defaultdict(list)
        for entry in models:
            groups[provider_connection_key(entry)].append(entry)
        self._global_spend = global_spend_summary(models=models, budgets=list(budgets.values()))
        self._spend_by_key = {
            row["connection_key"]: row for row in self._global_spend.get("connections") or []
        }
        self._update_summary_strip()
        self._table.setRowCount(0)
        self._row_widgets.clear()
        self._row_keys.clear()
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
        sorted_groups = sorted(
            groups.items(),
            key=lambda kv: provider_group_label(kv[1][0]).lower(),
        )
        for row_index, (key, connection_models) in enumerate(sorted_groups):
            self._row_keys.append(key)
            stored = budgets.get(key, {})
            sample = connection_models[0]
            provider_label = provider_group_label(sample)
            rated = connection_has_usd_pricing(connection_models)
            widgets = self._row_state_from_stored(stored, rated=rated)
            self._row_widgets[key] = widgets
            self._table.setCellWidget(
                row_index,
                _COL_PROVIDER,
                self._make_text_label(provider_label, muted=False),
            )
            spend = self._spend_by_key.get(key)
            self._fill_spend_and_limits_cells(row_index, key, spend=spend, widgets=widgets)
            self._table.setCellWidget(
                row_index,
                _COL_ACTIONS,
                self._make_actions_cell(key, provider_label, rated=rated),
            )
        self._set_status("")
        self._loading = False

    def show_global_breakdown(self) -> None:
        """Open the all-models spend breakdown dialog."""
        summary = self._global_spend
        models = list(summary.get("models") or []) if summary is not None else []
        show_budget_spend_breakdown(
            title="Spend breakdown — all providers",
            models=models,
            parent=self._page.window(),
        )

    def apply(self) -> None:
        """Persist current table state (no-op when budgets already saved live)."""
        self._persist_if_valid()

    def _row_state_from_stored(
        self, stored: ProviderBudgetEntry, *, rated: bool
    ) -> _BudgetRowWidgets:
        """Build in-memory row state from persisted budget data."""
        stored_period = stored.get("period") or "none"
        if stored_period not in BUDGET_PERIODS:
            stored_period = "none"
        period = cast(BudgetPeriod, stored_period)
        soft_val = stored.get("soft_limit_usd")
        hard_val = stored.get("hard_limit_usd")
        return _BudgetRowWidgets(
            rated=rated,
            period=period,
            period_anchor=stored.get("period_anchor"),
            soft_limit_usd=(
                float(soft_val)
                if rated and soft_val is not None and soft_val >= _MIN_LIMIT_USD
                else None
            ),
            hard_limit_usd=(
                float(hard_val)
                if rated and hard_val is not None and hard_val >= _MIN_LIMIT_USD
                else None
            ),
        )

    def _update_summary_strip(self) -> None:
        if self._summary is None:
            return
        summary = self._global_spend
        if summary is None:
            self._summary.setText("")
            return
        has_rated = any(
            float(conn.get("known_overall_usd") or 0.0) > 0
            for conn in summary.get("connections") or []
        )
        period_line = format_global_spend_summary_line(
            label="This period",
            known_usd=float(summary.get("known_period_usd") or 0.0),
            total_usd=summary.get("period_usd"),
            tokens=int(summary.get("period_tokens") or 0),
            partial=bool(summary.get("partial_period")),
            has_rated_spend=has_rated,
        )
        overall_line = format_global_spend_summary_line(
            label="All time",
            known_usd=float(summary.get("known_overall_usd") or 0.0),
            total_usd=summary.get("overall_usd"),
            tokens=int(summary.get("overall_tokens") or 0),
            partial=bool(summary.get("partial_overall")),
            has_rated_spend=has_rated,
        )
        self._summary.setText(f"{period_line}   ·   {overall_line}")

    def _fill_spend_and_limits_cells(
        self,
        row_index: int,
        key: str,
        *,
        spend: ConnectionSpendSummary | None,
        widgets: _BudgetRowWidgets,
    ) -> None:
        """Populate spend, token, and limits cells for one row."""
        if self._table is None:
            return
        self._table.setCellWidget(
            row_index,
            _COL_PERIOD_USD,
            self._make_text_label(
                format_budget_usd_cell(
                    known_usd=float(spend.get("known_period_usd") or 0.0) if spend else 0.0,
                    total_usd=spend.get("period_usd") if spend else None,
                    partial=bool(spend.get("partial_period")) if spend else False,
                    rated=widgets.rated,
                ),
            ),
        )
        self._table.setCellWidget(
            row_index,
            _COL_PERIOD_TOKENS,
            self._make_text_label(
                format_budget_tokens_cell(int(spend.get("period_tokens") or 0) if spend else 0),
            ),
        )
        self._table.setCellWidget(
            row_index,
            _COL_OVERALL_USD,
            self._make_text_label(
                format_budget_usd_cell(
                    known_usd=float(spend.get("known_overall_usd") or 0.0) if spend else 0.0,
                    total_usd=spend.get("overall_usd") if spend else None,
                    partial=bool(spend.get("partial_overall")) if spend else False,
                    rated=widgets.rated,
                ),
            ),
        )
        self._table.setCellWidget(
            row_index,
            _COL_OVERALL_TOKENS,
            self._make_text_label(
                format_budget_tokens_cell(int(spend.get("overall_tokens") or 0) if spend else 0),
            ),
        )
        limits_text = self._limits_summary(widgets) if widgets.rated else "—"
        self._table.setCellWidget(
            row_index,
            _COL_LIMITS,
            self._make_text_label(limits_text, muted=True),
        )

    def _limits_summary(self, widgets: _BudgetRowWidgets) -> str:
        return format_budget_limits_summary(
            period=widgets.period,
            period_anchor=widgets.period_anchor,
            soft_limit_usd=widgets.soft_limit_usd,
            hard_limit_usd=widgets.hard_limit_usd,
        )

    def _make_text_label(self, text: str, *, muted: bool = True) -> QWidget:
        """Wrap one label for a read-only table cell."""
        host = QWidget()
        lay = QHBoxLayout(host)
        lay.setContentsMargins(4, 0, 4, 0)
        label = QLabel(text)
        if muted:
            label.setObjectName("mutedLabel")
        lay.addWidget(label)
        return host

    def _make_actions_cell(
        self, connection_key: str, provider_label: str, *, rated: bool
    ) -> QWidget:
        """Build the per-row gear menu."""
        return make_budget_row_gear_button(
            on_limits=(
                partial(self._edit_limits, connection_key, provider_label) if rated else None
            ),
            on_details=partial(self._show_row_breakdown, connection_key, provider_label),
        )

    def _edit_limits(self, connection_key: str, provider_label: str) -> None:
        widgets = self._row_widgets.get(connection_key)
        if widgets is None or not widgets.rated:
            return
        result = edit_budget_limits(
            provider_label=provider_label,
            period=widgets.period,
            period_anchor=widgets.period_anchor,
            soft_limit_usd=widgets.soft_limit_usd,
            hard_limit_usd=widgets.hard_limit_usd,
            parent=self._page.window(),
        )
        if result is None:
            return
        widgets.period = result.period
        widgets.period_anchor = result.period_anchor
        widgets.soft_limit_usd = result.soft_limit_usd
        widgets.hard_limit_usd = result.hard_limit_usd
        self._on_row_edited()

    def _show_row_breakdown(self, connection_key: str, provider_label: str) -> None:
        spend = self._spend_by_key.get(connection_key)
        models = list(spend.get("models") or []) if spend is not None else []
        show_budget_spend_breakdown(
            title=f"Spend breakdown — {provider_label}",
            models=models,
            parent=self._page.window(),
        )

    def _on_row_edited(self) -> None:
        if self._loading:
            return
        if self._persist_if_valid():
            self._on_changed()
            self._refresh_row_displays()

    def _refresh_row_displays(self) -> None:
        """Recompute spend and limits labels without rebuilding editors."""
        if self._table is None:
            return
        models = AiConfig.get_models()
        budgets = {entry["connection_key"]: entry for entry in AiBudgetConfig.get_budgets()}
        self._global_spend = global_spend_summary(models=models, budgets=list(budgets.values()))
        self._spend_by_key = {
            row["connection_key"]: row for row in self._global_spend.get("connections") or []
        }
        self._update_summary_strip()
        for row_index, key in enumerate(self._row_keys):
            widgets = self._row_widgets.get(key)
            if widgets is None:
                continue
            spend = self._spend_by_key.get(key)
            self._fill_spend_and_limits_cells(row_index, key, spend=spend, widgets=widgets)

    def _collect_entries(self) -> list[ProviderBudgetEntry]:
        """Read budget rows from in-memory row state."""
        entries: list[ProviderBudgetEntry] = []
        for key, widgets in self._row_widgets.items():
            if not widgets.rated:
                continue
            entry: ProviderBudgetEntry = {
                "connection_key": key,
                "period": widgets.period,
                "period_anchor": widgets.period_anchor,
                "soft_limit_usd": widgets.soft_limit_usd,
                "hard_limit_usd": widgets.hard_limit_usd,
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


def _configure_budget_table(table: QTableWidget) -> None:
    """Stretch the provider column and size the rest to content."""
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(_COL_PROVIDER, QHeaderView.ResizeMode.Stretch)
    for col in range(1, table.columnCount()):
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)


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
        "Track spend per provider connection (same groups as Models). Rated providers can "
        "open the gear menu to set reset schedules and optional USD limits. Soft limits "
        "warn when exceeded; hard limits block new messages once enforcement is enabled."
    )
    intro.setObjectName("mutedLabel")
    intro.setWordWrap(True)
    layout.addWidget(intro)

    summary_row = QHBoxLayout()
    summary_row.setContentsMargins(0, 0, 0, 0)
    summary_row.setSpacing(8)
    summary = QLabel("")
    summary.setObjectName("aiBudgetSpendSummaryLabel")
    summary_row.addWidget(summary, 1)
    view_breakdown = QPushButton("View breakdown")
    view_breakdown.setObjectName("aiBudgetViewBreakdownBtn")
    summary_row.addWidget(view_breakdown, 0)
    layout.addLayout(summary_row)

    empty = QLabel("No provider connections configured. Add providers under AI → Models.")
    empty.setObjectName("aiBudgetEmptyLabel")
    empty.setWordWrap(True)
    layout.addWidget(empty)

    table = QTableWidget(0, 7)
    table.setObjectName("aiProviderBudgetsTree")
    table.setHorizontalHeaderLabels(
        [
            "Provider",
            "Period spend",
            "Period tokens",
            "All-time spend",
            "All-time tokens",
            "Limits",
            "",
        ]
    )
    table.verticalHeader().setVisible(False)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    _configure_budget_table(table)
    layout.addWidget(table, 1)

    status = QLabel("")
    status.setObjectName("aiBudgetStatusLabel")
    status.setWordWrap(True)
    layout.addWidget(status)

    ctrl = AiBudgetPageController(page, on_changed)
    view_breakdown.clicked.connect(ctrl.show_global_breakdown)
    return page, ctrl


__all__ = ["AiBudgetPageController", "build_ai_budget_page"]
