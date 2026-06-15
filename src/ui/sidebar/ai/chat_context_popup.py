"""Context usage popover for the AI chat composer ring."""

from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import QDateTime, QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import Shiboken

from services.ai.chat.context_usage import ContextUsageBreakdown, ContextUsageCategory
from services.ai.provider_catalog import format_run_context_tokens
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
        self._breakdown = _empty_breakdown()
        self._rows: list[_CategoryRow] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        title = QLabel("Context Usage")
        title.setObjectName("titleLabel")
        header.addWidget(title, 1)
        self._close_btn = QPushButton()
        self._close_btn.setObjectName("iconButton")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setIcon(phi("x", size=14))
        self._close_btn.clicked.connect(self.hide_popup)
        header.addWidget(self._close_btn, 0)
        root.addLayout(header)

        summary = QHBoxLayout()
        summary.setContentsMargins(0, 0, 0, 0)
        summary.setSpacing(8)
        self._summary_left = QLabel("")
        summary.addWidget(self._summary_left, 1)
        self._summary_right = QLabel("")
        self._summary_right.setObjectName("mutedLabel")
        summary.addWidget(self._summary_right, 0)
        root.addLayout(summary)

        self._bar = ContextUsageBar(self)
        root.addWidget(self._bar)

        self._hint = QLabel("")
        self._hint.setObjectName("mutedLabel")
        self._hint.setWordWrap(True)
        self._hint.hide()
        root.addWidget(self._hint)

        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        body = QWidget()
        self._rows_layout = QVBoxLayout(body)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        for _ in range(8):
            row = _CategoryRow(body)
            self._rows.append(row)
            self._rows_layout.addWidget(row)
        self._rows_layout.addStretch(1)
        self.set_breakdown(self._breakdown)

    def show_for(self, anchor: QWidget, breakdown: ContextUsageBreakdown | None) -> None:
        """Populate from *breakdown* and show above *anchor*."""
        app = QGuiApplication.instance()
        if app is not None and self.isVisible():
            app.removeEventFilter(self)
        self._anchor = anchor
        self.set_breakdown(breakdown or _empty_breakdown())
        self.adjustSize()
        self._position_for(anchor)
        self.show()
        self.raise_()
        self._opened_at_ms = QDateTime.currentMSecsSinceEpoch()
        if app is not None:
            app.installEventFilter(self)

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


__all__ = ["AiChatContextUsagePopup", "ContextUsageBar", "compute_bar_segments"]
