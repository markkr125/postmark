"""Context usage popover for the AI chat composer ring."""

from __future__ import annotations

from typing import ClassVar, Literal

from PySide6.QtCore import QDateTime, QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import Shiboken

from services.ai.chat.budget_status import (
    ConnectionBudgetStatus,
    connection_budget_card_visible,
    format_connection_budget_card_amounts,
)
from services.ai.chat.context_usage import ContextUsageBreakdown, ContextUsageCategory
from services.ai.chat.message_usage import (
    SessionSpendBreakdown,
    format_spend_tab_label,
    format_usd_amount,
)
from services.ai.provider_catalog import format_run_context_tokens
from ui.sidebar.ai.chat_panel.context_popup_mode_pill import ContextPopupModePill
from ui.styling.icons import phi
from ui.styling.theme import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_DELETE,
    COLOR_MUTED,
    COLOR_OPTIONS,
    COLOR_SUCCESS,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
)
from ui.styling.theme_manager import ThemeManager

_SHOW_GRACE_MS = 200
_SPEND_POPUP_MIN_HEIGHT_PX = 300
_SPEND_POPUP_MAX_HEIGHT_PX = 420
_SPEND_LIST_MIN_HEIGHT_PX = 140
_SPEND_LIST_MAX_HEIGHT_PX = 260
_QWIDGET_MAX_HEIGHT = 16777215

PopupMode = Literal["context", "spend"]


def _empty_spend_breakdown() -> SessionSpendBreakdown:
    """Return a zeroed spend breakdown for initial popup renders."""
    return {
        "total_usd": None,
        "known_usd": 0.0,
        "assistant_turns": 0,
        "priced_turns": 0,
        "partial": False,
        "models": [],
    }


def _install_bar_theme_hook(widget: ContextUsageBar) -> None:
    """Connect ``ThemeManager.theme_changed`` so the bar repaints on theme flips."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    for child in app.children():
        if isinstance(child, ThemeManager):
            child.theme_changed.connect(widget.update)
            return


def _category_color(category_id: str) -> str:
    """Return the theme color used for one Cursor-style context bucket."""
    return {
        "system_prompt": COLOR_ACCENT,
        "tools": COLOR_SUCCESS,
        "rules": COLOR_WARNING,
        "skills": COLOR_OPTIONS,
        "mcp": COLOR_DANGER,
        "subagents": COLOR_DELETE,
        "summarized_conversation": COLOR_MUTED,
        "conversation": COLOR_TEXT,
    }.get(category_id, COLOR_TEXT_MUTED)


def _empty_breakdown() -> ContextUsageBreakdown:
    """Return a zeroed breakdown for initial popup renders."""
    categories: list[ContextUsageCategory] = [
        {"id": "system_prompt", "label": "System prompt", "tokens": 0},
        {"id": "tools", "label": "Tools", "tokens": 0},
        {"id": "rules", "label": "Rules", "tokens": 0},
        {"id": "skills", "label": "Skills", "tokens": 0},
        {"id": "mcp", "label": "MCP", "tokens": 0},
        {"id": "subagents", "label": "Subagents", "tokens": 0},
        {"id": "summarized_conversation", "label": "Summarized conversation", "tokens": 0},
        {"id": "conversation", "label": "Conversation", "tokens": 0},
    ]
    return {
        "used_tokens": 0,
        "total_tokens": 0,
        "categories": categories,
        "has_summarized": False,
        "is_estimated": True,
    }


def compute_bar_segments(
    *,
    bar_width: int,
    used_tokens: int,
    total_tokens: int,
    categories: list[ContextUsageCategory],
) -> list[tuple[str, int, int]]:
    """Return ``(category_id, x_offset, width)`` segments for one usage bar.

    The filled portion spans ``used_tokens / total_tokens`` of *bar_width*; category
    colors are stacked only inside that slice so the track still shows headroom.
    """
    if bar_width <= 0:
        return []
    category_total = sum(max(0, int(cat["tokens"])) for cat in categories)
    if category_total <= 0:
        return []
    if total_tokens > 0:
        fill_width = min(bar_width, max(0, round(bar_width * used_tokens / total_tokens)))
    else:
        fill_width = bar_width
    if fill_width <= 0:
        return []

    segments: list[tuple[str, int, int]] = []
    x = 0
    remaining_w = fill_width
    non_zero = [cat for cat in categories if int(cat["tokens"]) > 0]
    for index, category in enumerate(non_zero):
        tokens = max(0, int(category["tokens"]))
        if index == len(non_zero) - 1:
            width = remaining_w
        else:
            width = max(1, round(fill_width * tokens / category_total))
            width = min(width, remaining_w)
        if width <= 0:
            continue
        segments.append((category["id"], x, width))
        x += width
        remaining_w = max(0, fill_width - x)
    return segments


class ContextUsageBar(QWidget):
    """Stacked horizontal bar showing one segment per context bucket."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create an empty stacked bar."""
        super().__init__(parent)
        self._categories: list[ContextUsageCategory] = []
        self._used_tokens = 0
        self._total_tokens = 0
        self.setFixedHeight(10)
        _install_bar_theme_hook(self)

    def set_usage(
        self,
        *,
        used_tokens: int,
        total_tokens: int,
        categories: list[ContextUsageCategory],
    ) -> None:
        """Apply totals, categories, and repaint."""
        self._used_tokens = max(0, used_tokens)
        self._total_tokens = max(0, total_tokens)
        self._categories = list(categories)
        self.update()

    def set_categories(self, categories: list[ContextUsageCategory]) -> None:
        """Apply categories only and repaint (legacy helper for tests)."""
        self._categories = list(categories)
        self.update()

    def fill_width(self) -> int:
        """Return how many pixels of the widget width represent used context."""
        total_w = max(0, self.width() - 1)
        if total_w <= 0:
            return 0
        segments = compute_bar_segments(
            bar_width=total_w,
            used_tokens=self._used_tokens,
            total_tokens=self._total_tokens,
            categories=self._categories,
        )
        if not segments:
            return 0
        return segments[-1][1] + segments[-1][2]

    def paintEvent(self, event) -> None:
        """Paint the muted track and non-zero colored segments."""
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        painter.setPen(QPen(QColor(COLOR_BORDER), 1))
        painter.setBrush(QColor(COLOR_BORDER))
        painter.drawRoundedRect(rect, 4, 4)
        segments = compute_bar_segments(
            bar_width=rect.width(),
            used_tokens=self._used_tokens,
            total_tokens=self._total_tokens,
            categories=self._categories,
        )
        for category_id, offset, width in segments:
            left = rect.x() + offset
            right = left + width - 1
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(_category_color(category_id)))
            painter.drawRoundedRect(left, rect.y(), right - left + 1, rect.height(), 4, 4)


