"""Trailing (i) control on sidebar tree leaves (local scripts, snippets)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QPersistentModelIndex, QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent, QPainter
from PySide6.QtWidgets import QTreeWidget

from ui.styling.icons import phi
from ui.styling.theme import COLOR_TEXT_MUTED
from ui.widgets.info_popup import InfoPopup

# Layout matches the local-scripts tree screenshot (compact icon at row right).
TREE_ROW_INFO_ICON_PX = 14
TREE_ROW_INFO_RIGHT_GAP_PX = 6
TREE_ROW_INFO_HIT_PAD_PX = 2


def tree_row_info_rect(row_rect: QRect) -> QRect:
    """Return the icon bounds for the trailing (i) in *row_rect*."""
    size = TREE_ROW_INFO_ICON_PX
    x = row_rect.right() - TREE_ROW_INFO_RIGHT_GAP_PX - size
    y = row_rect.top() + (row_rect.height() - size) // 2
    return QRect(x, y, size, size)


def paint_tree_row_info_button(painter: QPainter, row_rect: QRect) -> QRect:
    """Draw the muted info icon; return its paint/hit rectangle."""
    icon_rect = tree_row_info_rect(row_rect)
    icon = phi("info", size=TREE_ROW_INFO_ICON_PX, color=COLOR_TEXT_MUTED)
    painter.drawPixmap(
        icon_rect,
        icon.pixmap(TREE_ROW_INFO_ICON_PX, TREE_ROW_INFO_ICON_PX),
    )
    return icon_rect


def tree_row_info_hit(row_rect: QRect, pos: QPoint) -> bool:
    """Return whether *pos* (viewport coordinates) is on the (i) control."""
    hit = tree_row_info_rect(row_rect)
    hit = hit.adjusted(
        -TREE_ROW_INFO_HIT_PAD_PX,
        -TREE_ROW_INFO_HIT_PAD_PX,
        TREE_ROW_INFO_HIT_PAD_PX,
        TREE_ROW_INFO_HIT_PAD_PX,
    )
    return hit.contains(pos)


def name_rect_before_info(name_rect: QRect, row_rect: QRect) -> QRect:
    """Shrink *name_rect* so elided text does not run under the (i) icon."""
    info_left = tree_row_info_rect(row_rect).left()
    if name_rect.right() >= info_left - 4:
        name_rect.setRight(max(name_rect.left(), info_left - 4))
    return name_rect


def show_tree_row_info_popup(
    popup: InfoPopup,
    tree: QTreeWidget,
    index: QModelIndex | QPersistentModelIndex,
) -> None:
    """Show *popup* adjacent to the visual row for *index*."""
    rect = tree.visualRect(index)
    global_pt = tree.viewport().mapToGlobal(rect.bottomLeft())
    popup.adjustSize()
    screen = tree.screen()
    if screen is not None:
        sr = screen.availableGeometry()
        hint = popup.sizeHint()
        if global_pt.x() + hint.width() > sr.right():
            global_pt.setX(sr.right() - hint.width())
        if global_pt.x() < sr.left():
            global_pt.setX(sr.left())
        if global_pt.y() + hint.height() > sr.bottom():
            global_pt = tree.viewport().mapToGlobal(rect.topLeft())
            global_pt.setY(global_pt.y() - hint.height())
    popup.move(global_pt)
    popup.show()
    popup.activateWindow()
    popup.setFocus()


def tree_row_info_editor_event(
    event: QEvent,
    *,
    tree: QTreeWidget,
    index: QModelIndex | QPersistentModelIndex,
    on_info: object,
) -> bool:
    """Handle mouse release on the (i); call *on_info* when hit."""
    if event.type() != QEvent.Type.MouseButtonRelease:
        return False
    me = event
    if not isinstance(me, QMouseEvent):
        return False
    if me.button() != Qt.MouseButton.LeftButton:
        return False
    rect = tree.visualRect(index)
    if not tree_row_info_hit(rect, me.pos()):
        return False
    on_info()  # type: ignore[operator]
    return True


def script_info_body(
    *,
    basename: str,
    language: str,
    module_format: str,
) -> str:
    """Format local-script row metadata for the info popup."""
    from ui.local_scripts.script_filename import script_display_name, script_tooltip

    display = script_display_name(basename, language, module_format)
    return script_tooltip(basename, language, module_format) + f"\n\nFile: {display}"
