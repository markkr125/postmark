"""Left-aligned enable checkbox for the AI models settings tree (column 0)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QStyle, QStyleOptionButton, QStyledItemDelegate, QStyleOptionViewItem

from ui.dialogs.settings.ai_page_actions import NAME_COLUMN

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

_GROUP_PREFIX = "group:"


_ROLE_ENABLED = Qt.ItemDataRole.UserRole + 20
_CHECK_MARGIN = 4


def set_model_row_enabled(item: QTreeWidgetItem, *, column: int, enabled: bool) -> None:
    """Store enabled state on a model row for :class:`AiModelsEnableDelegate`."""
    item.setData(column, _ROLE_ENABLED, enabled)


def model_row_enabled(item: QTreeWidgetItem, *, column: int) -> bool:
    """Read enabled state from a model row."""
    return bool(item.data(column, _ROLE_ENABLED))


class AiModelsEnableDelegate(QStyledItemDelegate):
    """Paint a checkbox flush with the left edge of the enable column (no tree indent)."""

    def __init__(self, tree: QTreeWidget, *, enabled_column: int) -> None:
        """Bind to *tree* and paint toggles in *enabled_column*."""
        super().__init__(tree)
        self._tree = tree
        self._enabled_column = enabled_column

    def _is_model_row(self, index: QModelIndex) -> bool:
        if not index.isValid():
            return False
        item = self._tree.itemFromIndex(index)
        if item is None:
            return False
        row_id = item.data(NAME_COLUMN, Qt.ItemDataRole.UserRole)
        return isinstance(row_id, str) and row_id and not row_id.startswith(_GROUP_PREFIX)

    def _paint_cell_background(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """Draw selection/hover/provider-alt background before custom foreground."""
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else None
        if style is None:
            return
        cell = QStyleOptionViewItem(option)
        cell.text = ""
        cell.icon = option.icon
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem,
            cell,
            painter,
            option.widget,
        )

    def _checkbox_rect(self, option: QStyleOptionViewItem) -> QRect:
        opt = QStyleOptionButton()
        opt.state = QStyle.StateFlag.State_Enabled
        if option.state & QStyle.StateFlag.State_MouseOver:
            opt.state |= QStyle.StateFlag.State_MouseOver
        box = self._tree.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, opt)
        x = self._tree.columnViewportPosition(self._enabled_column) + _CHECK_MARGIN
        y = option.rect.y() + (option.rect.height() - box.height()) // 2
        return QRect(x, y, box.width(), box.height())

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """Draw row background; model rows also paint the enable checkbox."""
        if not self._is_model_row(index):
            self._paint_cell_background(painter, option, index)
            return
        item = self._tree.itemFromIndex(index)
        if item is None:
            return
        self._paint_cell_background(painter, option, index)
        checked = model_row_enabled(item, column=self._enabled_column)
        opt = QStyleOptionButton()
        opt.rect = self._checkbox_rect(option)
        opt.state = QStyle.StateFlag.State_Enabled
        if checked:
            opt.state |= QStyle.StateFlag.State_On
        else:
            opt.state |= QStyle.StateFlag.State_Off
        if option.state & QStyle.StateFlag.State_MouseOver:
            opt.state |= QStyle.StateFlag.State_MouseOver
        self._tree.style().drawControl(QStyle.ControlElement.CE_CheckBox, opt, painter, self._tree)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Return checkbox size for model rows."""
        if not self._is_model_row(index):
            return super().sizeHint(option, index)
        return self._checkbox_rect(option).size()
