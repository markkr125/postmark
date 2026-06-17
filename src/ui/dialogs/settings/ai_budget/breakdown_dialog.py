"""Per-model spend breakdown dialog for Settings → AI → Budgets."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services.ai.chat.message_usage import (
    ModelSpendRow,
    format_run_context_tokens,
    format_usd_amount,
)


class _BreakdownModelRow(QWidget):
    """One model row in the budget spend breakdown dialog."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build model, provider, token, and cost columns."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        name_col = QVBoxLayout()
        name_col.setContentsMargins(0, 0, 0, 0)
        name_col.setSpacing(0)
        self._model = QLabel("")
        name_col.addWidget(self._model)
        self._provider = QLabel("")
        self._provider.setObjectName("mutedLabel")
        name_col.addWidget(self._provider)
        layout.addLayout(name_col, 1)

        self._tokens = QLabel("")
        self._tokens.setObjectName("mutedLabel")
        layout.addWidget(self._tokens, 0)

        self._cost = QLabel("")
        self._cost.setObjectName("mutedLabel")
        layout.addWidget(self._cost, 0)

    def set_row(self, row: ModelSpendRow) -> None:
        """Update row content from *row*."""
        self._model.setText(str(row.get("model_label") or ""))
        self._provider.setText(str(row.get("provider_label") or ""))
        tokens = (
            int(row.get("prompt_tokens") or 0)
            + int(row.get("completion_tokens") or 0)
            + int(row.get("reasoning_tokens") or 0)
        )
        self._tokens.setText(format_run_context_tokens(tokens))
        cost = row.get("cost_usd")
        if cost is None:
            self._cost.setText("—")
        else:
            self._cost.setText(format_usd_amount(float(cost)))


class AiBudgetSpendBreakdownDialog(QDialog):
    """Modal table of per-model spend for one connection or all providers."""

    def __init__(
        self,
        *,
        title: str,
        models: list[ModelSpendRow],
        parent: QWidget | None = None,
    ) -> None:
        """Build the dialog for *models*."""
        super().__init__(parent)
        self.setObjectName("aiBudgetSpendBreakdownDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        if not models:
            empty = QLabel("No usage recorded yet.")
            empty.setObjectName("mutedLabel")
            root.addWidget(empty)
        else:
            scroll = QScrollArea()
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidgetResizable(True)
            body = QWidget()
            rows_layout = QVBoxLayout(body)
            rows_layout.setContentsMargins(0, 0, 0, 0)
            rows_layout.setSpacing(6)
            for row in models:
                widget = _BreakdownModelRow(body)
                widget.set_row(row)
                rows_layout.addWidget(widget)
            rows_layout.addStretch(1)
            scroll.setWidget(body)
            root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)


def show_budget_spend_breakdown(
    *,
    title: str,
    models: list[ModelSpendRow],
    parent: QWidget | None = None,
) -> None:
    """Open the spend breakdown dialog modally."""
    dialog = AiBudgetSpendBreakdownDialog(title=title, models=models, parent=parent)
    dialog.exec()


__all__ = ["AiBudgetSpendBreakdownDialog", "show_budget_spend_breakdown"]
