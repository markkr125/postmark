"""Per-model spend breakdown panel for Settings → AI → Budgets."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services.ai.ai_budget_config import BudgetPeriod
from services.ai.budget_period import format_period_reset_label
from services.ai.chat.message_usage import (
    ModelSpendRow,
    format_run_context_tokens,
    format_usd_amount,
)
from services.ai.chat.spend_rollup import (
    ConnectionSpendSummary,
    format_budget_tokens_cell,
    format_budget_usd_cell,
)

_TOKENS_COL_WIDTH = 72
_COST_COL_WIDTH = 64
_ROW_VERTICAL_PADDING = 8


@dataclass(frozen=True)
class BudgetSpendDetailsContext:
    """Spend summary and per-model rows for one provider connection."""

    models: list[ModelSpendRow]
    rated: bool
    period: BudgetPeriod
    period_anchor: str | None
    period_known_usd: float
    period_usd: float | None
    period_tokens: int
    partial_period: bool
    overall_known_usd: float
    overall_usd: float | None
    overall_tokens: int
    partial_overall: bool

    @classmethod
    def from_spend(
        cls,
        spend: ConnectionSpendSummary | None,
        *,
        rated: bool,
        period: BudgetPeriod,
        period_anchor: str | None,
    ) -> BudgetSpendDetailsContext:
        """Build panel context from a connection rollup and limit settings."""
        if spend is None:
            return cls(
                models=[],
                rated=rated,
                period=period,
                period_anchor=period_anchor,
                period_known_usd=0.0,
                period_usd=None,
                period_tokens=0,
                partial_period=False,
                overall_known_usd=0.0,
                overall_usd=None,
                overall_tokens=0,
                partial_overall=False,
            )
        return cls(
            models=list(spend.get("models") or []),
            rated=rated,
            period=period,
            period_anchor=period_anchor,
            period_known_usd=float(spend.get("known_period_usd") or 0.0),
            period_usd=spend.get("period_usd"),
            period_tokens=int(spend.get("period_tokens") or 0),
            partial_period=bool(spend.get("partial_period")),
            overall_known_usd=float(spend.get("known_overall_usd") or 0.0),
            overall_usd=spend.get("overall_usd"),
            overall_tokens=int(spend.get("overall_tokens") or 0),
            partial_overall=bool(spend.get("partial_overall")),
        )


def _format_summary_amounts(
    *,
    known_usd: float,
    total_usd: float | None,
    tokens: int,
    partial: bool,
    rated: bool,
) -> str:
    """Format one summary line (USD and/or tokens) for the spend card."""
    usd = format_budget_usd_cell(
        known_usd=known_usd,
        total_usd=total_usd,
        partial=partial,
        rated=rated,
    )
    token_text = format_budget_tokens_cell(tokens)
    if not rated:
        return f"{token_text} tokens" if tokens > 0 else "—"
    if usd == "—" and token_text == "—":
        return "—"
    if usd == "—":
        return f"{token_text} tokens"
    if token_text == "—":
        return usd
    return f"{usd} · {token_text} tokens"


def _period_summary_title(period: BudgetPeriod, period_anchor: str | None) -> str:
    """Return the This period heading, including reset schedule when configured."""
    reset_label = format_period_reset_label(period, period_anchor)
    if reset_label:
        return f"This period · {reset_label}"
    return "This period"


class _SpendColumnHeader(QWidget):
    """Column labels aligned with model spend rows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build Model / Tokens / Cost header row."""
        super().__init__(parent)
        self.setObjectName("aiBudgetSpendDetailsHeader")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(8)

        model = QLabel("Model")
        model.setObjectName("mutedLabel")
        layout.addWidget(model, 1)

        tokens = QLabel("Tokens")
        tokens.setObjectName("mutedLabel")
        tokens.setFixedWidth(_TOKENS_COL_WIDTH)
        tokens.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(tokens, 0)

        cost = QLabel("Cost")
        cost.setObjectName("mutedLabel")
        cost.setFixedWidth(_COST_COL_WIDTH)
        cost.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(cost, 0)


class _BreakdownModelRow(QWidget):
    """One model row in the budget spend breakdown list."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build model, provider, token, and cost columns."""
        super().__init__(parent)
        self.setObjectName("aiBudgetSpendModelRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, _ROW_VERTICAL_PADDING, 0, _ROW_VERTICAL_PADDING)
        layout.setSpacing(8)

        name_col = QVBoxLayout()
        name_col.setContentsMargins(0, 0, 0, 0)
        name_col.setSpacing(2)
        self._model = QLabel("")
        name_col.addWidget(self._model)
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("mutedLabel")
        name_col.addWidget(self._subtitle)
        layout.addLayout(name_col, 1)

        self._tokens = QLabel("")
        self._tokens.setFixedWidth(_TOKENS_COL_WIDTH)
        self._tokens.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._tokens, 0)

        self._cost = QLabel("")
        self._cost.setFixedWidth(_COST_COL_WIDTH)
        self._cost.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._cost, 0)

    def set_row(self, row: ModelSpendRow, *, rated: bool) -> None:
        """Update row content from *row*."""
        self._model.setText(str(row.get("model_label") or ""))
        provider = str(row.get("provider_label") or "")
        turns = int(row.get("turn_count") or 0)
        if turns > 0:
            turn_word = "turn" if turns == 1 else "turns"
            subtitle = f"{provider} · {turns} {turn_word}" if provider else f"{turns} {turn_word}"
        else:
            subtitle = provider
        self._subtitle.setText(subtitle)

        tokens = (
            int(row.get("prompt_tokens") or 0)
            + int(row.get("completion_tokens") or 0)
            + int(row.get("reasoning_tokens") or 0)
        )
        self._tokens.setText(format_run_context_tokens(tokens))
        cost = row.get("cost_usd")
        if not rated or cost is None:
            self._cost.setText("—")
        else:
            self._cost.setText(format_usd_amount(float(cost)))


