"""Delegate that paints AI model capability pills without per-row QWidget embedding."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QEvent, QModelIndex, QPersistentModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QHelpEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
)

from services.ai.provider_catalog import CapabilityKind, CapabilityTag
from ui.styling.theme import (
    BADGE_BORDER_RADIUS,
    BADGE_FONT_SIZE,
    BADGE_HEIGHT,
    ai_capability_color,
)

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTreeWidget

_CAPABILITIES_COLUMN = 5
_TAG_GAP = 4
_TAG_PAD_X = 6


def _tags_from_index(index: QModelIndex | QPersistentModelIndex) -> list[CapabilityTag]:
    raw = index.data(Qt.ItemDataRole.UserRole)
    if not isinstance(raw, list):
        return []
    out: list[CapabilityTag] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        tooltip = item.get("tooltip")
        kind = item.get("kind")
        if (
            isinstance(label, str)
            and isinstance(tooltip, str)
            and kind
            in (
                "suggest",
                "tools",
                "vision",
            )
        ):
            out.append(
                cast(
                    "CapabilityTag",
                    {"label": label, "tooltip": tooltip, "kind": cast("CapabilityKind", kind)},
                )
            )
    return out


def _pill_layout(
    tags: list[CapabilityTag], *, cell_rect: QRect
) -> list[tuple[QRect, CapabilityTag]]:
    """Return each pill rect and tag, laid out left-to-right inside *cell_rect*."""
    if not tags:
        return []
    font = QFont()
    font.setPixelSize(BADGE_FONT_SIZE)
    font.setBold(True)
    fm = QFontMetrics(font)
    y = cell_rect.top() + (cell_rect.height() - BADGE_HEIGHT) // 2
    x = cell_rect.left() + 4
    right = cell_rect.right() - 4
    placed: list[tuple[QRect, CapabilityTag]] = []
    for tag in tags:
        text_w = fm.horizontalAdvance(tag["label"])
        w = text_w + _TAG_PAD_X * 2
        if x + w > right:
            break
        placed.append((QRect(x, y, w, BADGE_HEIGHT), tag))
        x += w + _TAG_GAP
    return placed


class AiModelsTreeDelegate(QStyledItemDelegate):
    """Paints capability tags in the models tree Capabilities column (model rows only)."""

    def __init__(
        self, tree: QTreeWidget, *, capabilities_column: int = _CAPABILITIES_COLUMN
    ) -> None:
        """Attach to *tree*; custom paint applies only to *capabilities_column*."""
        super().__init__(tree)
        self._tree = tree
        self._capabilities_column = capabilities_column

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Draw colored capability pills for model rows; default paint otherwise."""
        if index.column() != self._capabilities_column:
            super().paint(painter, option, index)
            return
        tags = _tags_from_index(index)
        if not tags:
            super().paint(painter, option, index)
            return

        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else None
        if style:
            opt = QStyleOptionViewItem(option)
            opt.text = ""
            opt.icon = option.icon
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, option.widget)

        rect: QRect = option.rect  # type: ignore[assignment]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        badge_font = QFont(painter.font())
        badge_font.setPixelSize(BADGE_FONT_SIZE)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        for pill_rect, tag in _pill_layout(tags, cell_rect=rect):
            bg, fg = ai_capability_color(tag["kind"])
            painter.setBrush(QColor(bg))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(pill_rect, BADGE_BORDER_RADIUS, BADGE_BORDER_RADIUS)
            painter.setPen(QPen(QColor(fg)))
            painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, tag["label"])
        painter.restore()

    def helpEvent(
        self,
        event: QHelpEvent,
        view: QAbstractItemView,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """Show per-tag tooltips when the pointer is over a capability pill."""
        if event.type() != QEvent.Type.ToolTip or index.column() != self._capabilities_column:
            return super().helpEvent(event, view, option, index)
        tags = _tags_from_index(index)
        if not tags:
            return super().helpEvent(event, view, option, index)
        pos = event.pos()
        for pill_rect, tag in _pill_layout(tags, cell_rect=option.rect):
            if pill_rect.contains(pos):
                QToolTip.showText(event.globalPos(), tag["tooltip"], view)
                return True
        QToolTip.hideText()
        return True

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        """Keep uniform row height for capability rows."""
        if index.column() == self._capabilities_column and _tags_from_index(index):
            return QSize(option.rect.width(), BADGE_HEIGHT + 8)
        return super().sizeHint(option, index)