class _SpendModelRow(QWidget):
    """One model row in the session spend flyout."""

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

    def set_row(
        self,
        *,
        model_label: str,
        provider_label: str,
        tokens: int,
        cost_usd: float | None,
        turn_count: int = 0,
    ) -> None:
        """Update row content."""
        self._model.setText(model_label)
        if turn_count > 0:
            turn_word = "turn" if turn_count == 1 else "turns"
            subtitle = (
                f"{provider_label} · {turn_count} {turn_word}"
                if provider_label
                else f"{turn_count} {turn_word}"
            )
        else:
            subtitle = provider_label
        self._provider.setText(subtitle)
        self._tokens.setText(format_run_context_tokens(tokens))
        if cost_usd is None:
            self._cost.setText("—")
        else:
            self._cost.setText(format_usd_amount(cost_usd))


class _CategoryRow(QWidget):
    """Legend row for one context bucket."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build one swatch + label + count row."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._swatch = QLabel("●")
        self._swatch.setFixedWidth(12)
        layout.addWidget(self._swatch, 0)

        self._label = QLabel("")
        layout.addWidget(self._label, 1)

        self._tokens = QLabel("")
        self._tokens.setObjectName("mutedLabel")
        layout.addWidget(self._tokens, 0)

    def set_category(self, category: ContextUsageCategory) -> None:
        """Update row content from *category*."""
        self._swatch.setStyleSheet(f"color: {_category_color(category['id'])};")
        self._label.setText(category["label"])
        self._tokens.setText(format_run_context_tokens(int(category["tokens"])))


class AiChatContextUsagePopup(QFrame):
    """Singleton flyout showing the full context breakdown above the ring."""

    hidden = Signal()
    _instance: ClassVar[AiChatContextUsagePopup | None] = None

    @classmethod
    def instance(cls) -> AiChatContextUsagePopup:
        """Return the shared popup, creating it when needed."""
        if cls._instance is not None and not Shiboken.isValid(cls._instance):
            cls._instance = None
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the popup chrome and empty breakdown rows."""
        super().__init__(parent)
        self.setObjectName("aiChatContextPopup")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedWidth(320)

        self._anchor: QWidget | None = None
        self._opened_at_ms = 0
        self._mode: PopupMode = "context"
        self._breakdown = _empty_breakdown()
        self._spend_breakdown = _empty_spend_breakdown()
        self._connection_budget: ConnectionBudgetStatus | None = None
        self._rows: list[_CategoryRow] = []
        self._spend_rows: list[_SpendModelRow] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        self._context_pill = ContextPopupModePill("Context")
        self._context_pill.clicked.connect(lambda: self.set_mode("context"))
        header.addWidget(self._context_pill, 0)
        self._cost_pill = ContextPopupModePill("Spend")
        self._cost_pill.clicked.connect(lambda: self.set_mode("spend"))
        header.addWidget(self._cost_pill, 0)
        header.addStretch(1)
        self._close_btn = QPushButton()
        self._close_btn.setObjectName("iconButton")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setIcon(phi("x", size=14))
        self._close_btn.clicked.connect(self.hide_popup)
        header.addWidget(self._close_btn, 0)
        root.addLayout(header)

        self._context_body = QWidget(self)
        context_layout = QVBoxLayout(self._context_body)
        context_layout.setContentsMargins(0, 0, 0, 0)
        context_layout.setSpacing(8)

        summary = QHBoxLayout()
        summary.setContentsMargins(0, 0, 0, 0)
        summary.setSpacing(8)
        self._summary_left = QLabel("")
        context_layout.addLayout(summary)
        summary.addWidget(self._summary_left, 1)
        self._summary_right = QLabel("")
        self._summary_right.setObjectName("mutedLabel")
        summary.addWidget(self._summary_right, 0)

        self._bar = ContextUsageBar(self)
        context_layout.addWidget(self._bar)

        self._hint = QLabel("")
        self._hint.setObjectName("mutedLabel")
        self._hint.setWordWrap(True)
        self._hint.hide()
        context_layout.addWidget(self._hint)

        context_scroll = QScrollArea()
        context_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        context_scroll.setWidgetResizable(True)
        context_body = QWidget()
        self._rows_layout = QVBoxLayout(context_body)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        context_scroll.setWidget(context_body)
        context_layout.addWidget(context_scroll, 1)

        for _ in range(8):
            category_row = _CategoryRow(context_body)
            self._rows.append(category_row)
            self._rows_layout.addWidget(category_row)
        self._rows_layout.addStretch(1)
        root.addWidget(self._context_body, 1)

        self._spend_body = QWidget(self)
        spend_layout = QVBoxLayout(self._spend_body)
        spend_layout.setContentsMargins(0, 0, 0, 0)
        spend_layout.setSpacing(8)

        self._spend_summary = QLabel("")
        spend_layout.addWidget(self._spend_summary)

        self._budget_card = QFrame()
        self._budget_card.setObjectName("aiChatBudgetStatusCard")
        budget_layout = QVBoxLayout(self._budget_card)
        budget_layout.setContentsMargins(12, 12, 12, 12)
        budget_layout.setSpacing(4)
        self._budget_title = QLabel("")
        self._budget_title.setObjectName("titleLabel")
        budget_layout.addWidget(self._budget_title)
        self._budget_amounts = QLabel("")
        budget_layout.addWidget(self._budget_amounts)
        self._budget_reset = QLabel("")
        self._budget_reset.setObjectName("mutedLabel")
        budget_layout.addWidget(self._budget_reset)
        self._budget_card.hide()
        spend_layout.addWidget(self._budget_card)

        spend_scroll = QScrollArea()
        spend_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        spend_scroll.setWidgetResizable(True)
        spend_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._spend_scroll = spend_scroll
        spend_body = QWidget()
        self._spend_rows_layout = QVBoxLayout(spend_body)
        self._spend_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._spend_rows_layout.setSpacing(6)
        spend_scroll.setWidget(spend_body)
        spend_layout.addWidget(spend_scroll, 1)

        for _ in range(10):
            spend_row = _SpendModelRow(spend_body)
            self._spend_rows.append(spend_row)
            self._spend_rows_layout.addWidget(spend_row)
        self._spend_rows_layout.addStretch(1)

        self._spend_empty = QLabel("No usage recorded yet.")
        self._spend_empty.setObjectName("mutedLabel")
        self._spend_empty.setWordWrap(True)
        self._spend_empty.hide()
        spend_layout.addWidget(self._spend_empty)

        self._spend_footer = QLabel(
            "Estimated from model rates in Settings. Compaction not included. "
            "Rates apply at read time."
        )
        self._spend_footer.setObjectName("mutedLabel")
        self._spend_footer.setWordWrap(True)
        spend_layout.addWidget(self._spend_footer)
        self._spend_body.hide()
        root.addWidget(self._spend_body, 1)

        self.set_breakdown(self._breakdown)
        self.set_mode("context")

    def set_mode(self, mode: PopupMode) -> None:
        """Switch flyout body between context breakdown and session spend."""
        self._mode = mode
        self._context_pill.set_active(mode == "context")
        self._cost_pill.set_active(mode == "spend")
        self._apply_mode_visibility()
        self._apply_popup_size_constraints()
        self.adjustSize()
        if self._anchor is not None:
            self._position_for(self._anchor)

    def _apply_popup_size_constraints(self) -> None:
        """Clamp Spend tab height; Context tab sizes to its breakdown naturally."""
        if self._mode == "spend":
            self.setMinimumHeight(_SPEND_POPUP_MIN_HEIGHT_PX)
            self.setMaximumHeight(_SPEND_POPUP_MAX_HEIGHT_PX)
            self._spend_scroll.setMinimumHeight(_SPEND_LIST_MIN_HEIGHT_PX)
            self._spend_scroll.setMaximumHeight(_SPEND_LIST_MAX_HEIGHT_PX)
            self._spend_scroll.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            return
        self.setMinimumHeight(0)
        self.setMaximumHeight(_QWIDGET_MAX_HEIGHT)
        self._spend_scroll.setMinimumHeight(0)
        self._spend_scroll.setMaximumHeight(_QWIDGET_MAX_HEIGHT)

    def show_for(
        self,
        anchor: QWidget,
        breakdown: ContextUsageBreakdown | None,
        *,
        spend_breakdown: SessionSpendBreakdown | None = None,
    ) -> None:
        """Populate and show above *anchor*; opens on the Context tab."""
        if spend_breakdown is not None:
            self.set_spend_breakdown(spend_breakdown)
        self._show_popup(anchor, "context", breakdown=breakdown or _empty_breakdown())

    def _show_popup(
        self,
        anchor: QWidget,
        mode: PopupMode,
        *,
        breakdown: ContextUsageBreakdown | None = None,
        spend_breakdown: SessionSpendBreakdown | None = None,
    ) -> None:
        """Show or dismiss the popup above *anchor*."""
        app = QGuiApplication.instance()
        if app is not None and self.isVisible():
            app.removeEventFilter(self)
        if self.isVisible() and self._anchor is anchor:
            self.hide_popup()
            return
        self._anchor = anchor
        if breakdown is not None:
            self.set_breakdown(breakdown)
        if spend_breakdown is not None:
            self.set_spend_breakdown(spend_breakdown)
        self.set_mode(mode)
        self.adjustSize()
        self._position_for(anchor)
        self.show()
        self.raise_()
        self._opened_at_ms = QDateTime.currentMSecsSinceEpoch()
        if app is not None:
            app.installEventFilter(self)

    def _apply_mode_visibility(self) -> None:
        """Toggle context vs spend sections."""
        is_context = self._mode == "context"
        self._context_body.setVisible(is_context)
        self._spend_body.setVisible(not is_context)

    def set_spend_breakdown(self, breakdown: SessionSpendBreakdown) -> None:
        """Refresh spend-mode popup contents and the Spend pill label."""
        self._spend_breakdown = breakdown
        self._cost_pill.setText(format_spend_tab_label(breakdown))
        turns = int(breakdown.get("assistant_turns") or 0)
        models = list(breakdown.get("models") or [])
        if turns <= 0:
            total_label = "—"
        elif breakdown.get("partial"):
            total_label = f"~{format_usd_amount(float(breakdown.get('known_usd') or 0.0))}+"
        else:
            total = breakdown.get("total_usd")
            total_label = format_usd_amount(float(total)) if total is not None else "—"
        turn_word = "turn" if turns == 1 else "turns"
        self._spend_summary.setText(f"{total_label} · {turns} assistant {turn_word}")
        has_rows = bool(models)
        self._spend_empty.setVisible(not has_rows)
        for row in self._spend_rows:
            row.hide()
        for index, model_row in enumerate(models):
            if index >= len(self._spend_rows):
                break
            row = self._spend_rows[index]
            tokens = (
                int(model_row.get("prompt_tokens") or 0)
                + int(model_row.get("completion_tokens") or 0)
                + int(model_row.get("reasoning_tokens") or 0)
            )
            row.set_row(
                model_label=str(model_row.get("model_label") or ""),
                provider_label=str(model_row.get("provider_label") or ""),
                tokens=tokens,
                cost_usd=model_row.get("cost_usd"),
                turn_count=int(model_row.get("turn_count") or 0),
            )
            row.show()

    def set_connection_budget(self, status: ConnectionBudgetStatus | None) -> None:
        """Refresh the connection budget card on the Spend tab."""
        self._connection_budget = status
        if not connection_budget_card_visible(status):
            self._budget_card.hide()
            return
        assert status is not None
        self._budget_title.setText(f"{status['provider_label']} · this period")
        self._budget_amounts.setText(format_connection_budget_card_amounts(status))
        reset_label = status.get("period_reset_label") or ""
        if reset_label:
            self._budget_reset.setText(f"Resets {reset_label}")
            self._budget_reset.show()
        else:
            self._budget_reset.hide()
        self._budget_card.show()

    def set_breakdown(self, breakdown: ContextUsageBreakdown) -> None:
        """Refresh popup contents while it is open."""
        self._breakdown = breakdown
        used = int(breakdown["used_tokens"])
        total = int(breakdown["total_tokens"])
        pct = min(100, round(100 * used / total)) if total > 0 else 0
        left = f"{pct}% Full"
        if breakdown["is_estimated"]:
            left += "  Estimated"
        self._summary_left.setText(left)
        self._summary_right.setText(
            f"~{format_run_context_tokens(used)} / {format_run_context_tokens(total)} Tokens"
        )
        self._bar.set_usage(
            used_tokens=used,
            total_tokens=total,
            categories=breakdown["categories"],
        )
        for row, category in zip(self._rows, breakdown["categories"], strict=False):
            row.set_category(category)
        has_summary_tokens = any(
            category["id"] == "summarized_conversation" and int(category["tokens"]) > 0
            for category in breakdown["categories"]
        )
        hint_lines: list[str] = []
        used = int(breakdown["used_tokens"])
        total = int(breakdown["total_tokens"])
        high_usage = total > 0 and used / total >= 0.70
        if breakdown["is_estimated"] and high_usage:
            hint_lines.append("This is estimated until the model context is available.")
        if breakdown.get("transcript_larger_than_sdk") and high_usage:
            hint_lines.append(
                "This session's saved transcript is larger than the model context currently loaded."
            )
        if breakdown["has_summarized"] and has_summary_tokens:
            hint_lines.append("The assistant no longer sees older messages verbatim.")
        if hint_lines:
            self._hint.setText(" ".join(hint_lines))
            self._hint.show()
        else:
            self._hint.hide()

    def hide_popup(self) -> None:
        """Dismiss the popup and remove the click-away filter."""
        if not self.isVisible():
            return
        app = QGuiApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.hide()
        self._anchor = None
        self.hidden.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Dismiss on Escape."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide_popup()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Close on an outside mouse press after the grace window."""
        is_press = event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent)
        past_grace = QDateTime.currentMSecsSinceEpoch() - self._opened_at_ms >= _SHOW_GRACE_MS
        if is_press and past_grace and self.isVisible():
            mouse = event
            global_pos = mouse.globalPosition().toPoint()  # type: ignore[attr-defined]
            if self.geometry().contains(global_pos):
                return super().eventFilter(obj, event)
            if self._hits_anchor(global_pos):
                return super().eventFilter(obj, event)
            self.hide_popup()
        return super().eventFilter(obj, event)

    def _hits_anchor(self, global_pos: QPoint) -> bool:
        """Return whether *global_pos* lands on the ring button anchor."""
        if self._anchor is None or not self._anchor.isVisible():
            return False
        local = self._anchor.mapFromGlobal(global_pos)
        return self._anchor.rect().contains(local)

    def _position_for(self, anchor: QWidget) -> None:
        """Place the popup above *anchor*, right-aligned to the ring."""
        gap = 4
        top_right = anchor.mapToGlobal(anchor.rect().topRight())
        x = top_right.x() - self.width()
        y = top_right.y() - self.height() - gap
        screen = QGuiApplication.screenAt(top_right) or QGuiApplication.primaryScreen()
        sr = screen.availableGeometry() if screen else None
        if sr is not None:
            x = max(sr.left(), min(x, sr.right() - self.width()))
            y = max(sr.top(), min(y, sr.bottom() - self.height()))
        self.move(x, y)


__all__ = [
    "AiChatContextUsagePopup",
    "ContextUsageBar",
    "PopupMode",
    "compute_bar_segments",
]
