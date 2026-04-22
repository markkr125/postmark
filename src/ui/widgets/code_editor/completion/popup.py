"""Completion popup for the code editor.

Displays a filtered list of :class:`CompletionItem` suggestions below
the cursor.  Handles keyboard navigation (arrows, Enter/Tab to accept,
Escape to dismiss) and mouse clicks.

Styled via global QSS targeting ``objectName="completionPopup"``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFocusEvent, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from PySide6.QtCore import QModelIndex, QPersistentModelIndex

    from ui.widgets.code_editor.completion.engine import CompletionItem

# Maximum visible rows before scrollbar activates.
_MAX_VISIBLE_ITEMS = 10

# Fixed row height for consistent sizing.
_ROW_HEIGHT = 22

# Icons for different completion kinds.
_KIND_ICONS: dict[str, str] = {
    "method": "\u2a5e",  # small function glyph
    "property": "\u25c6",  # diamond
    "object": "\u25a0",  # filled square
    "variable": "\u03b1",  # alpha
    "keyword": "K",
}


class _CompletionDelegate(QStyledItemDelegate):
    """Custom delegate rendering kind icon, label, and type string."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Render a completion row: icon + name + type_str."""
        self.initStyleOption(option, index)
        painter.save()

        # Draw selection/hover background.
        style = option.widget.style() if option.widget else QWidget().style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter)

        rect = option.rect
        left = rect.left() + 6

        # Kind icon
        kind = index.data(Qt.ItemDataRole.UserRole + 1) or "property"
        icon_char = _KIND_ICONS.get(kind, "\u25c6")

        from ui.styling.theme import _active

        icon_font = QFont(option.font)
        icon_font.setPointSize(max(1, icon_font.pointSize() - 1))
        painter.setFont(icon_font)
        painter.setPen(option.palette.color(option.palette.ColorRole.Highlight))
        painter.drawText(
            left, rect.top(), 16, rect.height(), Qt.AlignmentFlag.AlignCenter, icon_char
        )
        left += 20

        # Label (bold)
        label = index.data(Qt.ItemDataRole.DisplayRole) or ""
        label_font = QFont(option.font)
        label_font.setBold(True)
        painter.setFont(label_font)
        painter.setPen(option.palette.color(option.palette.ColorRole.Text))
        fm_bold = painter.fontMetrics()
        painter.drawText(
            left,
            rect.top(),
            fm_bold.horizontalAdvance(label) + 4,
            rect.height(),
            Qt.AlignmentFlag.AlignVCenter,
            label,
        )
        left += fm_bold.horizontalAdvance(label) + 8

        # Type string (muted)
        type_str = index.data(Qt.ItemDataRole.UserRole + 2) or ""
        if type_str:
            muted_font = QFont(option.font)
            muted_font.setPointSize(max(1, muted_font.pointSize() - 1))
            painter.setFont(muted_font)
            painter.setPen(_active["text_muted"])
            painter.drawText(
                left,
                rect.top(),
                rect.right() - left - 4,
                rect.height(),
                Qt.AlignmentFlag.AlignVCenter,
                type_str,
            )

        painter.restore()

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        """Return a fixed-height size hint."""
        return QSize(0, _ROW_HEIGHT)


class CompletionPopup(QFrame):
    """Floating autocomplete popup for the code editor.

    Signals:
        item_selected: Emitted when the user accepts a completion.
            Carries ``(insert_text, kind)`` — the text to insert and
            the completion kind (for adding parentheses to methods).
        dismissed: Emitted when the popup closes without selection.
    """

    item_selected = Signal(str, str)
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the popup with frameless tool-window flags."""
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setObjectName("completionPopup")
        self.setFixedWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)

        # Doc label (shown above list for the selected item).
        self._doc_label = QLabel()
        self._doc_label.setObjectName("completionPopupDoc")
        self._doc_label.setWordWrap(True)
        self._doc_label.hide()
        layout.addWidget(self._doc_label)

        self._list = QListWidget()
        self._list.setObjectName("completionPopupList")
        self._list.setItemDelegate(_CompletionDelegate(self._list))
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setMouseTracking(True)
        self._list.itemClicked.connect(self._accept_current)
        self._list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list)

        self._items: list[CompletionItem] = []

    # -- Public API ----------------------------------------------------

    def set_items(self, items: list[CompletionItem]) -> None:
        """Populate the popup with completion items."""
        self._items = items
        self._list.clear()

        for item in items:
            li = QListWidgetItem(item.label)
            li.setData(Qt.ItemDataRole.UserRole, item.insert_text)
            li.setData(Qt.ItemDataRole.UserRole + 1, item.kind)
            li.setData(Qt.ItemDataRole.UserRole + 2, item.type_str)
            li.setData(Qt.ItemDataRole.UserRole + 3, item.doc)
            li.setData(Qt.ItemDataRole.UserRole + 4, item.signature)
            self._list.addItem(li)

        visible = min(len(items), _MAX_VISIBLE_ITEMS)
        self._list.setFixedHeight(visible * _ROW_HEIGHT + 2)
        self.adjustSize()

        if items:
            self._list.setCurrentRow(0)

    def select_next(self) -> None:
        """Move selection down by one row."""
        row = self._list.currentRow()
        if row < self._list.count() - 1:
            self._list.setCurrentRow(row + 1)

    def select_previous(self) -> None:
        """Move selection up by one row."""
        row = self._list.currentRow()
        if row > 0:
            self._list.setCurrentRow(row - 1)

    def accept_current(self) -> None:
        """Accept the currently selected completion."""
        self._accept_current()

    def dismiss(self) -> None:
        """Hide the popup and emit dismissed signal."""
        self.hide()
        self.dismissed.emit()

    def is_active(self) -> bool:
        """Return whether the popup is currently visible."""
        return self.isVisible()

    # -- Event overrides -----------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        """Delegate to QFrame for border rendering."""
        super().paintEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        """Dismiss when focus is lost."""
        super().focusOutEvent(event)
        self.dismiss()

    # -- Private -------------------------------------------------------

    def _accept_current(self) -> None:
        """Emit the selected item and hide."""
        item = self._list.currentItem()
        if item is None:
            self.dismiss()
            return
        insert_text = item.data(Qt.ItemDataRole.UserRole) or ""
        kind = item.data(Qt.ItemDataRole.UserRole + 1) or "property"
        self.hide()
        self.item_selected.emit(insert_text, kind)

    def _on_row_changed(self, row: int) -> None:
        """Update the doc label when the selection changes."""
        if row < 0 or row >= len(self._items):
            self._doc_label.hide()
            return
        item = self._items[row]
        doc_parts: list[str] = []
        if item.signature:
            doc_parts.append(f"<b>{item.label}</b>{item.signature}")
        if item.doc:
            doc_parts.append(item.doc)
        if doc_parts:
            self._doc_label.setText("  ".join(doc_parts))
            self._doc_label.show()
        else:
            self._doc_label.hide()
        self.adjustSize()