class _SpendSummaryCard(QFrame):
    """Connection-level period and all-time totals."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build side-by-side period and all-time summary blocks."""
        super().__init__(parent)
        self.setObjectName("aiBudgetSpendSummaryCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        period_col = QVBoxLayout()
        period_col.setContentsMargins(0, 0, 0, 0)
        period_col.setSpacing(4)
        self._period_title = QLabel("")
        self._period_title.setObjectName("titleLabel")
        period_col.addWidget(self._period_title)
        self._period_amounts = QLabel("")
        period_col.addWidget(self._period_amounts)
        layout.addLayout(period_col, 1)

        overall_col = QVBoxLayout()
        overall_col.setContentsMargins(0, 0, 0, 0)
        overall_col.setSpacing(4)
        self._overall_title = QLabel("All time")
        self._overall_title.setObjectName("titleLabel")
        overall_col.addWidget(self._overall_title)
        self._overall_amounts = QLabel("")
        overall_col.addWidget(self._overall_amounts)
        layout.addLayout(overall_col, 1)

    def set_context(self, context: BudgetSpendDetailsContext) -> None:
        """Refresh card labels from *context*."""
        self._period_title.setText(_period_summary_title(context.period, context.period_anchor))
        self._period_amounts.setText(
            _format_summary_amounts(
                known_usd=context.period_known_usd,
                total_usd=context.period_usd,
                tokens=context.period_tokens,
                partial=context.partial_period,
                rated=context.rated,
            )
        )
        self._overall_amounts.setText(
            _format_summary_amounts(
                known_usd=context.overall_known_usd,
                total_usd=context.overall_usd,
                tokens=context.overall_tokens,
                partial=context.partial_overall,
                rated=context.rated,
            )
        )


class BudgetSpendDetailsPanel(QWidget):
    """Scrollable per-model spend list for a provider connection."""

    def __init__(
        self,
        context: BudgetSpendDetailsContext,
        parent: QWidget | None = None,
    ) -> None:
        """Build the spend summary and model list for *context*."""
        super().__init__(parent)
        self.setObjectName("aiBudgetSpendDetailsPanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        intro = QLabel(
            "Totals below match the Budgets table. The model list is all-time usage "
            "across every chat session for this connection."
        )
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        root.addWidget(intro)

        if not context.rated:
            unrated_note = QLabel(
                "USD tracking requires model rates in Settings → Models. "
                "Token counts are still shown below."
            )
            unrated_note.setObjectName("mutedLabel")
            unrated_note.setWordWrap(True)
            root.addWidget(unrated_note)

        summary = _SpendSummaryCard()
        summary.set_context(context)
        root.addWidget(summary)

        models = context.models
        if not models:
            empty = QLabel("No usage recorded yet.")
            empty.setObjectName("mutedLabel")
            root.addWidget(empty)
        else:
            root.addWidget(_SpendColumnHeader())
            scroll = QScrollArea()
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidgetResizable(True)
            body = QWidget()
            rows_layout = QVBoxLayout(body)
            rows_layout.setContentsMargins(0, 0, 0, 0)
            rows_layout.setSpacing(0)
            for row in models:
                widget = _BreakdownModelRow(body)
                widget.set_row(row, rated=context.rated)
                rows_layout.addWidget(widget)
            rows_layout.addStretch(1)
            scroll.setWidget(body)
            root.addWidget(scroll, 1)

        footer = QLabel(
            "Estimated from model rates in Settings → Models. "
            "Some turns may be unpriced (shown as ~$X+). Compaction not included."
        )
        footer.setObjectName("mutedLabel")
        footer.setWordWrap(True)
        root.addWidget(footer)


__all__ = ["BudgetSpendDetailsContext", "BudgetSpendDetailsPanel"]
